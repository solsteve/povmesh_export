from __future__ import annotations

from mathutils import Matrix

from .coordinate_policy import CoordinatePolicy
from .export_types import ExportOptions, TransformData, TransformMode


class TransformExtractor:
    """
    Transform-policy helper for the exporter.

    Responsibilities
    ----------------
    - define whether geometry is exported in baked world space or object-local space
    - expose the matrices needed by mesh extraction
    - capture object transform metadata for later wrapper-transform export

    Phase 2 status
    --------------
    BAKE_WORLD
        Fully supported now. Matches Phase 1 behavior.

    EMIT_OBJECT_TRANSFORMS
        Geometry extraction path is supported now:
        - mesh vertices remain in object-local space
        - normals remain in object-local space
        - transform metadata is captured for later object-wrapper SDL emission

        Final SDL writing for this mode is not implemented in this step.
    """

    @staticmethod
    def extract_transform_data(obj, export_options: ExportOptions) -> TransformData:
        """
        Build a canonical transform record for one Blender object.

        This data is not yet written to SDL in this step, but it is captured now
        so later object-wrapper export can reuse the same contract.
        """
        matrix_world_rows = CoordinatePolicy.matrix_to_rows(obj.matrix_world)
        matrix_export_rows = CoordinatePolicy.convert_matrix_rows(
            matrix_world_rows,
            export_options.coordinate_mode,
        )

        translation = obj.matrix_world.to_translation()
        location = CoordinatePolicy.convert_point(
            (translation.x, translation.y, translation.z),
            export_options.coordinate_mode,
        )

        scale = obj.matrix_world.to_scale()
        scale_vec = (float(scale.x), float(scale.y), float(scale.z))

        is_identity = TransformExtractor._is_identity_matrix_rows(matrix_export_rows)

        return TransformData(
            source_name=obj.name,
            matrix_world_rows=matrix_world_rows,
            matrix_export_rows=matrix_export_rows,
            location=location,
            rotation_rows=None,
            scale=scale_vec,
            is_identity=is_identity,
        )

    @staticmethod
    def get_geometry_matrices(obj, export_options: ExportOptions):
        """
        Return the matrices that mesh extraction should apply to geometry data.

        Returns
        -------
        point_matrix, normal_matrix

        BAKE_WORLD
            point_matrix  = obj.matrix_world
            normal_matrix = world-space normal matrix

        EMIT_OBJECT_TRANSFORMS
            point_matrix  = identity
            normal_matrix = identity

        The emitted-transform mode intentionally leaves geometry in local space.
        """
        if export_options.transform_mode == TransformMode.EMIT_OBJECT_TRANSFORMS:
            return Matrix.Identity(4), Matrix.Identity(3)

        point_matrix = obj.matrix_world.copy()
        normal_matrix = obj.matrix_world.to_3x3().inverted_safe().transposed()
        return point_matrix, normal_matrix

    @staticmethod
    def uses_baked_world_geometry(export_options: ExportOptions) -> bool:
        return export_options.transform_mode == TransformMode.BAKE_WORLD

    @staticmethod
    def uses_emitted_object_transforms(export_options: ExportOptions) -> bool:
        return export_options.transform_mode == TransformMode.EMIT_OBJECT_TRANSFORMS

    @staticmethod
    def _is_identity_matrix_rows(matrix_rows, epsilon: float = 1.0e-9) -> bool:
        identity = (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )

        for row_index in range(4):
            for col_index in range(4):
                if abs(float(matrix_rows[row_index][col_index]) - identity[row_index][col_index]) > epsilon:
                    return False
        return True
