# ui.py - StaX Blender UI (no circular imports)
import bpy
from bpy.types import Panel, UIList
from . import db

class STAX_UL_library(UIList):
    """Simple UIList to show library entries from stax_db.json"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # item is a dict from db.get_entries_as_list()
        name = item.get("name", "<no-name>")
        list_name = item.get("list", "")
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=name)
            row.label(text=f"({list_name})")
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=name)

class STAX_PT_panel(Panel):
    bl_label = "StaX"
    bl_idname = "STAX_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "StaX"

    def draw(self, context):
        layout = self.layout
        addon_key = __name__.split('.')[0]  # "StaX"
        repo_set = False
        addon = bpy.context.preferences.addons.get(addon_key)
        if addon:
            repo_set = bool(getattr(addon.preferences, "repository_path", ""))

        col = layout.column(align=True)
        col.label(text="Repository configured: " + ("Yes" if repo_set else "No"))
        col.operator("stax.add_to_library", text="Add to library (export .abc + .glb)")
        col.separator()
        col.label(text="Library")

        entries = db.get_entries_as_list()
        if entries:
            box = col.box()
            for e in entries:
                row = box.row(align=True)
                row.label(text=e.get("name", "<no-name>"))
                row.label(text=e.get("list", ""))
                # Use operator idnames (no direct imports) to avoid circular import
                op_imp = row.operator("stax.import_from_library", text="Import")
                # encode key as "list||name"
                op_imp.lib_entry_index = f"{e.get('list')}||{e.get('name')}"
                row.operator("stax.preview_toggle", text="Preview").start_preview = True

            col.operator("stax.preview_toggle", text="End Preview").start_preview = False
        else:
            col.label(text="No items in StaX DB. Use 'Add to library' to export selected objects.")
