import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty
from bpy.types import Operator

from . import pipeline


class EXPORT_SCENE_OT_povmesh(Operator, ExportHelper):
    """Export selected mesh object(s) to POV-Ray mesh2"""

    bl_idname = "export_scene.povmesh"
    bl_label = "POV-Ray Mesh2 (.pov)"
    bl_description = "Export selected mesh object(s) as a combined POV-Ray mesh2"
    bl_options = {"PRESET"}

    filename_ext = ".pov"

    filter_glob: StringProperty(
        default="*.pov",
        options={"HIDDEN"},
        maxlen=255,
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

    def execute(self, context):
        try:
            result = pipeline.export_povmesh(context, self.filepath)

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
