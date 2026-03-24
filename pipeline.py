from __future__ import annotations

import re
from pathlib import Path
from collections import defaultdict
from typing import Iterable, List, TextIO

from .coordinate_policy import CoordinatePolicy
from .export_types import (
    CoordinateMode,
    ExportContext,
    ExportOptions,
    MaterialData,
    ObjectExportRecord,
    ObjectMeshData,
    SceneExportData,
    TransformMode,
    Vec2,
    Vec3,
)
from .material_extractor import MaterialExtractor
from .transform_extractor import TransformExtractor
from .writers_material import MaterialWriter
from .writers_mesh import MeshDeclarationWriter
from .writers_object import ObjectSceneWriter

print("[POV EXPORT DEBUG] pipeline loaded from:", __file__)
print("[POV EXPORT DEBUG] ObjectExportRecord fields:", ObjectExportRecord.__annotations__)

class ExportError(Exception):
    """Raised for expected exporter failures that should be shown to the user."""


def export_povmesh(
    context,
    filepath,
    coordinate_mode="BLENDER_TO_POV",
    export_materials=True,
    emit_debug_helpers=True,
    include_comments=True,
):
    """
    Export selected Blender mesh objects as reusable POV-Ray parts plus one final asset.

    Export rules
    ------------
    - every selected mesh object exports as its own local-space mesh2 declaration
    - every part may export one minimal material declaration
    - every part gets a declared wrapper object with a matrix transform
    - if one part exists, the final asset is a declared object wrapper
    - if multiple parts exist, the final asset is a declared union
    """
    try:
        export_ctx = ExportContext(filepath=Path(filepath))
        export_options = ExportOptions(
            transform_mode=TransformMode.EMIT_OBJECT_TRANSFORMS,
            coordinate_mode=CoordinateMode(coordinate_mode),
            export_materials=bool(export_materials),
            emit_debug_helpers=bool(emit_debug_helpers),
            combine_objects=False,
            include_comments=bool(include_comments),
        )

        objects = MeshCollector.get_selected_mesh_objects(context)
        scene_data = MeshExtractor.extract_scene_data_for_asset_export(
            context=context,
            objects=objects,
            export_ctx=export_ctx,
            export_options=export_options,
        )

        FileWriter.ensure_parent_dir(export_ctx.filepath)
        SceneWriter.write_scene_file(export_ctx.filepath, scene_data)

        print(
            "[povmesh_export] Exported "
            f"{len(scene_data.source_names)} part(s) to '{export_ctx.filepath}' "
            f"as asset '{scene_data.asset_export_name}'"
        )
        return {"FINISHED"}

    except ExportError:
        raise

    except Exception as exc:
        raise ExportError(f"Unexpected export failure: {exc}") from exc


class MeshCollector:
    @staticmethod
    def get_selected_mesh_objects(context):
        selected = getattr(context, "selected_objects", None)
        if not selected:
            raise ExportError("No objects selected.")

        mesh_objects = [obj for obj in selected if obj.type == "MESH"]

        if not mesh_objects:
            raise ExportError("No mesh object selected.")

        return MeshCollector.sort_objects_deterministically(mesh_objects)

    @staticmethod
    def sort_objects_deterministically(objects):
        return sorted(objects, key=lambda obj: (obj.name.casefold(), obj.name))


