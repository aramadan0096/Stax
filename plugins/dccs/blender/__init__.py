# -*- coding: utf-8 -*-
"""
StaX Blender Addon
Two-stage loading: Stage 1 (minimal initialization) and Stage 2 (deferred full load)
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

# Resolve StaX root robustly when installed into Blender addons.
current_dir = os.path.dirname(__file__)
_stax_root = None

# 1) Env override
_env_root = os.environ.get('STAX_ROOT')
if _env_root and os.path.isdir(_env_root):
    _stax_root = os.path.abspath(_env_root)

# 2) Installer-written hint file
if _stax_root is None:
    hint_path = os.path.join(current_dir, '_stax_paths.py')
    if os.path.isfile(hint_path):
        try:
            hint_mod = {}
            with open(hint_path, 'r') as fh:
                code = fh.read()
            exec(code, hint_mod, hint_mod)
            hinted = hint_mod.get('STAX_ROOT')
            if hinted and os.path.isdir(hinted):
                _stax_root = os.path.abspath(hinted)
        except Exception:
            pass

# 3) Fallback to relative (dev mode)
if _stax_root is None:
    _stax_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))

# Put root/lib on sys.path before importing bootstrap
if _stax_root not in sys.path:
    sys.path.insert(0, _stax_root)
lib_dir = os.path.join(_stax_root, 'lib')
if os.path.exists(lib_dir) and lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

# Ensure StaX bootstrap runs first (sets sys.path, PATH, Qt plugin paths)
import dependency_bootstrap
dependency_bootstrap.bootstrap(base_dir=_stax_root)

# Stage 1: Minimal initialization - setup paths and environment
print("\n[StaX Blender Addon] Stage 1: Initialization started...")

# Stage 1: Initialize IPC server (minimal, no heavy imports)
_ipc_server = None
_panel_module = None  # Will be loaded in Stage 2

def _stage1_init():
    """Stage 1: Minimal initialization - IPC server setup only."""
    global _ipc_server
    
    try:
        from .ipc_server import IPCServer
        
        # Create minimal command handler for Stage 1
        def stage1_command_handler(command, args=None, kwargs=None):
            """Stage 1 command handler - triggers Stage 2 load."""
            if command == "stax.blender.load_stage2":
                _load_stage2()
                return {'success': True, 'message': 'Stage 2 loaded'}
            return {'success': False, 'error': 'Stage 2 not loaded yet'}
        
        _ipc_server = IPCServer(command_handler=stage1_command_handler)
        _ipc_server.set_command_executor(stage1_command_handler)
        _ipc_server.start()
        
        print("[StaX Blender Addon] Stage 1: IPC server started on port {}".format(_ipc_server.port))
        return True
    except Exception as e:
        print("[StaX Blender Addon] Stage 1 ERROR: {}".format(e))
        import traceback
        traceback.print_exc()
        return False

def _load_stage2():
    """Stage 2: Deferred full load - import heavy modules and create UI."""
    global _panel_module
    
    if _panel_module is not None:
        return True  # Already loaded
    
    print("[StaX Blender Addon] Stage 2: Loading full module...")
    
    try:
        # Setup QApplication first (like Prism does)
        try:
            from PySide2.QtWidgets import QApplication
            qapp = QApplication.instance()
            if qapp is None:
                import sys
                qapp = QApplication(sys.argv)
                print("[StaX Blender Addon] Created QApplication instance")
            else:
                print("[StaX Blender Addon] Using existing QApplication instance")
        except ImportError:
            try:
                from PySide.QtGui import QApplication
                qapp = QApplication.instance()
                if qapp is None:
                    import sys
                    qapp = QApplication(sys.argv)
                    print("[StaX Blender Addon] Created QApplication instance (PySide)")
            except ImportError as e:
                print("[StaX Blender Addon] ERROR: PySide not available: {}".format(e))
                return False
        
        # Import panel module (this triggers all heavy imports)
        from . import panel
        _panel_module = panel
        
        # Update IPC server command handler to use full panel
        panel_instance = panel.get_panel_instance()
        if _ipc_server and panel_instance:
            _ipc_server.set_command_executor(panel_instance._execute_ipc_command)
        
        print("[StaX Blender Addon] Stage 2: Full module loaded successfully")
        return True
    except Exception as e:
        print("[StaX Blender Addon] Stage 2 ERROR: {}".format(e))
        import traceback
        error_trace = traceback.format_exc()
        print(error_trace)
        # Store error for reporting
        _panel_module = {'error': str(e), 'traceback': error_trace}
        return False

# Blender operator classes
class STAX_OT_OpenPanel(bpy.types.Operator):
    """Open the StaX Asset Manager Panel"""
    bl_idname = "stax.open_panel"
    bl_label = "Open StaX"
    bl_description = "Open StaX Asset Manager Panel"

    def execute(self, context):
        # Trigger Stage 2 load if not already loaded
        success = _load_stage2()
        
        if success and _panel_module and hasattr(_panel_module, 'show_stax_panel'):
            try:
                _panel_module.show_stax_panel()
            except Exception as e:
                error_msg = "Error showing panel: {}".format(str(e))
                print("[StaX Blender Addon] {}".format(error_msg))
                import traceback
                traceback.print_exc()
                self.report({'ERROR'}, error_msg)
        else:
            error_msg = "Failed to load StaX panel"
            if isinstance(_panel_module, dict) and 'error' in _panel_module:
                error_msg = "Failed to load StaX panel: {}".format(_panel_module['error'])
            print("[StaX Blender Addon] {}".format(error_msg))
            if isinstance(_panel_module, dict) and 'traceback' in _panel_module:
                print(_panel_module['traceback'])
            self.report({'ERROR'}, error_msg)
        return {'FINISHED'}

class STAX_OT_AddToLibrary(bpy.types.Operator):
    """Add selected objects to StaX Library"""
    bl_idname = "stax.add_to_library"
    bl_label = "Add to Library"
    bl_description = "Add selected Blender objects to StaX library"

    def execute(self, context):
        success = _load_stage2()
        
        if success and _panel_module and hasattr(_panel_module, 'add_to_library'):
            try:
                _panel_module.add_to_library()
            except Exception as e:
                error_msg = "Error adding to library: {}".format(str(e))
                print("[StaX Blender Addon] {}".format(error_msg))
                self.report({'ERROR'}, error_msg)
        else:
            error_msg = "Failed to load StaX panel"
            if isinstance(_panel_module, dict) and 'error' in _panel_module:
                error_msg = "Failed to load StaX panel: {}".format(_panel_module['error'])
            self.report({'ERROR'}, error_msg)
        return {'FINISHED'}

class STAX_MT_Menu(bpy.types.Menu):
    bl_label = "StaX"
    bl_idname = "STAX_MT_Menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("stax.open_panel", text="Open Browser")
        layout.operator("stax.add_to_library", text="Add Selected to Library")

def draw_menu(self, context):
    """Draw menu item in Blender's topbar."""
    self.layout.menu(STAX_MT_Menu.bl_idname)

