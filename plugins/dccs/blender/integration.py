# -*- coding: utf-8 -*-
"""
Blender Integration Module
Handles OS-level window re-parenting, event loop synchronization, and Blender API integration
"""

import os
import sys
import platform

try:
    import bpy
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False
    print("[BlenderIntegration] WARNING: bpy module not available (running outside Blender)")

try:
    from PySide2 import QtWidgets, QtCore, QtGui
    PYSIDE_AVAILABLE = True
    PYSIDE_VERSION = 2
except ImportError:
    try:
        from PySide import QtWidgets, QtCore, QtGui
        PYSIDE_AVAILABLE = True
        PYSIDE_VERSION = 1
    except ImportError:
        PYSIDE_AVAILABLE = False
        PYSIDE_VERSION = None
        print("[BlenderIntegration] WARNING: PySide not available")

from .dcc_base import DCCBaseMixin, ReferenceManager


class BlenderIntegration(DCCBaseMixin):
    """
    Blender-specific integration implementation.
    Handles window re-parenting, event loop, and Blender API calls.
    """
    
    def __init__(self):
        """Initialize Blender integration."""
        super(BlenderIntegration, self).__init__()
        self._blender_window_handle = None
        self._event_timer = None
        self._app = None
        self._input_filter = None
        
        if not BLENDER_AVAILABLE:
            print("[BlenderIntegration] WARNING: Running outside Blender environment")
        if not PYSIDE_AVAILABLE:
            print("[BlenderIntegration] ERROR: PySide not available - GUI will not work")
    
    def get_main_window_handle(self):
        """
        Get Blender's main window OS-level handle.
        Uses platform-specific APIs (Windows: win32gui, Linux: X11, macOS: Cocoa).
        
        Returns:
            long/int: Native window handle or None
        """
        if self._blender_window_handle:
            return self._blender_window_handle
        
        system = platform.system()
        
        if system == 'Windows':
            self._blender_window_handle = self._get_windows_handle()
        elif system == 'Linux':
            self._blender_window_handle = self._get_linux_handle()
        elif system == 'Darwin':  # macOS
            self._blender_window_handle = self._get_macos_handle()
        else:
            print("[BlenderIntegration] WARNING: Unsupported platform: {}".format(system))
            return None
        
        return self._blender_window_handle
    
    def _get_windows_handle(self):
        """Get Blender window handle on Windows using win32gui."""
        try:
            try:
                import win32gui
                import win32con
            except ImportError:
                print("[BlenderIntegration] ERROR: win32gui not available - install pywin32")
                return None
            
            # Find Blender window by class name or title
            def enum_windows_callback(hwnd, windows):
                window_text = win32gui.GetWindowText(hwnd)
                class_name = win32gui.GetClassName(hwnd)
                
                # Blender's main window typically has "Blender" in title
                if 'blender' in window_text.lower() or 'blender' in class_name.lower():
                    # Check if it's the main window (has children, visible, etc.)
                    if win32gui.IsWindowVisible(hwnd):
                        windows.append(hwnd)
            
            windows = []
            win32gui.EnumWindows(enum_windows_callback, windows)
            
            if windows:
                # Get the top-level window (usually the first one)
                hwnd = windows[0]
                print("[BlenderIntegration] Found Blender window handle: {}".format(hwnd))
                return hwnd
            else:
                print("[BlenderIntegration] WARNING: Blender window not found")
                return None
                
        except Exception as e:
            print("[BlenderIntegration] ERROR: Failed to get Windows handle: {}".format(e))
            import traceback
            traceback.print_exc()
            return None
    
    def _get_linux_handle(self):
        """Get Blender window handle on Linux using X11."""
        try:
            # Try using Xlib (requires python-xlib)
            from Xlib import display
            from Xlib import X
            
            d = display.Display()
            root = d.screen().root
            
            # Search for Blender window
            def find_blender_window(window):
                try:
                    name = window.get_wm_name()
                    if name and 'blender' in name.lower():
                        return window.id
                    
                    # Check children
                    children = window.query_tree().children
                    for child in children:
                        result = find_blender_window(child)
                        if result:
                            return result
                except:
                    pass
                return None
            
            window_id = find_blender_window(root)
            if window_id:
                print("[BlenderIntegration] Found Blender window XID: {}".format(window_id))
                return window_id
            else:
                print("[BlenderIntegration] WARNING: Blender window not found")
                return None
                
        except ImportError:
            print("[BlenderIntegration] ERROR: Xlib not available - install python-xlib")
            return None
        except Exception as e:
            print("[BlenderIntegration] ERROR: Failed to get Linux handle: {}".format(e))
            import traceback
            traceback.print_exc()
            return None
    
    def _get_macos_handle(self):
        """Get Blender window handle on macOS using Cocoa/AppKit."""
        try:
            # macOS implementation would use PyObjC or ctypes with Cocoa
            # This is a placeholder - full implementation requires PyObjC
            print("[BlenderIntegration] WARNING: macOS handle retrieval not yet implemented")
            return None
        except Exception as e:
            print("[BlenderIntegration] ERROR: Failed to get macOS handle: {}".format(e))
            return None
    
    def setup_qapplication(self):
        """
        Setup QApplication instance (must be called before creating widgets).
        Uses existing instance if available, creates new one if not.
        """
        if not PYSIDE_AVAILABLE:
            print("[BlenderIntegration] ERROR: Cannot setup QApplication - PySide not available")
            return None
        
        app = QtWidgets.QApplication.instance()
        if app is None:
            print("[BlenderIntegration] Creating new QApplication instance")
            app = QtWidgets.QApplication(sys.argv)
            self._app = app
        else:
            print("[BlenderIntegration] Using existing QApplication instance")
            self._app = app
        
        # CRITICAL: Do NOT call app.exec() - it would block Blender!
        return app
    
    def reparent_window(self, widget, parent_handle):
        """
        Re-parent a Qt widget to Blender's main window using OS-level APIs.
        
        Args:
            widget: QWidget to re-parent
            parent_handle: Native window handle of Blender main window
            
        Returns:
            bool: True if successful
        """
        if not widget or not parent_handle:
            return False
        
        system = platform.system()
        
        if system == 'Windows':
            return self._reparent_windows(widget, parent_handle)
        elif system == 'Linux':
            return self._reparent_linux(widget, parent_handle)
        elif system == 'Darwin':
            return self._reparent_macos(widget, parent_handle)
        else:
            print("[BlenderIntegration] WARNING: Unsupported platform for re-parenting")
            return False
    
    def _reparent_windows(self, widget, parent_handle):
        """Re-parent widget on Windows using SetParent API."""
        try:
            try:
                import win32gui
                import win32con
            except ImportError:
                print("[BlenderIntegration] ERROR: win32gui not available - install pywin32")
                return False
            
            # Get widget's native window handle
            widget_handle = int(widget.winId())
            
            # Re-parent using SetParent
            win32gui.SetParent(widget_handle, parent_handle)
            
            # Set window styles for proper embedding
            style = win32gui.GetWindowLong(widget_handle, win32con.GWL_STYLE)
            style = style & ~win32con.WS_POPUP
            style = style | win32con.WS_CHILD
            win32gui.SetWindowLong(widget_handle, win32con.GWL_STYLE, style)
            
            # Show window
            win32gui.ShowWindow(widget_handle, win32con.SW_SHOW)
            
            print("[BlenderIntegration] Successfully re-parented widget to Blender window")
            return True
            
        except ImportError:
            print("[BlenderIntegration] ERROR: win32gui not available - install pywin32")
            return False
        except Exception as e:
            print("[BlenderIntegration] ERROR: Failed to re-parent on Windows: {}".format(e))
            import traceback
            traceback.print_exc()
            return False
    
    def _reparent_linux(self, widget, parent_handle):
        """Re-parent widget on Linux using X11."""
        try:
            from Xlib import display
            from Xlib import X
            
            d = display.Display()
            widget_xid = int(widget.winId())
            
            # Re-parent using XReparentWindow
            widget_window = d.create_resource_object('window', widget_xid)
            parent_window = d.create_resource_object('window', parent_handle)
            
            widget_window.reparent(parent_window, 0, 0)
            d.sync()
            
            print("[BlenderIntegration] Successfully re-parented widget to Blender window")
            return True
            
        except Exception as e:
            print("[BlenderIntegration] ERROR: Failed to re-parent on Linux: {}".format(e))
            import traceback
            traceback.print_exc()
            return False
    
    def _reparent_macos(self, widget, parent_handle):
        """Re-parent widget on macOS (placeholder)."""
        print("[BlenderIntegration] WARNING: macOS re-parenting not yet implemented")
        return False
    
    def setup_event_loop(self):
        """
        Setup non-blocking event loop using Blender's timer system.
        Registers a modal timer operator that calls QApplication.processEvents().
        """
        if not PYSIDE_AVAILABLE:
            print("[BlenderIntegration] WARNING: Cannot setup event loop - PySide not available")
            return
        
        if not BLENDER_AVAILABLE:
            print("[BlenderIntegration] WARNING: Cannot setup event loop - Blender not available")
            return
        
        # Register modal timer operator
        try:
            # Create operator class dynamically
            class StaXEventLoopOperator(bpy.types.Operator):
                """Modal timer operator for Qt event processing."""
                bl_idname = "wm.stax_event_loop"
                bl_label = "StaX Event Loop"
                
                _timer = None
                
                def modal(self, context, event):
                    """Modal function called periodically."""
                    if event.type == 'TIMER':
                        # Process Qt events (non-blocking, 1ms limit)
                        app = QtWidgets.QApplication.instance()
                        if app:
                            app.processEvents(QtCore.QEventLoop.AllEvents, 1)
                    return {'PASS_THROUGH'}
                
                def execute(self, context):
                    """Start the timer."""
                    wm = context.window_manager
                    self._timer = wm.event_timer_add(0.01, window=context.window)  # 10ms = 100Hz
                    wm.modal_handler_add(self)
                    return {'RUNNING_MODAL'}
                
                def cancel(self, context):
                    """Stop the timer."""
                    wm = context.window_manager
                    wm.event_timer_remove(self._timer)
                    return {'CANCELLED'}
            
            # Register operator
            if not hasattr(bpy.types, 'WM_OT_stax_event_loop'):
                bpy.utils.register_class(StaXEventLoopOperator)
                print("[BlenderIntegration] Registered event loop operator")
            
            # Start the operator
            bpy.ops.wm.stax_event_loop()
            print("[BlenderIntegration] Started event loop timer")
            
        except Exception as e:
            print("[BlenderIntegration] ERROR: Failed to setup event loop: {}".format(e))
            import traceback
            traceback.print_exc()
    
    def setup_input_filter(self, widget):
        """
        Setup global event filter to prevent input capture conflicts.
        Passes Blender navigation shortcuts back to Blender.
        
        Args:
            widget: QWidget to install filter on
        """
        if not PYSIDE_AVAILABLE:
            return
        
        class BlenderInputFilter(QtCore.QObject):
            """Event filter to pass Blender shortcuts through."""
            
            def eventFilter(self, obj, event):
                """Filter events to allow Blender navigation."""
                # Blender navigation typically uses Alt + Mouse
                if event.type() == QtCore.QEvent.KeyPress:
                    # Allow Alt key combinations to pass through
                    if event.modifiers() & QtCore.Qt.AltModifier:
                        return False  # Don't filter - let Blender handle it
                
                # Let Qt handle other events normally
                return super(BlenderInputFilter, self).eventFilter(obj, event)
        
        self._input_filter = BlenderInputFilter()
        widget.installEventFilter(self._input_filter)
        print("[BlenderIntegration] Installed input filter for Blender navigation")
    
    def cleanup(self):
        """Cleanup resources on shutdown."""
        # Stop event loop
        if BLENDER_AVAILABLE:
            try:
                bpy.ops.wm.stax_event_loop('CANCELLED')
            except:
                pass
        
        # Remove input filter
        if self._input_filter:
            self._input_filter = None
        
        print("[BlenderIntegration] Cleanup completed")