class MeshExtractor:
    @staticmethod
    def extract_scene_data_for_asset_export(
        context,
        objects,
        export_ctx: ExportContext,
        export_options: ExportOptions,
    ) -> SceneExportData:
        source_names: List[str] = [obj.name for obj in objects]
        asset_export_name = NamePolicy.make_export_name(export_ctx.filepath, source_names)

        object_records: List[ObjectExportRecord] = []

        for obj in objects:
            object_parts = MeshExtractor._extract_object_mesh_parts(
                context,
                obj,
                export_options,
            )

            if not object_parts:
                continue

            transform_data = TransformExtractor.extract_transform_data(obj, export_options)
            multiple_parts = len(object_parts) > 1

            for material_slot_index, object_mesh_data in object_parts:
                source_material_name = MaterialExtractor.get_slot_material_name(
                    obj,
                    material_slot_index,
                )

                part_export_name = NamePolicy.make_part_export_name(
                    asset_export_name,
                    obj.name,
                    material_slot_index=material_slot_index if multiple_parts else None,
                    material_name=source_material_name,
                )

                material_data = None
                if export_options.export_materials:
                    if multiple_parts:
                        material_data = MaterialExtractor.extract_material_data_for_slot(
                            obj,
                            material_slot_index,
                            part_export_name,
                        )
                    else:
                        material_data = MaterialExtractor.extract_material_data(
                            obj,
                            part_export_name,
                        )

                object_records.append(
                    ObjectExportRecord(
                        source_name=obj.name,
                        export_name=part_export_name,
                        mesh_data=None,
                        object_mesh_data=object_mesh_data,
                        transform_data=transform_data,
                        material_data=material_data,
                        material_slot_index=material_slot_index,
                        source_material_name=source_material_name,
                    )
                )

        if not object_records:
            raise ExportError("Selected mesh objects contained no exportable faces.")

        return SceneExportData(
            export_context=export_ctx,
            export_options=export_options,
            object_records=object_records,
            combined_mesh_data=None,
            source_names=[record.source_name for record in object_records],
            asset_export_name=asset_export_name,
        )

    @staticmethod
    def _extract_object_mesh_parts(
        context,
        obj,
        export_options: ExportOptions,
    ) -> List[tuple[int, ObjectMeshData]]:
        depsgraph = context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)

        mesh_eval = None

        try:
            mesh_eval = obj_eval.to_mesh(
                preserve_all_data_layers=True,
                depsgraph=depsgraph,
            )

            if mesh_eval is None:
                raise ExportError(
                    f"Unable to evaluate mesh from selected object '{obj.name}'."
                )

            mesh_eval.calc_loop_triangles()
            return ExpandedCornerBuilder.build_object_mesh_parts(
                obj,
                mesh_eval,
                export_options,
            )

        finally:
            if mesh_eval is not None:
                obj_eval.to_mesh_clear()


class ExpandedCornerBuilder:
    @staticmethod
    def build_object_mesh_parts(
        obj,
        mesh,
        export_options: ExportOptions,
    ) -> List[tuple[int, ObjectMeshData]]:
        triangles_by_slot: dict[int, list] = defaultdict(list)

        polygon_count = len(getattr(mesh, "polygons", []))

        for tri in mesh.loop_triangles:
            polygon_index = getattr(tri, "polygon_index", -1)
            material_slot_index = -1

            if 0 <= polygon_index < polygon_count:
                polygon = mesh.polygons[polygon_index]
                material_slot_index = int(getattr(polygon, "material_index", -1))

            triangles_by_slot[material_slot_index].append(tri)

        part_records: List[tuple[int, ObjectMeshData]] = []
        for material_slot_index in sorted(triangles_by_slot):
            tri_group = triangles_by_slot[material_slot_index]
            if not tri_group:
                continue

            object_mesh_data = ExpandedCornerBuilder._build_object_mesh_data_for_triangles(
                obj,
                mesh,
                export_options,
                tri_group,
            )

            if object_mesh_data.faces:
                part_records.append((material_slot_index, object_mesh_data))

        return part_records

    @staticmethod
    def _build_object_mesh_data_for_triangles(
        obj,
        mesh,
        export_options: ExportOptions,
        triangles: Iterable,
    ) -> ObjectMeshData:
        uv_layer = UVExtractor.get_active_render_uv_layer(mesh)

        vertices: List[Vec3] = []
        faces: List[tuple[int, int, int]] = []
        normals: List[Vec3] = []
        normal_indices: List[tuple[int, int, int]] = []
        uvs: List[Vec2] = []
        uv_indices: List[tuple[int, int, int]] = []

        for tri in triangles:
            if len(tri.loops) != 3:
                raise ExportError(
                    "Triangulation failed: encountered a non-triangle loop triangle."
                )

            face_corner_indices: List[int] = []
            uv_corner_indices: List[int] = []

            for loop_index in tri.loops:
                vertex_index = mesh.loops[loop_index].vertex_index
                vert = mesh.vertices[vertex_index]

                co_local = vert.co
                co_export = CoordinatePolicy.convert_point(
                    (
                        float(co_local.x),
                        float(co_local.y),
                        float(co_local.z),
                    ),
                    export_options.coordinate_mode,
                )
                vertices.append(co_export)
                face_corner_indices.append(len(vertices) - 1)

                normal_local = vert.normal.copy()
                normal_local.normalize()
                normal_export = CoordinatePolicy.convert_normal(
                    (
                        float(normal_local.x),
                        float(normal_local.y),
                        float(normal_local.z),
                    ),
                    export_options.coordinate_mode,
                )
                normals.append(normal_export)

                if uv_layer is not None:
                    uv = uv_layer.data[loop_index].uv
                    u = 1.0 - float(uv.x)
                    v = float(uv.y)
                    uvs.append((u, v))
                    uv_corner_indices.append(len(uvs) - 1)

            face = (
                face_corner_indices[0],
                face_corner_indices[1],
                face_corner_indices[2],
            )
            faces.append(face)
            normal_indices.append(face)

            if uv_layer is not None:
                uv_indices.append(
                    (
                        uv_corner_indices[0],
                        uv_corner_indices[1],
                        uv_corner_indices[2],
                    )
                )

        return ObjectMeshData(
            source_name=obj.name,
            vertices=vertices,
            faces=faces,
            normals=normals,
            normal_indices=normal_indices,
            uvs=uvs,
            uv_indices=uv_indices,
        )


