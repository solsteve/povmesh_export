import bpy

bl_info = {
    "name": "POV-Ray Mesh2 Exporter",
    "author": "Stephen Soliday",
    "version": (0, 1, 0),
    "blender": (5, 0, 0),
    "location": "File > Export",
    "description": "Export Blender meshes to POV-Ray mesh2 format",
    "category": "Import-Export",
}

from . import export_operator
from . import properties


def register():
    export_operator.register()
    properties.register()


def unregister():
    properties.unregister()
    export_operator.unregister()


if __name__ == "__main__":
    register()
