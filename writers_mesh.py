from __future__ import annotations

from typing import Sequence, TextIO

from .export_types import Face3, MeshData, ObjectMeshData, Vec2, Vec3


class MeshDeclarationWriter:
    """
    Writes raw POV-Ray mesh2 declarations.

    Responsibilities
    ----------------
    - write one combined mesh declaration
    - write one per-object mesh declaration
    - write only mesh2 geometry blocks
    - avoid object wrappers, transforms, or materials
    """

    @staticmethod
    def write_mesh_declaration(f: TextIO, export_name: str, mesh_data: MeshData) -> None:
        f.write(f"#declare {export_name} = mesh2 {{\n")
        MeshDeclarationWriter._write_vertex_vectors(f, mesh_data.vertices)
        f.write("\n")
        MeshDeclarationWriter._write_normal_vectors(f, mesh_data.normals)

        if mesh_data.uvs and mesh_data.uv_indices:
            f.write("\n")
            MeshDeclarationWriter._write_uv_vectors(f, mesh_data.uvs)

        f.write("\n")
        MeshDeclarationWriter._write_face_indices(f, mesh_data.faces)
        f.write("\n")
        MeshDeclarationWriter._write_normal_indices(f, mesh_data.normal_indices)

        if mesh_data.uvs and mesh_data.uv_indices:
            f.write("\n")
            MeshDeclarationWriter._write_uv_indices(f, mesh_data.uv_indices)

        f.write("}\n")

    @staticmethod
    def write_object_mesh_declaration(
        f: TextIO,
        export_name: str,
        object_mesh_data: ObjectMeshData,
    ) -> None:
        f.write(f"#declare {export_name} = mesh2 {{\n")
        MeshDeclarationWriter._write_vertex_vectors(f, object_mesh_data.vertices)
        f.write("\n")
        MeshDeclarationWriter._write_normal_vectors(f, object_mesh_data.normals)

        if object_mesh_data.uvs and object_mesh_data.uv_indices:
            f.write("\n")
            MeshDeclarationWriter._write_uv_vectors(f, object_mesh_data.uvs)

        f.write("\n")
        MeshDeclarationWriter._write_face_indices(f, object_mesh_data.faces)
        f.write("\n")
        MeshDeclarationWriter._write_normal_indices(f, object_mesh_data.normal_indices)

        if object_mesh_data.uvs and object_mesh_data.uv_indices:
            f.write("\n")
            MeshDeclarationWriter._write_uv_indices(f, object_mesh_data.uv_indices)

        f.write("}\n")

    @staticmethod
    def _write_vertex_vectors(f: TextIO, vertices: Sequence[Vec3]) -> None:
        f.write(f"    vertex_vectors {{ {len(vertices)},\n")
        for index, vert in enumerate(vertices):
            suffix = "," if index < len(vertices) - 1 else ""
            f.write(f"        {MeshFormatters.vec3(vert)}{suffix}\n")
        f.write("    }\n")

    @staticmethod
    def _write_normal_vectors(f: TextIO, normals: Sequence[Vec3]) -> None:
        f.write(f"    normal_vectors {{ {len(normals)},\n")
        for index, normal in enumerate(normals):
            suffix = "," if index < len(normals) - 1 else ""
            f.write(f"        {MeshFormatters.vec3(normal)}{suffix}\n")
        f.write("    }\n")

    @staticmethod
    def _write_uv_vectors(f: TextIO, uvs: Sequence[Vec2]) -> None:
        f.write(f"    uv_vectors {{ {len(uvs)},\n")
        for index, uv in enumerate(uvs):
            suffix = "," if index < len(uvs) - 1 else ""
            f.write(f"        {MeshFormatters.vec2(uv)}{suffix}\n")
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


class MeshFormatters:
    @staticmethod
    def vec2(vec: Vec2) -> str:
        return f"<{MeshFormatters.float(vec[0])}, {MeshFormatters.float(vec[1])}>"

    @staticmethod
    def vec3(vec: Vec3) -> str:
        return (
            f"<{MeshFormatters.float(vec[0])}, "
            f"{MeshFormatters.float(vec[1])}, "
            f"{MeshFormatters.float(vec[2])}>"
        )

    @staticmethod
    def float(value: float) -> str:
        return f"{float(value):.9g}"