class UVExtractor:
    @staticmethod
    def get_active_render_uv_layer(mesh):
        uv_layers = getattr(mesh, "uv_layers", None)
        if not uv_layers:
            return None

        active_render = getattr(uv_layers, "active_render", None)
        if active_render is not None:
            return active_render

        active = getattr(uv_layers, "active", None)
        if active is not None:
            return active

        if len(uv_layers) > 0:
            return uv_layers[0]

        return None


class SceneWriter:
    @staticmethod
    def write_scene_file(filepath: Path, scene_data: SceneExportData) -> None:
        with open(filepath, "w", encoding="utf-8", newline="\n") as f:
            if scene_data.export_options.include_comments:
                SceneWriter._write_header(f, scene_data)

            SceneWriter._write_mesh_declarations(
                f,
                scene_data,
                include_comments=scene_data.export_options.include_comments,
            )
            f.write("\n")

            SceneWriter._write_material_declarations(
                f,
                scene_data,
                include_comments=scene_data.export_options.include_comments,
            )
            f.write("\n")

            SceneWriter._write_debug_helpers(f, scene_data)
            f.write("\n")

            ObjectSceneWriter.write_object_declarations(
                f,
                scene_data,
                include_comments=scene_data.export_options.include_comments,
            )
            f.write("\n")

            ObjectSceneWriter.write_asset_declaration(
                f,
                scene_data,
                include_comments=scene_data.export_options.include_comments,
            )

    @staticmethod
    def _write_header(f: TextIO, scene_data: SceneExportData) -> None:
        policy_info = CoordinatePolicy.get_info(scene_data.export_options.coordinate_mode)

        f.write("// POV-Ray mesh2 export\n")
        f.write("// Generated by Blender add-on: POV-Ray Mesh2 Exporter\n")
        f.write("// Export mode: per-part local-space declarations with assembled asset output\n")
        f.write("// Geometry policy: each selected Blender mesh object exports in local coordinates\n")
        f.write("// Transform policy: part wrapper matrices are derived from Blender world transforms\n")
        f.write(f"// Coordinate policy: {policy_info.short_label}\n")
        f.write(f"// Coordinate policy detail: {policy_info.description}\n")

        if scene_data.export_options.export_materials:
            f.write("// Material policy: per-part minimal material export enabled\n")
        else:
            f.write("// Material policy: disabled\n")

        f.write("// Source objects:\n")
        for name in scene_data.source_names:
            f.write(f"//   - {name}\n")

        f.write("// Mesh declarations:\n")
        for record in scene_data.object_records:
            if record.object_mesh_data is not None:
                f.write(f"//   - {record.export_name}\n")

        f.write("// Material declarations:\n")
        wrote_material = False
        for record in scene_data.object_records:
            if record.material_data is not None:
                f.write(f"//   - {record.material_data.export_name}\n")
                wrote_material = True
        if not wrote_material:
            f.write("//   - (none)\n")

        f.write("// Part object wrappers:\n")
        for record in scene_data.object_records:
            if record.object_mesh_data is not None:
                f.write(f"//   - {record.export_name}_OBJECT\n")

        f.write("// Final asset declaration:\n")
        f.write(f"//   - {scene_data.asset_export_name}\n")
        f.write("\n")

    @staticmethod
    def _write_mesh_declarations(
        f: TextIO,
        scene_data: SceneExportData,
        include_comments: bool = True,
    ) -> None:
        if include_comments:
            f.write("// ------------------------------------------------------------\n")
            f.write("// Mesh declarations\n")
            f.write("// ------------------------------------------------------------\n")

        for record in scene_data.object_records:
            if record.object_mesh_data is None:
                continue

            MeshDeclarationWriter.write_object_mesh_declaration(
                f,
                record.export_name,
                record.object_mesh_data,
            )
            f.write("\n")

    @staticmethod
    def _write_material_declarations(
        f: TextIO,
        scene_data: SceneExportData,
        include_comments: bool = True,
    ) -> None:
        materials: list[MaterialData] = [
            record.material_data
            for record in scene_data.object_records
            if record.material_data is not None
        ]
        MaterialWriter.write_material_declarations(
            f,
            materials,
            include_comments=include_comments,
        )

    @staticmethod
    def _write_debug_helpers(f: TextIO, scene_data: SceneExportData) -> None:
        if not scene_data.export_options.emit_debug_helpers:
            return

        wrote_any = False

        for record in scene_data.object_records:
            object_mesh_data = record.object_mesh_data
            if object_mesh_data is None:
                continue

            if not object_mesh_data.uvs or not object_mesh_data.uv_indices:
                continue

            if not wrote_any and scene_data.export_options.include_comments:
                f.write("// ------------------------------------------------------------\n")
                f.write("// Built-in UV debug helpers\n")
                f.write("// ------------------------------------------------------------\n")
                f.write("// Usage examples:\n")
                f.write("//\n")
                f.write("// object {\n")
                f.write("//     OBJ_Part_OBJECT\n")
                f.write("//     texture { OBJ_Part_UV_DEBUG_TEXTURE }\n")
                f.write("// }\n")
                f.write("//\n")
                f.write("// object {\n")
                f.write("//     OBJ_Part_OBJECT\n")
                f.write('//     texture { OBJ_Part_UV_IMAGE_TEXTURE("/absolute/path/to/uv_debug.png") }\n')
                f.write("// }\n")
                f.write("//\n")
                f.write("// object {\n")
                f.write("//     OBJ_Part_OBJECT\n")
                f.write("//     texture { OBJ_Part_UV_IMAGE_TEXTURE_AUTO }\n")
                f.write("// }\n")
                f.write("//\n")
                wrote_any = True

            auto_image_path = None
            if record.material_data is not None and record.material_data.image_texture is not None:
                image_data = record.material_data.image_texture
                auto_image_path = (
                    image_data.filepath_resolved
                    or image_data.filepath_raw
                    or image_data.image_name
                )

            DebugMaterialWriter.write_debug_block_for_name(
                f,
                record.export_name,
                auto_image_path=auto_image_path,
                include_comments=scene_data.export_options.include_comments,
            )
            f.write("\n")


