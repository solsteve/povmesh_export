import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from . import pipeline


class EXPORT_SCENE_OT_povmesh(Operator, ExportHelper):
    """Export selected mesh object(s) to POV-Ray mesh2"""

    bl_idname = "export_scene.povmesh"
    bl_label = "POV-Ray Mesh2 (.pov)"
    bl_description = "Export selected mesh object(s) as a POV-Ray mesh2"
    bl_options = {"PRESET"}

    filename_ext = ".pov"

    filter_glob: StringProperty(
        default="*.pov",
        options={"HIDDEN"},
        maxlen=255,
    )

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
        default="BAKE_WORLD",
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

    @classmethod
    def poll(cls, context):
        selected = getattr(context, "selected_objects", None)

        if not selected:
            cls.poll_message_set("Select one or more mesh objects to export.")
            return False

        mesh_objects = [obj for obj in selected if obj.type == "MESH"]

        if not mesh_objects:
            cls.poll_message_set("No mesh object selected.")
            return False

        return True

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="Transform and Coordinates")
        box.prop(self, "transform_mode")
        box.prop(self, "coordinate_mode")

        box = layout.box()
        box.label(text="Output Options")
        box.prop(self, "emit_debug_helpers")
        box.prop(self, "include_comments")
        box.prop(self, "export_materials")

        box = layout.box()
        box.label(text="Mesh Aggregation")
        row = box.row()
        row.enabled = self.transform_mode == "BAKE_WORLD"
        row.prop(self, "combine_objects")

        if self.transform_mode == "EMIT_OBJECT_TRANSFORMS":
            warn = layout.box()
            warn.label(
                text="Per-object mesh declarations and wrapper transforms will be emitted.",
                icon="INFO",
            )

    def execute(self, context):
        try:
            result = pipeline.export_povmesh(
                context=context,
                filepath=self.filepath,
                transform_mode=self.transform_mode,
                coordinate_mode=self.coordinate_mode,
                export_materials=self.export_materials,
                emit_debug_helpers=self.emit_debug_helpers,
                combine_objects=self.combine_objects,
                include_comments=self.include_comments,
            )

            if result == {"FINISHED"}:
                self.report({"INFO"}, "POV-Ray mesh2 export completed.")
                return result

            self.report({"ERROR"}, "POV-Ray export failed.")
            return {"CANCELLED"}

        except pipeline.ExportError as exc:
            message = str(exc)
            self.report({"ERROR"}, message)
            print(f"[povmesh_export] {message}")
            return {"CANCELLED"}

        except Exception as exc:
            message = f"Unexpected exporter error: {exc}"
            self.report({"ERROR"}, message)
            print(f"[povmesh_export] {message}")
            return {"CANCELLED"}


def menu_func_export(self, context):
    self.layout.operator(
        EXPORT_SCENE_OT_povmesh.bl_idname,
        text="POV-Ray Mesh2 (.pov)",
    )


classes = (
    EXPORT_SCENE_OT_povmesh,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
