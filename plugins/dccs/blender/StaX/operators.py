import bpy, os, tempfile, shutil
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator
from . import db
from .prefs import addon_key

PREVIEW_COLLECTION_NAME = "StaX_Preview_Collection"
PREVIEW_DUP_PREFIX = "StaXPreview_"

def get_repo_root():
    prefs = bpy.context.preferences.addons.get(addon_key)
    if not prefs:
        return ""
    return prefs.preferences.repository_path if hasattr(prefs, "preferences") else prefs.repository_path

class STAX_OT_add_to_library(Operator):
    bl_idname = "stax.add_to_library"
    bl_label = "Add selected to StaX library"
    bl_options = {'REGISTER', 'UNDO'}

    object_name: StringProperty(name="Object Name", default="")
    list_name: StringProperty(name="List", default="default")
    comment: StringProperty(name="Comment", default="")

    def invoke(self, context, event):
        if context.selected_objects:
            # suggest default name from active object
            self.object_name = context.active_object.name if context.active_object else context.selected_objects[0].name
        else:
            self.report({'ERROR'}, "No object selected to add to library.")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):
        repo = get_repo_root()
        if not repo:
            self.report({'ERROR'}, "StaX repository path not configured in add-on preferences.")
            return {'CANCELLED'}
        mesh_dir = os.path.join(repo, "mesh")
        proxy_dir = os.path.join(repo, "proxy")
        os.makedirs(mesh_dir, exist_ok=True)
        os.makedirs(proxy_dir, exist_ok=True)

        name_safe = self.object_name.replace(" ", "_")
        abc_fname = f"{name_safe}.abc"
        glb_fname = f"{name_safe}.glb"
        abc_path = os.path.join(mesh_dir, abc_fname)
        glb_path = os.path.join(proxy_dir, glb_fname)

        # Export Alembic (.abc)
        try:
            bpy.ops.wm.alembic_export(filepath=abc_path, selected=True, flatten=False, visible_layers_only=False)
        except Exception as e:
            self.report({'ERROR'}, f"Alembic export failed: {e}")
            return {'CANCELLED'}

        # Export GLB (proxy)
        try:
            bpy.ops.export_scene.gltf(filepath=glb_path, export_format='GLB', export_selected=True)
        except Exception as e:
            # remove abc if glb failed? we keep abc but warn
            self.report({'WARNING'}, f"GLB export failed: {e}. Alembic was exported.")
            # continue

        # register in StaX db
        rel_abc = os.path.relpath(abc_path, repo)
        rel_glb = os.path.relpath(glb_path, repo)
        db.register_abc(self.object_name, self.list_name, self.comment, rel_abc, rel_glb)

        self.report({'INFO'}, f"Exported {abc_fname} and {glb_fname} and registered in StaX DB (list={self.list_name}).")
        return {'FINISHED'}

class STAX_OT_import_from_library(Operator):
    bl_idname = "stax.import_from_library"
    bl_label = "Import selected StaX library item"
    bl_options = {'REGISTER', 'UNDO'}

    lib_entry_index: StringProperty(name="Entry key", default="")

    def execute(self, context):
        repo = get_repo_root()
        if not repo:
            self.report({'ERROR'}, "StaX repository path not configured in add-on preferences.")
            return {'CANCELLED'}
        # lib_entry_index uses a simple encoded format "list||name" (provided by UI)
        try:
            list_name, name = self.lib_entry_index.split("||", 1)
        except:
            self.report({'ERROR'}, "Invalid library key.")
            return {'CANCELLED'}

        db_data = db.load_db()
        if list_name not in db_data:
            self.report({'ERROR'}, "List not found.")
            return {'CANCELLED'}
        found = None
        for item in db_data[list_name]:
            if item.get("name") == name:
                found = item
                break
        if not found:
            self.report({'ERROR'}, "Library item not found.")
            return {'CANCELLED'}

        # Prefer GLB import (proxy) if exists, else ABC
        glb_rel = found.get("glb")
        abc_rel = found.get("abc")
        glb_path = os.path.join(repo, glb_rel) if glb_rel else None
        abc_path = os.path.join(repo, abc_rel) if abc_rel else None

        if glb_path and os.path.exists(glb_path):
            # glTF import
            bpy.ops.import_scene.gltf(filepath=glb_path)
            self.report({'INFO'}, f"Imported proxy GLB: {os.path.basename(glb_path)}")
            return {'FINISHED'}
        elif abc_path and os.path.exists(abc_path):
            bpy.ops.wm.alembic_import(filepath=abc_path)
            self.report({'INFO'}, f"Imported Alembic: {os.path.basename(abc_path)}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Neither GLB nor ABC found on disk.")
            return {'CANCELLED'}

