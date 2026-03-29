from __future__ import annotations

from typing import TextIO

from .export_types import SceneExportData, TransformData
from .material_policy import MaterialPolicy


class ObjectSceneWriter:
    @staticmethod
    def write_object_declarations(
        f: TextIO,
        scene_data: SceneExportData,
        include_comments: bool = True,
    ) -> None:
        if include_comments:
            f.write("// ------------------------------------------------------------\n")
            f.write("// Part object declarations\n")
            f.write("// ------------------------------------------------------------\n")

        for record in scene_data.object_records:
            if record.object_mesh_data is None:
                continue

            object_decl_name = f"{record.export_name}_OBJECT"
            f.write(f"#declare {object_decl_name} = object {{\n")
            f.write(f"    {record.export_name}\n")

            material = record.material_data
            if material is not None:
                material = MaterialPolicy.normalize(material, scene_data.export_options)
                f.write(f"    texture {{ {material.export_name}_MAT }}\n")

                if MaterialPolicy.should_emit_hollow(material):
                    f.write("    hollow\n")
                if MaterialPolicy.should_emit_interior(material):
                    f.write(f"    interior {{ ior {material.ior:.6f} }}\n")

            if record.transform_data is not None and not record.transform_data.is_identity:
                ObjectSceneWriter._write_matrix_transform(f, record.transform_data)

            f.write("}\n\n")

    @staticmethod
    def write_asset_declaration(
        f: TextIO,
        scene_data: SceneExportData,
        include_comments: bool = True,
    ) -> None:
        part_records = [
            record for record in scene_data.object_records if record.object_mesh_data is not None
        ]
        if not part_records:
            return

        asset_name = scene_data.asset_export_name
        if include_comments:
            f.write("// ------------------------------------------------------------\n")
            f.write("// Final asset declaration\n")
            f.write("// ------------------------------------------------------------\n")

        if len(part_records) == 1:
            part = part_records[0]
            f.write(f"#declare {asset_name} = object {{\n")
            f.write(f"    {part.export_name}_OBJECT\n")
            f.write("}\n")
            return

        f.write(f"#declare {asset_name} = union {{\n")
        for part in part_records:
            f.write("    object {\n")
            f.write(f"        {part.export_name}_OBJECT\n")
            f.write("    }\n")
        f.write("}\n")

    @staticmethod
    def _write_matrix_transform(f: TextIO, transform_data: TransformData) -> None:
        matrix_rows = transform_data.matrix_export_rows
        if matrix_rows is None:
            return

        a = matrix_rows[0][0]
        b = matrix_rows[1][0]
        c = matrix_rows[2][0]
        d = matrix_rows[0][1]
        e = matrix_rows[1][1]
        f2 = matrix_rows[2][1]
        g = matrix_rows[0][2]
        h = matrix_rows[1][2]
        i = matrix_rows[2][2]
        tx = matrix_rows[0][3]
        ty = matrix_rows[1][3]
        tz = matrix_rows[2][3]

        f.write(
            "    matrix <"
            f"{ObjectFormatters.float(a)}, {ObjectFormatters.float(b)}, {ObjectFormatters.float(c)}, "
            f"{ObjectFormatters.float(d)}, {ObjectFormatters.float(e)}, {ObjectFormatters.float(f2)}, "
            f"{ObjectFormatters.float(g)}, {ObjectFormatters.float(h)}, {ObjectFormatters.float(i)}, "
            f"{ObjectFormatters.float(tx)}, {ObjectFormatters.float(ty)}, {ObjectFormatters.float(tz)}"
            ">\n"
        )


class ObjectFormatters:
    @staticmethod
    def float(value: float) -> str:
        return f"{float(value):.9g}"
