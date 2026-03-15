from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, TextIO, Tuple


Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]
Face3 = Tuple[int, int, int]


@dataclass(frozen=True)
class ExportContext:
    filepath: Path


@dataclass(frozen=True)
class ObjectMeshData:
    source_name: str
    vertices: List[Vec3]
    faces: List[Face3]
    normals: List[Vec3]
    normal_indices: List[Face3]
    uvs: List[Vec2]
    uv_indices: List[Face3]


@dataclass(frozen=True)
class MeshData:
    source_names: List[str]
    export_name: str
    vertices: List[Vec3]
    faces: List[Face3]
    normals: List[Vec3]
    normal_indices: List[Face3]
    uvs: List[Vec2]
    uv_indices: List[Face3]


class ExportError(Exception):
    """Raised for expected exporter failures that should be shown to the user."""


def export_povmesh(context, filepath):
    """
    Export one or more selected mesh objects as a single POV-Ray mesh2.

    Current strategy:
    - deterministic object ordering
    - evaluated mesh export
    - Blender loop_triangles as the authoritative triangle source
    - expanded per-triangle-corner export:
        * one vertex per triangle corner
        * one normal per triangle corner
        * one UV per triangle corner
      so face_indices, normal_indices, and uv_indices are identical
    - object world transform baked into vertex positions
    - vertex normals transformed to world space
    - active render UV map exported when present
    - U is flipped during export so POV-Ray image_map usage needs no texture scale hack
    - emits optional debug SDL helpers for UV diagnosis
    """
    try:
        export_ctx = ExportContext(filepath=Path(filepath))

        objects = MeshCollector.get_selected_mesh_objects(context)
        mesh_data = MeshExtractor.extract_combined_mesh(context, objects, export_ctx)

        FileWriter.ensure_parent_dir(export_ctx.filepath)
        Mesh2Writer.write_file(export_ctx.filepath, mesh_data)

        print(
            "[povmesh_export] Exported "
            f"{len(mesh_data.source_names)} object(s) to '{export_ctx.filepath}'"
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
    ) -> MeshData:
        combined_vertices: List[Vec3] = []
        combined_faces: List[Face3] = []
        combined_normals: List[Vec3] = []
        combined_normal_indices: List[Face3] = []
        combined_uvs: List[Vec2] = []
        combined_uv_indices: List[Face3] = []
        source_names: List[str] = []

        for obj in objects:
            obj_mesh = MeshExtractor._extract_single_object_mesh(context, obj)

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
    def _extract_single_object_mesh(context, obj) -> ObjectMeshData:
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

            return ExpandedCornerBuilder.build_object_mesh_data(obj, mesh_eval)

        finally:
            if mesh_eval is not None:
                obj_eval.to_mesh_clear()