class STAX_OT_preview_toggle(Operator):
    bl_idname = "stax.preview_toggle"
    bl_label = "Toggle Preview Mode"
    bl_options = {'REGISTER'}

    start_preview: BoolProperty(default=True)

    def execute(self, context):
        if self.start_preview:
            return self.start_preview_mode(context)
        else:
            return self.stop_preview_mode(context)

    def start_preview_mode(self, context):
        # Duplicate selected objects into a preview collection and hide other collections
        sel = context.selected_objects
        if not sel:
            self.report({'ERROR'}, "No selection to preview.")
            return {'CANCELLED'}
        # create/clean preview collection
        coll = bpy.data.collections.get(PREVIEW_COLLECTION_NAME)
        if not coll:
            coll = bpy.data.collections.new(PREVIEW_COLLECTION_NAME)
            context.scene.collection.children.link(coll)
        else:
            # remove existing objects inside preview
            for o in list(coll.objects):
                coll.objects.unlink(o)

        # duplicate selection into preview collection
        dup_objs = []
        for o in sel:
            new = o.copy()
            if o.data:
                new.data = o.data.copy()
            coll.objects.link(new)
            dup_objs.append(new)
            new.name = PREVIEW_DUP_PREFIX + new.name

        # hide all other collections (store hidden state on scene)
        scene = context.scene
        scene["stax_preview_hidden_collections"] = []
        for c in list(scene.collection.children):
            if c.name != PREVIEW_COLLECTION_NAME:
                scene["stax_preview_hidden_collections"].append(c.name)
                c.hide_viewport = True
                c.hide_render = True

        self.report({'INFO'}, "StaX preview started. Use 'End Preview' to restore view.")
        return {'FINISHED'}

    def stop_preview_mode(self, context):
        # restore visibility and remove preview collection
        scene = context.scene
        hidden = scene.get("stax_preview_hidden_collections", [])
        for name in hidden:
            c = bpy.data.collections.get(name)
            if c:
                c.hide_viewport = False
                c.hide_render = False
        # remove preview collection and its objects
        coll = bpy.data.collections.get(PREVIEW_COLLECTION_NAME)
        if coll:
            # remove objects
            for o in list(coll.objects):
                coll.objects.unlink(o)
                try:
                    bpy.data.objects.remove(o)
                except Exception:
                    pass
            # unlink and remove collection
            try:
                scene.collection.children.unlink(coll)
            except Exception:
                pass
            try:
                bpy.data.collections.remove(coll)
            except Exception:
                pass

        if "stax_preview_hidden_collections" in scene:
            del scene["stax_preview_hidden_collections"]

        self.report({'INFO'}, "StaX preview ended and view restored.")
        return {'FINISHED'}

def cleanup_preview_if_exists():
    coll = bpy.data.collections.get(PREVIEW_COLLECTION_NAME)
    if coll:
        # try to unlink from any scenes
        for scene in bpy.data.scenes:
            try:
                if coll.name in [c.name for c in scene.collection.children]:
                    scene.collection.children.unlink(coll)
            except Exception:
                pass
        for o in list(coll.objects):
            try:
                coll.objects.unlink(o)
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass
        try:
            bpy.data.collections.remove(coll)
        except Exception:
            pass
