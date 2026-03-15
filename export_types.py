from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple


Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]
Face3 = Tuple[int, int, int]
ColorRGB = Tuple[float, float, float]
Matrix4Rows = Tuple[
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
]


class TransformMode(str, Enum):
    """
    Controls how object transforms are represented in export output.

    BAKE_WORLD
        Preserve Phase 1 behavior: bake each object's world transform into
        exported vertex positions and transform normals into world space.

    EMIT_OBJECT_TRANSFORMS
        Reserved for Phase 2 transform-wrapper export. Geometry remains in
        object-local space and object transforms are emitted later in SDL.
    """

    BAKE_WORLD = "BAKE_WORLD"
    EMIT_OBJECT_TRANSFORMS = "EMIT_OBJECT_TRANSFORMS"


class CoordinateMode(str, Enum):
    """
    Reserved for the future Blender -> POV-Ray coordinate conversion layer.

    For Step 1, this remains a placeholder enum so later pipeline stages can
    depend on a stable option type without changing the data model again.
    """

    BLENDER_NATIVE = "BLENDER_NATIVE"
    BLENDER_TO_POV = "BLENDER_TO_POV"


@dataclass(frozen=True)
class ExportContext:
    """
    Runtime export context shared across the pipeline.

    filepath
        Final target path for the .pov export.
    """

    filepath: Path


@dataclass(frozen=True)
class ExportOptions:
    """
    Phase 2 top-level export configuration.

    This is intentionally richer than current Phase 1 needs so later phases can
    plug into a stable internal contract without repeatedly changing function
    signatures.

    Current Phase 1-compatible defaults preserve existing behavior.
    """

    transform_mode: TransformMode = TransformMode.BAKE_WORLD
    coordinate_mode: CoordinateMode = CoordinateMode.BLENDER_NATIVE
    export_materials: bool = False
    emit_debug_helpers: bool = True
    combine_objects: bool = True
    include_comments: bool = True


@dataclass(frozen=True)
class TransformData:
    """
    Canonical container for object transform data.

    Step 1 note:
    - The current pipeline does not yet use this structure.
    - It exists now so transform extraction and SDL emission can be added later
      without redesigning pipeline contracts.

    matrix_world_rows
        Blender object matrix in row-major tuple form, when captured.

    matrix_export_rows
        Export-space transform matrix after any future coordinate conversion.

    location / rotation_rows / scale
        Optional cached decomposed transform components for later writer use.

    is_identity
        Whether the transform is effectively identity in export space.
    """

    source_name: str
    matrix_world_rows: Optional[Matrix4Rows] = None
    matrix_export_rows: Optional[Matrix4Rows] = None
    location: Optional[Vec3] = None
    rotation_rows: Optional[Tuple[Vec3, Vec3, Vec3]] = None
    scale: Optional[Vec3] = None
    is_identity: bool = True


@dataclass(frozen=True)
class ImageTextureData:
    """
    Minimal description of an exported image texture reference.

    Step 1 note:
    - This is not used yet by the pipeline.
    - It will later hold image texture information extracted from a supported
      Principled BSDF graph.
    """

    source_name: str = ""
    image_name: str = ""
    filepath_raw: str = ""
    filepath_resolved: str = ""
    exists_on_disk: bool = False
    uses_uv_mapping: bool = True


@dataclass(frozen=True)
class MaterialData:
    """
    Minimal Phase 2 material extraction result.

    Step 1 note:
    - Not yet used by writer code.
    - Designed to support a deliberately narrow material exporter:
      Principled BSDF base color and optional image texture reference.
    """

    source_name: str
    export_name: str
    is_supported: bool = False
    uses_nodes: bool = False
    base_color: Optional[ColorRGB] = None
    image_texture: Optional[ImageTextureData] = None
    uses_uv_mapping: bool = False
    warning: str = ""


@dataclass(frozen=True)
class ObjectMeshData:
    """
    Geometry extracted for a single Blender object.

    This is the existing Phase 1 mesh payload and remains the geometry backbone
    of the exporter.
    """

    source_name: str
    vertices: List[Vec3]
    faces: List[Face3]
    normals: List[Vec3]
    normal_indices: List[Face3]
    uvs: List[Vec2]
    uv_indices: List[Face3]


@dataclass(frozen=True)
class MeshData:
    """
    Geometry payload written as a POV-Ray mesh2 declaration.

    In Phase 1 this represents the combined mesh export.
    In later Phase 2 steps it can also represent per-object mesh declarations.
    """

    source_names: List[str]
    export_name: str
    vertices: List[Vec3]
    faces: List[Face3]
    normals: List[Vec3]
    normal_indices: List[Face3]
    uvs: List[Vec2]
    uv_indices: List[Face3]


@dataclass(frozen=True)
class ObjectExportRecord:
    """
    Phase 2 per-object export record.

    This will eventually become the unit that ties together:
    - object identity
    - geometry
    - transform
    - material

    Step 1 note:
    - Present now for future pipeline refactors.
    - Not yet consumed by the exporter.
    """

    source_name: str
    export_name: str
    mesh_data: Optional[MeshData] = None
    object_mesh_data: Optional[ObjectMeshData] = None
    transform_data: Optional[TransformData] = None
    material_data: Optional[MaterialData] = None


@dataclass(frozen=True)
class SceneExportData:
    """
    Top-level structured export description for a full export operation.

    Step 1 note:
    - This is not yet required by the current pipeline output path.
    - It gives Phase 2 a stable container for later orchestration and writing.
    """

    export_context: ExportContext
    export_options: ExportOptions = field(default_factory=ExportOptions)
    object_records: List[ObjectExportRecord] = field(default_factory=list)
    combined_mesh_data: Optional[MeshData] = None
    source_names: List[str] = field(default_factory=list)
