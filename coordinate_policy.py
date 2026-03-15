from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

from .export_types import CoordinateMode, Matrix4Rows, Vec3


@dataclass(frozen=True)
class CoordinatePolicyInfo:
    """
    Descriptive metadata for the active coordinate policy.

    This is intended for exporter comments, diagnostics, and future debugging.
    """

    mode: CoordinateMode
    short_label: str
    description: str


class CoordinatePolicy:
    """
    Authoritative Blender -> POV-Ray coordinate conversion layer.

    Phase 2 Step 2 goals:
    - centralize point/vector/normal/matrix conversion
    - keep the current exporter behavior unchanged by default
    - prepare for future object-transform export

    Notes
    -----
    BLENDER_NATIVE
        Pass-through mode. Preserves Phase 1 behavior exactly.

    BLENDER_TO_POV
        Enables a canonical axis remap intended for POV-Ray export space.
        The chosen mapping here is:

            Blender (x, y, z) -> POV (x, z, y)

        This is a pure basis remap with no sign flip.

        The important architectural point is not the exact mapping itself,
        but that *all* coordinate conversion now flows through one place.
        If the project later adopts a different final mapping, this file is the
        only place that should need to change.
    """

    @staticmethod
    def get_info(mode: CoordinateMode) -> CoordinatePolicyInfo:
        if mode == CoordinateMode.BLENDER_TO_POV:
            return CoordinatePolicyInfo(
                mode=mode,
                short_label="BLENDER_TO_POV",
                description="Blender basis remapped to POV export basis: <x, y, z> -> <x, z, y>",
            )

        return CoordinatePolicyInfo(
            mode=CoordinateMode.BLENDER_NATIVE,
            short_label="BLENDER_NATIVE",
            description="No coordinate conversion; preserves Blender-space export values",
        )

    @staticmethod
    def convert_point(vec: Vec3, mode: CoordinateMode) -> Vec3:
        """
        Convert a position vector.

        In this step, positions and directions share the same linear basis
        mapping. Translation handling becomes relevant later when full object
        transforms are emitted.
        """
        return CoordinatePolicy._convert_vec3(vec, mode)

    @staticmethod
    def convert_vector(vec: Vec3, mode: CoordinateMode) -> Vec3:
        """
        Convert a direction vector.
        """
        return CoordinatePolicy._convert_vec3(vec, mode)

    @staticmethod
    def convert_normal(vec: Vec3, mode: CoordinateMode) -> Vec3:
        """
        Convert a normal vector.

        For the currently supported policy mappings, the same basis remap is
        valid for normals because Step 2 does not yet emit object transforms or
        apply a distinct export-space normal matrix.
        """
        return CoordinatePolicy._convert_vec3(vec, mode)

    @staticmethod
    def convert_matrix_rows(matrix_rows: Matrix4Rows, mode: CoordinateMode) -> Matrix4Rows:
        """
        Convert a 4x4 matrix represented as row tuples.

        This is included now so later transform export work has a stable API.

        For BLENDER_NATIVE this is a pass-through.
        For BLENDER_TO_POV this performs basis-change remapping using:

            M_export = C * M_blender * C^-1

        where C is the coordinate conversion basis matrix.
        """
        if mode == CoordinateMode.BLENDER_NATIVE:
            return matrix_rows

        blender_matrix = CoordinatePolicy._rows_to_mutable_matrix(matrix_rows)
        basis = CoordinatePolicy._basis_matrix(mode)
        basis_inv = CoordinatePolicy._transpose_4x4(basis)  # permutation matrix inverse
        export_matrix = CoordinatePolicy._matmul_4x4(
            CoordinatePolicy._matmul_4x4(basis, blender_matrix),
            basis_inv,
        )
        return CoordinatePolicy._mutable_matrix_to_rows(export_matrix)

    @staticmethod
    def matrix_to_rows(matrix_like) -> Matrix4Rows:
        """
        Convert a Blender-style matrix or a nested iterable into Matrix4Rows.

        Accepted forms:
        - Blender mathutils.Matrix (4x4)
        - nested iterables of numeric values
        """
        rows = []
        for row in matrix_like:
            row_values = tuple(float(value) for value in row)
            if len(row_values) != 4:
                raise ValueError("Expected a 4x4 matrix when converting to Matrix4Rows.")
            rows.append(row_values)

        if len(rows) != 4:
            raise ValueError("Expected exactly 4 rows when converting to Matrix4Rows.")

        return (
            rows[0],
            rows[1],
            rows[2],
            rows[3],
        )

    @staticmethod
    def _convert_vec3(vec: Vec3, mode: CoordinateMode) -> Vec3:
        x, y, z = float(vec[0]), float(vec[1]), float(vec[2])

        if mode == CoordinateMode.BLENDER_TO_POV:
            return (x, z, y)

        return (x, y, z)

    @staticmethod
    def _basis_matrix(mode: CoordinateMode):
        """
        Return a 4x4 basis-conversion matrix C such that:

            v_export = C * v_blender

        using homogeneous coordinates.
        """
        if mode == CoordinateMode.BLENDER_TO_POV:
            return [
                [1.0, 0.0, 0.0, 0.0],  # x' = x
                [0.0, 0.0, 1.0, 0.0],  # y' = z
                [0.0, 1.0, 0.0, 0.0],  # z' = y
                [0.0, 0.0, 0.0, 1.0],
            ]

        return [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]

    @staticmethod
    def _rows_to_mutable_matrix(matrix_rows: Matrix4Rows):
        return [
            [float(matrix_rows[0][0]), float(matrix_rows[0][1]), float(matrix_rows[0][2]), float(matrix_rows[0][3])],
            [float(matrix_rows[1][0]), float(matrix_rows[1][1]), float(matrix_rows[1][2]), float(matrix_rows[1][3])],
            [float(matrix_rows[2][0]), float(matrix_rows[2][1]), float(matrix_rows[2][2]), float(matrix_rows[2][3])],
            [float(matrix_rows[3][0]), float(matrix_rows[3][1]), float(matrix_rows[3][2]), float(matrix_rows[3][3])],
        ]

    @staticmethod
    def _mutable_matrix_to_rows(matrix) -> Matrix4Rows:
        return (
            (float(matrix[0][0]), float(matrix[0][1]), float(matrix[0][2]), float(matrix[0][3])),
            (float(matrix[1][0]), float(matrix[1][1]), float(matrix[1][2]), float(matrix[1][3])),
            (float(matrix[2][0]), float(matrix[2][1]), float(matrix[2][2]), float(matrix[2][3])),
            (float(matrix[3][0]), float(matrix[3][1]), float(matrix[3][2]), float(matrix[3][3])),
        )

    @staticmethod
    def _transpose_4x4(matrix):
        return [
            [float(matrix[0][0]), float(matrix[1][0]), float(matrix[2][0]), float(matrix[3][0])],
            [float(matrix[0][1]), float(matrix[1][1]), float(matrix[2][1]), float(matrix[3][1])],
            [float(matrix[0][2]), float(matrix[1][2]), float(matrix[2][2]), float(matrix[3][2])],
            [float(matrix[0][3]), float(matrix[1][3]), float(matrix[2][3]), float(matrix[3][3])],
        ]

    @staticmethod
    def _matmul_4x4(a, b):
        result = [[0.0, 0.0, 0.0, 0.0] for _ in range(4)]
        for row in range(4):
            for col in range(4):
                result[row][col] = (
                    a[row][0] * b[0][col]
                    + a[row][1] * b[1][col]
                    + a[row][2] * b[2][col]
                    + a[row][3] * b[3][col]
                )
        return result
