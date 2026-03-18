import bpy
from bpy.props import BoolProperty, EnumProperty
from bpy.types import PropertyGroup


class POVMeshExportProperties(PropertyGroup):
    transform_mode: EnumProperty(
        name="Transform Mode",
        description=(
            "Choose whether object transforms are baked into exported vertex "
            "coordinates or emitted as object wrapper transforms in POV-Ray SDL"
        ),
        items=(
            (
                "BAKE_WORLD",
                "Bake World Transform",
                "Bake each object's world transform into vertex positions and normals",
            ),
            (
                "EMIT_OBJECT_TRANSFORMS",
                "Emit Object Transforms",
                "Export object-local mesh data and emit a wrapper transform per object",
            ),
        ),
        default="EMIT_OBJECT_TRANSFORMS",
    )

    coordinate_mode: EnumProperty(
        name="Coordinate Mode",
        description="Coordinate conversion policy for Blender to POV-Ray export",
        items=(
            (
                "BLENDER_NATIVE",
                "Blender Native",
                "Do not remap coordinates; preserve current Phase 1 coordinate behavior",
            ),
            (
                "BLENDER_TO_POV",
                "Blender to POV",
                "Apply the exporter coordinate conversion policy for POV-Ray space",
            ),
        ),
        default="BLENDER_NATIVE",
    )

    export_materials: BoolProperty(
        name="Export Materials",
        description="Reserved for Phase 2 material export",
        default=False,
    )

    emit_debug_helpers: BoolProperty(
        name="Emit UV Debug Helpers",
        description="Write built-in UV debug textures/macros into the exported SDL",
        default=True,
    )

    combine_objects: BoolProperty(
        name="Combine Objects",
        description=(
            "Combine selected objects into one mesh when using baked world transforms. "
            "Ignored for emitted object transform mode"
        ),
        default=True,
    )

    include_comments: BoolProperty(
        name="Include Comments",
        description="Write explanatory comments into the exported SDL",
        default=True,
    )


classes = (
    POVMeshExportProperties,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