classes = (
    STAX_OT_OpenPanel,
    STAX_OT_AddToLibrary,
    STAX_MT_Menu,
)

def register():
    """Register Blender addon (Stage 1 only)."""
    print("[StaX Blender Addon] Registering addon...")

    # Skip UI setup in background mode
    if getattr(bpy.app, "background", False):
        print("[StaX Blender Addon] Running in background mode; skipping UI registration")
        return
    
    # Register Blender classes
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
            print("[StaX Blender Addon] Registered: {}".format(cls.__name__))
        except Exception as e:
            print("[StaX Blender Addon] ERROR registering {}: {}".format(cls.__name__, e))
    
    # Add menu
    try:
        bpy.types.TOPBAR_MT_editor_menus.append(draw_menu)
        print("[StaX Blender Addon] Added menu to topbar")
    except Exception as e:
        print("[StaX Blender Addon] ERROR adding menu: {}".format(e))
    
    # Stage 1 initialization
    _stage1_init()
    
    print("[StaX Blender Addon] Registration complete (Stage 1)")

def unregister():
    """Unregister Blender addon."""
    print("[StaX Blender Addon] Unregistering addon...")
    
    # Stop IPC server
    global _ipc_server
    if _ipc_server:
        _ipc_server.stop()
        _ipc_server = None
    
    # Remove menu
    try:
        bpy.types.TOPBAR_MT_editor_menus.remove(draw_menu)
    except:
        pass
    
    # Unregister classes
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except:
            pass
    
    print("[StaX Blender Addon] Unregistration complete")

if __name__ == "__main__":
    register()
