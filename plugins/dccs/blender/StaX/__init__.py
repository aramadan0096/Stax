# -*- coding: utf-8 -*-
"""
StaX Blender Addon
"""

bl_info = {
    "name": "StaX Asset Manager",
    "author": "Ahmed Ramadan",
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

# Addon Preferences to set StaX Root
class StaXAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    stax_root_path: bpy.props.StringProperty(
        name="StaX Root Directory",
        subtype='DIR_PATH',
        default="",
        description="Path to the StaX installation root (containing src/ and dependency_bootstrap.py)"
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "stax_root_path")

def get_stax_root():
    # Try to get from preferences
    preferences = bpy.context.preferences.addons[__name__].preferences
    if preferences.stax_root_path:
        return preferences.stax_root_path
    
    # Fallback: Try relative path (for dev environment)
    current_dir = os.path.dirname(__file__)
    # Assuming structure: plugins/dccs/blender/StaX/__init__.py -> root is 4 levels up
    dev_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..', '..'))
    if os.path.exists(os.path.join(dev_root, 'dependency_bootstrap.py')):
        return dev_root
    
    return None

def ensure_stax_path():
    root = get_stax_root()
    if root and root not in sys.path:
        sys.path.insert(0, root)
    return root

class STAX_OT_OpenPanel(bpy.types.Operator):
    """Open the StaX Asset Manager Panel"""
    bl_idname = "stax.open_panel"
    bl_label = "Open StaX"

    def execute(self, context):
        root = ensure_stax_path()
        if not root:
            self.report({'ERROR'}, "StaX Root not found. Please configure in Addon Preferences.")
            return {'CANCELLED'}
            
        try:
            from . import panel
            panel.show_stax_panel()
        except ImportError as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Failed to load StaX panel: {e}")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error opening StaX: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}
            
        return {'FINISHED'}

class STAX_OT_AddToLibrary(bpy.types.Operator):
    """Add selected objects to StaX Library"""
    bl_idname = "stax.add_to_library"
    bl_label = "Add to Library"

    def execute(self, context):
        root = ensure_stax_path()
        if not root:
            self.report({'ERROR'}, "StaX Root not found. Please configure in Addon Preferences.")
            return {'CANCELLED'}

        try:
            from . import panel
            panel.add_to_library()
        except Exception as e:
            self.report({'ERROR'}, f"Error: {e}")
            return {'CANCELLED'}
            
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
    StaXAddonPreferences,
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
