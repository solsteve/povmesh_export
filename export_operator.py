import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from . import pipeline


class EXPORT_SCENE_OT_povmesh(Operator, ExportHelper):
    """Export selected mesh object(s) to POV-Ray mesh2"""

    bl_idname = "export_scene.povmesh"
    bl_label = "POV-Ray Mesh2 (.pov)"
    bl_description = "Export selected mesh object(s) as reusable POV-Ray mesh2 part declarations plus an assembled asset declaration"
    bl_options = {"PRESET"}

    filename_ext = ".pov"

    filter_glob: StringProperty(
        default="*.pov",
        options={"HIDDEN"},
        maxlen=255,
    )

    coordinate_mode: EnumProperty(
        name="Coordinate Mode",
        description="Coordinate conversion policy for Blender to POV-Ray export",
        items=(
            (
                "BLENDER_NATIVE",
                "Blender Native",
                "Do not remap coordinates; preserve Blender-space export values",
            ),
            (
                "BLENDER_TO_POV",
                "Blender to POV",
                "Apply the exporter coordinate conversion policy for POV-Ray space",
            ),
        ),
        default="BLENDER_TO_POV",
    )

    export_materials: BoolProperty(
        name="Export Materials",
        description="Export minimal supported materials per object",
        default=True,
    )

    emit_debug_helpers: BoolProperty(
        name="Emit UV Debug Helpers",
        description="Write built-in UV debug helpers per object",
        default=True,
    )

    include_comments: BoolProperty(
        name="Include Comments",
        description="Write explanatory comments into the exported SDL",
        default=True,
    )

    texture_path_mode: EnumProperty(
        name="Texture Path Mode",
        description="How texture file paths are written into the exported POV-Ray SDL",
        items=(
            ("ABSOLUTE", "Absolute", "Write absolute texture file paths"),
            ("RELATIVE", "Relative", "Write paths relative to the exported .pov file"),
            ("COPY",     "Copy",     "Copy texture assets beside the export and write relative paths"),
        ),
        default="RELATIVE",
    )

    copy_texture_assets: BoolProperty(
        name="Copy Texture Assets",
        description="Copy texture files into a subdirectory beside the exported .pov file",
        default=False,
    )

    texture_copy_subdir: StringProperty(
        name="Texture Subdirectory",
        description="Subdirectory used when copying texture assets",
        default="textures",
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
        box.label(text="Coordinates")
        box.prop(self, "coordinate_mode")

        box = layout.box()
        box.label(text="Output Options")
        box.prop(self, "export_materials")
        box.prop(self, "emit_debug_helpers")
        box.prop(self, "include_comments")
        box.prop(self, "texture_path_mode")
        box.prop(self, "copy_texture_assets")
        box.prop(self, "texture_copy_subdir")

        info = layout.box()
        info.label(text="Each selected mesh is exported as its own local-space part.", icon="INFO")
        info.label(text="If multiple meshes are selected, a final union asset is emitted.")

    def execute(self, context):
        try:
            result = pipeline.export_povmesh(
                context=context,
                filepath=self.filepath,
                coordinate_mode=self.coordinate_mode,
                export_materials=self.export_materials,
                emit_debug_helpers=self.emit_debug_helpers,
                include_comments=self.include_comments,
                texture_path_mode=self.texture_path_mode,
                copy_texture_assets=self.copy_texture_assets,
                texture_copy_subdir=self.texture_copy_subdir,
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
