import bpy
from bpy.props import StringProperty
from bpy.types import AddonPreferences

addon_key = __name__.split('.')[0]

class StaxPreferences(AddonPreferences):
    bl_idname = addon_key

    repository_path: StringProperty(
        name="Repository Path",
        description="Root folder for StaX repository (must be writable). Inside it, 'mesh' and 'proxy' will be used.",
        default="",
        subtype='DIR_PATH'
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "repository_path")

def register():
    pass

def unregister():
    pass
