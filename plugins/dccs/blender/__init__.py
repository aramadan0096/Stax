# -*- coding: utf-8 -*-
"""
StaX Blender Addon
"""

bl_info = {
    "name": "StaX Asset Manager",
    "author": "StaX Team",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "location": "Window > StaX",
    "description": "Asset management system for VFX pipelines",
    "warning": "",
    "wiki_url": "",
    "category": "Pipeline",
}

import bpy
import sys
import os

# Ensure project root is in sys.path
current_dir = os.path.dirname(__file__)
stax_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
if stax_root not in sys.path:
    sys.path.insert(0, stax_root)

from . import panel

class STAX_OT_OpenPanel(bpy.types.Operator):
    """Open the StaX Asset Manager Panel"""
    bl_idname = "stax.open_panel"
    bl_label = "Open StaX"

    def execute(self, context):
        panel.show_stax_panel()
        return {'FINISHED'}

class STAX_OT_AddToLibrary(bpy.types.Operator):
    """Add selected objects to StaX Library"""
    bl_idname = "stax.add_to_library"
    bl_label = "Add to Library"

    def execute(self, context):
        panel.add_to_library()
        return {'FINISHED'}

class STAX_MT_Menu(bpy.types.Menu):
    bl_label = "StaX"
    bl_idname = "STAX_MT_Menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("stax.open_panel", text="Open Browser")
        layout.operator("stax.add_to_library", text="Add Selected to Library")

def draw_menu(self, context):
    self.layout.menu(STAX_MT_Menu.bl_idname)

classes = (
    STAX_OT_OpenPanel,
    STAX_OT_AddToLibrary,
    STAX_MT_Menu,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_editor_menus.append(draw_menu)

def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(draw_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
