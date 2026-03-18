from __future__ import annotations

from typing import TextIO

from .export_types import SceneExportData, TransformData


class ObjectSceneWriter:
    """
    Writes per-object POV-Ray wrapper object declarations for emitted-transform mode.

    Phase 2 scope
    -------------
    - references per-object mesh declarations
    - emits matrix transforms
    - attaches minimal exported materials when available
    - does not place live objects into the scene
    """

    @staticmethod
    def write_object_declarations(
        f: TextIO,
        scene_data: SceneExportData,
        include_comments: bool = True,
    ) -> None:
        if include_comments:
            f.write("// ------------------------------------------------------------\n")
            f.write("// Object declarations\n")
            f.write("// ------------------------------------------------------------\n")

        for record in scene_data.object_records:
            if record.object_mesh_data is None:
                continue

            object_decl_name = f"{record.export_name}_OBJECT"

            f.write(f"#declare {object_decl_name} = object {{\n")
            f.write(f"    {record.export_name}\n")

            if record.material_data is not None:
                f.write(f"    texture {{ {record.material_data.export_name} }}\n")

            if record.transform_data is not None and not record.transform_data.is_identity:
                ObjectSceneWriter._write_matrix_transform(f, record.transform_data)

            f.write("}\n\n")

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
