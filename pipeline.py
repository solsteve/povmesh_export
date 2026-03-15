from __future__ import annotations

import re
from pathlib import Path
from typing import List, Sequence, TextIO

from .coordinate_policy import CoordinatePolicy
from .export_types import (
    ExportContext,
    ExportOptions,
    CoordinateMode,
    Face3,
    MeshData,
    ObjectExportRecord,
    ObjectMeshData,
    SceneExportData,
    TransformMode,
    Vec2,
    Vec3,
)
from .transform_extractor import TransformExtractor
from .writers_mesh import MeshDeclarationWriter
from .writers_object import ObjectSceneWriter


class ExportError(Exception):
    """Raised for expected exporter failures that should be shown to the user."""

def export_povmesh(
    context,
    filepath,
    transform_mode="BAKE_WORLD",
    coordinate_mode="BLENDER_NATIVE",
    export_materials=False,
    emit_debug_helpers=True,
    combine_objects=True,
    include_comments=True,
):
    """
    Export selected mesh objects to POV-Ray SDL.

    Phase 2 transform split
    -----------------------
    BAKE_WORLD
        - geometry is baked to world space
        - output is a single combined mesh2 declaration

    EMIT_OBJECT_TRANSFORMS
        - geometry remains object-local
        - one mesh declaration is emitted per object
        - one object wrapper is emitted per object with a matrix transform
    """
    try:
        export_ctx = ExportContext(filepath=Path(filepath))
        export_options = ExportOptions(
            transform_mode=TransformMode(transform_mode),
            coordinate_mode=CoordinateMode(coordinate_mode),
            export_materials=bool(export_materials),
            emit_debug_helpers=bool(emit_debug_helpers),
            combine_objects=bool(combine_objects),
            include_comments=bool(include_comments),
        )

        objects = MeshCollector.get_selected_mesh_objects(context)

        if TransformExtractor.uses_emitted_object_transforms(export_options):
            scene_data = MeshExtractor.extract_scene_data_for_transform_export(
                context,
                objects,
                export_ctx,
                export_options,
            )
            FileWriter.ensure_parent_dir(export_ctx.filepath)
            SceneWriter.write_scene_file(export_ctx.filepath, scene_data)
            print(
                "[povmesh_export] Exported "
                f"{len(scene_data.source_names)} object(s) to '{export_ctx.filepath}' "
                "using emitted object transforms"
            )
            return {"FINISHED"}

        mesh_data = MeshExtractor.extract_combined_mesh(
            context,
            objects,
            export_ctx,
            export_options,
        )

        FileWriter.ensure_parent_dir(export_ctx.filepath)
        Mesh2Writer.write_file(export_ctx.filepath, mesh_data, export_options)

        print(
            "[povmesh_export] Exported "
            f"{len(mesh_data.source_names)} object(s) to '{export_ctx.filepath}' using baked world transforms"
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
    def extract_combined_mesh(
        context,
        objects,
        export_ctx: ExportContext,
        export_options: ExportOptions,
    ) -> MeshData:
        """
        Build the Phase 1-compatible combined mesh payload.

        This path is only valid for baked world-transform export.
        """
        if export_options.transform_mode != TransformMode.BAKE_WORLD:
            raise ExportError(
                "Combined mesh export currently requires TransformMode.BAKE_WORLD."
            )

        combined_vertices: List[Vec3] = []
        combined_faces: List[Face3] = []
        combined_normals: List[Vec3] = []
        combined_normal_indices: List[Face3] = []
        combined_uvs: List[Vec2] = []
        combined_uv_indices: List[Face3] = []
        source_names: List[str] = []

        for obj in objects:
            obj_mesh = MeshExtractor._extract_single_object_mesh(
                context,
                obj,
                export_options,
            )

            if not obj_mesh.faces:
                continue

            vertex_offset = len(combined_vertices)
            uv_offset = len(combined_uvs)

            combined_vertices.extend(obj_mesh.vertices)
            combined_faces.extend(
                FaceIndexBuilder.offset_faces(obj_mesh.faces, vertex_offset)
            )

            combined_normals.extend(obj_mesh.normals)
            combined_normal_indices.extend(
                FaceIndexBuilder.offset_faces(obj_mesh.normal_indices, vertex_offset)
            )

            if obj_mesh.uvs and obj_mesh.uv_indices:
                combined_uvs.extend(obj_mesh.uvs)
                combined_uv_indices.extend(
                    FaceIndexBuilder.offset_faces(obj_mesh.uv_indices, uv_offset)
                )

            source_names.append(obj_mesh.source_name)

        if not source_names:
            raise ExportError("Selected mesh objects contained no exportable faces.")

        export_name = NamePolicy.make_export_name(
            export_ctx.filepath,
            source_names,
        )

        return MeshData(
            source_names=source_names,
            export_name=export_name,
            vertices=combined_vertices,
            faces=combined_faces,
            normals=combined_normals,
            normal_indices=combined_normal_indices,
            uvs=combined_uvs,
            uv_indices=combined_uv_indices,
        )

    @staticmethod
    def extract_scene_data_for_transform_export(
        context,
        objects,
        export_ctx: ExportContext,
        export_options: ExportOptions,
    ) -> SceneExportData:
        """
        Build per-object scene export records for emitted-transform mode.
        """
        if export_options.transform_mode != TransformMode.EMIT_OBJECT_TRANSFORMS:
            raise ExportError(
                "Scene-data transform export path requires TransformMode.EMIT_OBJECT_TRANSFORMS."
            )

        object_records: List[ObjectExportRecord] = []
        source_names: List[str] = []

        for obj in objects:
            transform_data = TransformExtractor.extract_transform_data(obj, export_options)
            object_mesh_data = MeshExtractor._extract_single_object_mesh(
                context,
                obj,
                export_options,
            )

            if not object_mesh_data.faces:
                continue

            source_names.append(obj.name)
            object_records.append(
                ObjectExportRecord(
                    source_name=obj.name,
                    export_name=NamePolicy.make_object_export_name(obj.name),
                    mesh_data=None,
                    object_mesh_data=object_mesh_data,
                    transform_data=transform_data,
                    material_data=None,
                )
            )

        if not object_records:
            raise ExportError("Selected mesh objects contained no exportable faces.")

        return SceneExportData(
            export_context=export_ctx,
            export_options=export_options,
            object_records=object_records,
            combined_mesh_data=None,
            source_names=source_names,
        )

    @staticmethod
    def _extract_single_object_mesh(context, obj, export_options: ExportOptions) -> ObjectMeshData:
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

            return ExpandedCornerBuilder.build_object_mesh_data(
                obj,
                mesh_eval,
                export_options,
            )

        finally:
            if mesh_eval is not None:
                obj_eval.to_mesh_clear()


class ExpandedCornerBuilder:
    @staticmethod
    def build_object_mesh_data(obj, mesh, export_options: ExportOptions) -> ObjectMeshData:
        point_matrix, normal_matrix = TransformExtractor.get_geometry_matrices(
            obj,
            export_options,
        )
        uv_layer = UVExtractor.get_active_render_uv_layer(mesh)

        vertices: List[Vec3] = []
        faces: List[Face3] = []
        normals: List[Vec3] = []
        normal_indices: List[Face3] = []
        uvs: List[Vec2] = []
        uv_indices: List[Face3] = []

        for tri in mesh.loop_triangles:
            if len(tri.loops) != 3:
                raise ExportError(
                    "Triangulation failed: encountered a non-triangle loop triangle."
                )

            face_corner_indices: List[int] = []
            uv_corner_indices: List[int] = []

            for loop_index in tri.loops:
                vertex_index = mesh.loops[loop_index].vertex_index
                vert = mesh.vertices[vertex_index]

                co_export_source = point_matrix @ vert.co
                co_export = CoordinatePolicy.convert_point(
                    (
                        float(co_export_source.x),
                        float(co_export_source.y),
                        float(co_export_source.z),
                    ),
                    export_options.coordinate_mode,
                )
                vertices.append(co_export)
                face_corner_indices.append(len(vertices) - 1)

                normal_export_source = normal_matrix @ vert.normal
                normal_export_source.normalize()
                normal_export = CoordinatePolicy.convert_normal(
                    (
                        float(normal_export_source.x),
                        float(normal_export_source.y),
                        float(normal_export_source.z),
                    ),
                    export_options.coordinate_mode,
                )
                normals.append(normal_export)

                if uv_layer is not None:
                    uv = uv_layer.data[loop_index].uv

                    # Flip U during export so users do not need
                    # scale <-1, 1, 1> in POV-Ray texture blocks.
                    u = 1.0 - float(uv.x)
                    v = float(uv.y)

                    uvs.append((u, v))
                    uv_corner_indices.append(len(uvs) - 1)

            if len(face_corner_indices) != 3:
                raise ExportError(
                    "Expanded corner export failed: expected 3 corners per triangle."
                )

            face = (
                face_corner_indices[0],
                face_corner_indices[1],
                face_corner_indices[2],
            )
            faces.append(face)
            normal_indices.append(face)

            if uv_layer is not None:
                if len(uv_corner_indices) != 3:
                    raise ExportError(
                        "UV extraction failed: expected 3 UV corners per triangle."
                    )

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


class FaceIndexBuilder:
    @staticmethod
    def offset_faces(faces: Sequence[Face3], index_offset: int) -> List[Face3]:
        return [
            (
                face[0] + index_offset,
                face[1] + index_offset,
                face[2] + index_offset,
            )
            for face in faces
        ]


class Mesh2Writer:
    @staticmethod
    def write_file(
        filepath: Path,
        mesh_data: MeshData,
        export_options: ExportOptions,
    ) -> None:
        with open(filepath, "w", encoding="utf-8", newline="\n") as f:
            Mesh2Writer._write_header(f, mesh_data, export_options)
            MeshDeclarationWriter.write_mesh_declaration(
                f,
                mesh_data.export_name,
                mesh_data,
            )
            f.write("\n")
            if export_options.emit_debug_helpers:
                DebugMaterialWriter.write_debug_block(f, mesh_data)

    @staticmethod
    def _write_header(
        f: TextIO,
        mesh_data: MeshData,
        export_options: ExportOptions,
    ) -> None:
        policy_info = CoordinatePolicy.get_info(export_options.coordinate_mode)

        f.write("// POV-Ray mesh2 export\n")
        f.write("// Generated by Blender add-on: POV-Ray Mesh2 Exporter\n")
        f.write("// Export mode: combined selected mesh objects\n")
        f.write("// Geometry policy: expanded per-triangle-corner export\n")

        if export_options.transform_mode == TransformMode.BAKE_WORLD:
            f.write(
                "// Transform policy: each object's world transform baked into vertex positions\n"
            )
            f.write("// Normal policy: vertex normals transformed to world space\n")
        else:
            f.write(
                "// Transform policy: object-local geometry with deferred wrapper transforms\n"
            )
            f.write("// Normal policy: object-local vertex normals\n")

        f.write(f"// Coordinate policy: {policy_info.short_label}\n")
        f.write(f"// Coordinate policy detail: {policy_info.description}\n")

        if mesh_data.uvs and mesh_data.uv_indices:
            f.write("// UV policy: active render UV map exported per triangle corner\n")
            f.write(
                "// UV convention: U flipped during export for direct POV-Ray image_map use\n"
            )
        else:
            f.write("// UV policy: no active render UV map found\n")

        f.write("// Source objects:\n")
        for name in mesh_data.source_names:
            f.write(f"//   - {name}\n")
        f.write("\n")


class SceneWriter:
    @staticmethod
    def write_scene_file(filepath: Path, scene_data: SceneExportData) -> None:
        with open(filepath, "w", encoding="utf-8", newline="\n") as f:
            SceneWriter._write_header(f, scene_data)
            SceneWriter._write_mesh_declarations(f, scene_data)
            f.write("\n")
            SceneWriter._write_debug_helpers(f, scene_data)
            f.write("\n")
            ObjectSceneWriter.write_object_declarations(f, scene_data)

    @staticmethod
    def _write_header(f: TextIO, scene_data: SceneExportData) -> None:
        policy_info = CoordinatePolicy.get_info(scene_data.export_options.coordinate_mode)

        f.write("// POV-Ray mesh2 export\n")
        f.write("// Generated by Blender add-on: POV-Ray Mesh2 Exporter\n")
        f.write("// Export mode: per-object mesh declarations with emitted object transforms\n")
        f.write("// Geometry policy: expanded per-triangle-corner export\n")
        f.write("// Transform policy: object-local geometry with wrapper transforms emitted in SDL\n")
        f.write("// Normal policy: object-local vertex normals\n")
        f.write(f"// Coordinate policy: {policy_info.short_label}\n")
        f.write(f"// Coordinate policy detail: {policy_info.description}\n")
        f.write("// Source objects:\n")
        for name in scene_data.source_names:
            f.write(f"//   - {name}\n")
        f.write("\n")

    @staticmethod
    def _write_mesh_declarations(f: TextIO, scene_data: SceneExportData) -> None:
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

            if not wrote_any:
                f.write("// ------------------------------------------------------------\n")
                f.write("// Built-in UV debug helpers\n")
                f.write("// ------------------------------------------------------------\n")
                f.write("// Usage examples:\n")
                f.write("//\n")
                f.write("// object {\n")
                f.write("//     OBJ_Name_OBJECT\n")
                f.write("//     texture { OBJ_Name_UV_DEBUG_TEXTURE }\n")
                f.write("// }\n")
                f.write("//\n")
                f.write("// object {\n")
                f.write('//     OBJ_Name_OBJECT\n')
                f.write('//     texture { OBJ_Name_UV_IMAGE_TEXTURE("uv_debug.png") }\n')
                f.write("// }\n")
                f.write("//\n")
                wrote_any = True

            DebugMaterialWriter.write_debug_block_for_name(f, record.export_name)
            f.write("\n")


class DebugMaterialWriter:
    @staticmethod
    def write_debug_block(f: TextIO, mesh_data: MeshData) -> None:
        DebugMaterialWriter.write_debug_block_for_name(f, mesh_data.export_name)

    @staticmethod
    def write_debug_block_for_name(f: TextIO, export_name: str) -> None:
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
        f.write("    }\n")
        f.write("    finish {\n")
        f.write("        ambient 1\n")
        f.write("        diffuse 0\n")
        f.write("        specular 0\n")
        f.write("        roughness 1\n")
        f.write("    }\n")
        f.write("}\n")
        f.write("#end\n")


class FileWriter:
    @staticmethod
    def ensure_parent_dir(filepath: Path) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)


class NamePolicy:
    @staticmethod
    def make_export_name(filepath: Path, source_names: Sequence[str]) -> str:
        stem = filepath.stem.strip()

        if stem:
            return NamePolicy.make_pov_identifier(stem)

        if len(source_names) == 1:
            return NamePolicy.make_pov_identifier(source_names[0])

        return "OBJ_mesh"

    @staticmethod
    def make_object_export_name(source_name: str) -> str:
        return NamePolicy.make_pov_identifier(source_name)

    @staticmethod
    def make_pov_identifier(name: str) -> str:
        cleaned = re.sub(r"\W+", "_", name, flags=re.UNICODE)
        cleaned = cleaned.strip("_")

        if not cleaned:
            cleaned = "mesh"

        if cleaned[0].isdigit():
            cleaned = f"_{cleaned}"

        return f"OBJ_{cleaned}"
