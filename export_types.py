from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

print("[POV EXPORT DEBUG] export_types loaded from:", __file__)

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
    BAKE_WORLD = "BAKE_WORLD"
    EMIT_OBJECT_TRANSFORMS = "EMIT_OBJECT_TRANSFORMS"


class CoordinateMode(str, Enum):
    BLENDER_NATIVE = "BLENDER_NATIVE"
    BLENDER_TO_POV = "BLENDER_TO_POV"


@dataclass(frozen=True)
class ExportContext:
    filepath: Path


@dataclass(frozen=True)
class ExportOptions:
    transform_mode: TransformMode = TransformMode.EMIT_OBJECT_TRANSFORMS
    coordinate_mode: CoordinateMode = CoordinateMode.BLENDER_TO_POV
    export_materials: bool = True
    emit_debug_helpers: bool = True
    combine_objects: bool = False
    include_comments: bool = True


@dataclass(frozen=True)
class TransformData:
    source_name: str
    matrix_world_rows: Optional[Matrix4Rows] = None
    matrix_export_rows: Optional[Matrix4Rows] = None
    location: Optional[Vec3] = None
    rotation_rows: Optional[Tuple[Vec3, Vec3, Vec3]] = None
    scale: Optional[Vec3] = None
    is_identity: bool = True


@dataclass(frozen=True)
class ImageTextureData:
    source_name: str = ""
    image_name: str = ""
    filepath_raw: str = ""
    filepath_resolved: str = ""
    exists_on_disk: bool = False
    uses_uv_mapping: bool = True


@dataclass(frozen=True)
class MaterialData:
    source_name: str
    export_name: str
    is_supported: bool = False
    uses_nodes: bool = False
    base_color: Optional[ColorRGB] = None
    image_texture: Optional[ImageTextureData] = None
    uses_uv_mapping: bool = False
    warning: str = ""
    roughness: Optional[float] = None
    specular: Optional[float] = None
    metallic: Optional[float] = None

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


@dataclass(frozen=True)
class ObjectExportRecord:
    source_name: str
    export_name: str
    mesh_data: Optional[MeshData] = None
    object_mesh_data: Optional[ObjectMeshData] = None
    transform_data: Optional[TransformData] = None
    material_data: Optional[MaterialData] = None
    material_slot_index: Optional[int] = None
    source_material_name: str = ""

@dataclass(frozen=True)
class SceneExportData:
    export_context: ExportContext
    export_options: ExportOptions = field(default_factory=ExportOptions)
    object_records: List[ObjectExportRecord] = field(default_factory=list)
    combined_mesh_data: Optional[MeshData] = None
    source_names: List[str] = field(default_factory=list)
    asset_export_name: str = ""