class ExpandedCornerBuilder:
    @staticmethod
    def build_object_mesh_data(obj, mesh) -> ObjectMeshData:
        world_matrix = obj.matrix_world.copy()
        normal_matrix = obj.matrix_world.to_3x3().inverted_safe().transposed()
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

                co_world = world_matrix @ vert.co
                vertices.append((co_world.x, co_world.y, co_world.z))
                face_corner_indices.append(len(vertices) - 1)

                normal_world = normal_matrix @ vert.normal
                normal_world.normalize()
                normals.append((normal_world.x, normal_world.y, normal_world.z))

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
    def write_file(filepath: Path, mesh_data: MeshData) -> None:
        with open(filepath, "w", encoding="utf-8", newline="\n") as f:
            Mesh2Writer._write_header(f, mesh_data)
            Mesh2Writer._write_mesh2_block(f, mesh_data)
            f.write("\n")
            DebugMaterialWriter.write_debug_block(f, mesh_data)

    @staticmethod
    def _write_header(f: TextIO, mesh_data: MeshData) -> None:
        f.write("// POV-Ray mesh2 export\n")
        f.write("// Generated by Blender add-on: POV-Ray Mesh2 Exporter\n")
        f.write("// Export mode: combined selected mesh objects\n")
        f.write("// Geometry policy: expanded per-triangle-corner export\n")
        f.write(
            "// Transform policy: each object's world transform baked into vertex positions\n"
        )
        f.write("// Normal policy: vertex normals transformed to world space\n")
        if mesh_data.uvs and mesh_data.uv_indices:
            f.write("// UV policy: active render UV map exported per triangle corner\n")
            f.write("// UV convention: U flipped during export for direct POV-Ray image_map use\n")
        else:
            f.write("// UV policy: no active render UV map found\n")
        f.write("// Source objects:\n")
        for name in mesh_data.source_names:
            f.write(f"//   - {name}\n")
        f.write("\n")

    @staticmethod
    def _write_mesh2_block(f: TextIO, mesh_data: MeshData) -> None:
        f.write(f"#declare {mesh_data.export_name} = mesh2 {{\n")
        Mesh2Writer._write_vertex_vectors(f, mesh_data.vertices)
        f.write("\n")
        Mesh2Writer._write_normal_vectors(f, mesh_data.normals)

        if mesh_data.uvs and mesh_data.uv_indices:
            f.write("\n")
            Mesh2Writer._write_uv_vectors(f, mesh_data.uvs)

        f.write("\n")
        Mesh2Writer._write_face_indices(f, mesh_data.faces)
        f.write("\n")
        Mesh2Writer._write_normal_indices(f, mesh_data.normal_indices)

        if mesh_data.uvs and mesh_data.uv_indices:
            f.write("\n")
            Mesh2Writer._write_uv_indices(f, mesh_data.uv_indices)

        f.write("}\n")

    @staticmethod
    def _write_vertex_vectors(f: TextIO, vertices: Sequence[Vec3]) -> None:
        f.write(f"    vertex_vectors {{ {len(vertices)},\n")
        for index, vert in enumerate(vertices):
            suffix = "," if index < len(vertices) - 1 else ""
            f.write(f"        {Formatters.vec3(vert)}{suffix}\n")
        f.write("    }\n")

    @staticmethod
    def _write_normal_vectors(f: TextIO, normals: Sequence[Vec3]) -> None:
        f.write(f"    normal_vectors {{ {len(normals)},\n")
        for index, normal in enumerate(normals):
            suffix = "," if index < len(normals) - 1 else ""
            f.write(f"        {Formatters.vec3(normal)}{suffix}\n")
        f.write("    }\n")

    @staticmethod
    def _write_uv_vectors(f: TextIO, uvs: Sequence[Vec2]) -> None:
        f.write(f"    uv_vectors {{ {len(uvs)},\n")
        for index, uv in enumerate(uvs):
            suffix = "," if index < len(uvs) - 1 else ""
            f.write(f"        {Formatters.vec2(uv)}{suffix}\n")
        f.write("    }\n")

    @staticmethod
    def _write_face_indices(f: TextIO, faces: Sequence[Face3]) -> None:
        f.write(f"    face_indices {{ {len(faces)},\n")
        for index, face in enumerate(faces):
            suffix = "," if index < len(faces) - 1 else ""
            f.write(f"        <{face[0]}, {face[1]}, {face[2]}>{suffix}\n")
        f.write("    }\n")

    @staticmethod
    def _write_normal_indices(f: TextIO, normal_indices: Sequence[Face3]) -> None:
        f.write(f"    normal_indices {{ {len(normal_indices)},\n")
        for index, face in enumerate(normal_indices):
            suffix = "," if index < len(normal_indices) - 1 else ""
            f.write(f"        <{face[0]}, {face[1]}, {face[2]}>{suffix}\n")
        f.write("    }\n")

    @staticmethod
    def _write_uv_indices(f: TextIO, uv_indices: Sequence[Face3]) -> None:
        f.write(f"    uv_indices {{ {len(uv_indices)},\n")
        for index, face in enumerate(uv_indices):
            suffix = "," if index < len(uv_indices) - 1 else ""
            f.write(f"        <{face[0]}, {face[1]}, {face[2]}>{suffix}\n")
        f.write("    }\n")


class DebugMaterialWriter:
    @staticmethod
    def write_debug_block(f: TextIO, mesh_data: MeshData) -> None:
        f.write("// ------------------------------------------------------------\n")
        f.write("// Built-in UV debug helpers\n")
        f.write("// ------------------------------------------------------------\n")
        f.write("// Usage examples:\n")
        f.write("//\n")
        f.write("// 1) UV gradient debug:\n")
        f.write(f"// object {{ {mesh_data.export_name} texture {{ {mesh_data.export_name}_UV_DEBUG_TEXTURE }} }}\n")
        f.write("//\n")
        f.write("// 2) UV image debug:\n")
        f.write("// Replace \"uv_debug.png\" with your image file.\n")
        f.write(f"// object {{ {mesh_data.export_name} texture {{ {mesh_data.export_name}_UV_IMAGE_TEXTURE(\"uv_debug.png\") }} }}\n")
        f.write("//\n")

        f.write(f"#declare {mesh_data.export_name}_UV_DEBUG_TEXTURE =\n")
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

        f.write(f"#macro {mesh_data.export_name}_UV_IMAGE_TEXTURE(ImageFile)\n")
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
    def make_pov_identifier(name: str) -> str:
        cleaned = re.sub(r"\W+", "_", name, flags=re.UNICODE)
        cleaned = cleaned.strip("_")

        if not cleaned:
            cleaned = "mesh"

        if cleaned[0].isdigit():
            cleaned = f"_{cleaned}"

        return f"OBJ_{cleaned}"


class Formatters:
    @staticmethod
    def vec2(vec: Vec2) -> str:
        return f"<{Formatters.float(vec[0])}, {Formatters.float(vec[1])}>"

    @staticmethod
    def vec3(vec: Vec3) -> str:
        return (
            f"<{Formatters.float(vec[0])}, "
            f"{Formatters.float(vec[1])}, "
            f"{Formatters.float(vec[2])}>"
        )

    @staticmethod
    def float(value: float) -> str:
        return f"{float(value):.9g}"