class DebugMaterialWriter:
    @staticmethod
    def write_debug_block(
        f: TextIO,
        mesh_data,
        include_comments: bool = True,
    ) -> None:
        DebugMaterialWriter.write_debug_block_for_name(
            f,
            mesh_data.export_name,
            include_comments=include_comments,
        )

    @staticmethod
    def write_debug_block_for_name(
        f: TextIO,
        export_name: str,
        auto_image_path: str | None = None,
        include_comments: bool = True,
    ) -> None:
        f.write(f"#declare {export_name}_UV_DEBUG_TEXTURE =\n")
        f.write("texture {\n")
        f.write("    uv_mapping\n")
        f.write("    pigment {\n")
        f.write("        gradient x\n")
        f.write("        color_map {\n")
        f.write("            [0.0 color rgb <1, 0, 0>]\n")
        f.write("            [0.5 color rgb <0, 1, 0>]\n")
        f.write("            [1.0 color rgb <0, 0, 1>]\n")
        f.write("        }\n")
        f.write("    }\n")
        f.write("    finish {\n")
        f.write("        ambient 1\n")
        f.write("        diffuse 0\n")
        f.write("        specular 0\n")
        f.write("        roughness 1\n")
        f.write("    }\n")
        f.write("}\n\n")

        f.write(f"#macro {export_name}_UV_IMAGE_TEXTURE(ImageFile)\n")
        f.write("texture {\n")
        f.write("    uv_mapping\n")
        f.write("    pigment {\n")
        f.write("        image_map {\n")
        f.write("            png ImageFile\n")
        f.write("            once\n")
        f.write("        }\n")
        f.write("        scale <1, -1, 1>\n")
        f.write("        rotate <0, 0, 180>\n")
        f.write("        translate <1, 0, 1>\n")
        f.write("    }\n")
        f.write("    finish {\n")
        f.write("        ambient 1\n")
        f.write("        diffuse 0\n")
        f.write("        specular 0\n")
        f.write("        roughness 1\n")
        f.write("    }\n")
        f.write("}\n")
        f.write("#end\n")

        if auto_image_path:
            escaped_path = DebugMaterialWriter._escape_pov_string(auto_image_path)
            image_type = DebugMaterialWriter._image_map_type_token(auto_image_path)

            f.write("\n")
            f.write(f"#declare {export_name}_UV_IMAGE_TEXTURE_AUTO = texture {{\n")
            f.write("    uv_mapping\n")
            f.write("    pigment {\n")
            f.write("        image_map {\n")
            f.write(f'            {image_type} "{escaped_path}"\n')
            f.write("            once\n")
            f.write("        }\n")
            f.write("        scale <1, -1, 1>\n")
            f.write("        rotate <0, 0, 180>\n")
            f.write("        translate <1, 0, 1>\n")
            f.write("    }\n")
            f.write("    finish {\n")
            f.write("        ambient 1\n")
            f.write("        diffuse 0\n")
            f.write("        specular 0\n")
            f.write("        roughness 1\n")
            f.write("    }\n")
            f.write("}\n")

    @staticmethod
    def _escape_pov_string(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _image_map_type_token(path_str: str) -> str:
        lower = path_str.lower()
        if lower.endswith(".png"):
            return "png"
        if lower.endswith(".jpg") or lower.endswith(".jpeg"):
            return "jpeg"
        if lower.endswith(".tga"):
            return "tga"
        if lower.endswith(".bmp"):
            return "bmp"
        if lower.endswith(".gif"):
            return "gif"
        if lower.endswith(".iff"):
            return "iff"
        if lower.endswith(".ppm") or lower.endswith(".pgm"):
            return "ppm"
        if lower.endswith(".tiff") or lower.endswith(".tif"):
            return "tiff"
        if lower.endswith(".exr"):
            return "exr"
        return "png"


class FileWriter:
    @staticmethod
    def ensure_parent_dir(filepath: Path) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)


