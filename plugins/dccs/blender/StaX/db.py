import os, json
import bpy
from bpy.app.handlers import persistent
from .prefs import addon_key

DB_FILENAME = "stax_db.json"

def get_repo_root():
    prefs = bpy.context.preferences.addons.get(addon_key)
    if not prefs:
        return ""
    return prefs.preferences.repository_path if hasattr(prefs, "preferences") else prefs.repository_path  # compatibility

def _db_path():
    root = get_repo_root()
    if not root:
        return None
    return os.path.join(os.path.abspath(root), DB_FILENAME)

def ensure_repo_subfolders():
    root = get_repo_root()
    if not root:
        return
    os.makedirs(os.path.join(root, "mesh"), exist_ok=True)
    os.makedirs(os.path.join(root, "proxy"), exist_ok=True)

def load_db():
    path = _db_path()
    if not path:
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_db(data):
    path = _db_path()
    if not path:
        raise RuntimeError("Repository path not set in StaX preferences.")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def register_abc(name, list_name, comment, abc_path, glb_path):
    data = load_db()
    entry = {
        "name": name,
        "list": list_name,
        "comment": comment,
        "abc": abc_path,
        "glb": glb_path
    }
    # db structure: dict of lists -> arrays of entries
    if list_name not in data:
        data[list_name] = []
    data[list_name].append(entry)
    save_db(data)

def iter_library_entries():
    db_data = load_db()
    for list_name, items in db_data.items():
        for item in items:
            yield list_name, item

# convenience for UI
def get_entries_as_list():
    db_data = load_db()
    rows = []
    for list_name, items in db_data.items():
        for item in items:
            rows.append({
                "list": list_name,
                "name": item.get("name"),
                "comment": item.get("comment"),
                "abc": item.get("abc"),
                "glb": item.get("glb"),
            })
    return rows

def register():
    ensure_repo_subfolders()

def unregister():
    pass
