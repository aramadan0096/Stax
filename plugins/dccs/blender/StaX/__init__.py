bl_info = {
    "name": "StaX (Blender native UI)",
    "author": "StaX / reimplementation",
    "version": (0, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > StaX",
    "description": "StaX library integration using Blender UI: export .abc/.glb, register in StaX DB, preview and import.",
    "category": "Import-Export",
}

import bpy
from . import prefs, db, operators, ui

classes = (
    prefs.StaxPreferences,
    ui.STAX_PT_panel,
    ui.STAX_UL_library,
    operators.STAX_OT_add_to_library,
    operators.STAX_OT_import_from_library,
    operators.STAX_OT_preview_toggle,
    operators.STAX_OT_cleanup_preview,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    prefs.register()
    db.register()

def unregister():
    operators.cleanup_preview_if_exists()
    db.unregister()
    prefs.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