class NamePolicy:
    @staticmethod
    def make_export_name(filepath: Path, source_names) -> str:
        stem = filepath.stem.strip()

        if stem:
            return NamePolicy.make_pov_identifier(stem)

        if len(source_names) == 1:
            return NamePolicy.make_pov_identifier(source_names[0])

        return "OBJ_asset"

    @staticmethod
    def make_part_export_name(
        asset_export_name: str,
        source_name: str,
        material_slot_index: int | None = None,
        material_name: str | None = None,
    ) -> str:
        asset_core = asset_export_name[4:] if asset_export_name.startswith("OBJ_") else asset_export_name
        base_name = f"{asset_core}_{source_name}"

        if material_slot_index is None:
            return NamePolicy.make_pov_identifier(base_name)

        material_label = NamePolicy._make_material_label(material_slot_index, material_name)
        return NamePolicy.make_pov_identifier(f"{base_name}_{material_label}")

    @staticmethod
    def _make_material_label(material_slot_index: int, material_name: str | None) -> str:
        slot_label = str(material_slot_index) if material_slot_index >= 0 else "INVALID"
        if material_name:
            cleaned = re.sub(r"\W", "_", material_name, flags=re.UNICODE).strip("_")
            if cleaned:
                return f"MAT_{slot_label}_{cleaned}"
        return f"MAT_{slot_label}_UNASSIGNED"

    @staticmethod
    def make_pov_identifier(name: str) -> str:
        cleaned = re.sub(r"\W+", "_", name, flags=re.UNICODE)
        cleaned = cleaned.strip("_")

        if not cleaned:
            cleaned = "mesh"

        if cleaned[0].isdigit():
            cleaned = f"_{cleaned}"

        return f"OBJ_{cleaned}"
