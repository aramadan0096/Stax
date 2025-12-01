# -*- coding: utf-8 -*-
"""
DCC Base Mixin and Reference Manager
Provides universal base class for DCC-specific GUI implementations
"""

import sys
import os


class ReferenceManager(object):
    """
    Mandatory Reference Management system to prevent Python garbage collection
    of PySide widgets. Maintains persistent references to all top-level widgets.
    """
    
    _stax_widget_references = []  # Class-level list for all widgets
    _lock = None
    
    @classmethod
    def _get_lock(cls):
        """Get thread lock (lazy initialization)."""
        if cls._lock is None:
            import threading
            cls._lock = threading.Lock()
        return cls._lock
    
    @classmethod
    def register_widget(cls, widget):
        """Register a widget to prevent garbage collection.
        
        Args:
            widget: QWidget instance to register
        """
        with cls._get_lock():
            if widget not in cls._stax_widget_references:
                cls._stax_widget_references.append(widget)
                print("[ReferenceManager] Registered widget: {} (total: {})".format(
                    widget.__class__.__name__, len(cls._stax_widget_references)
                ))
    
    @classmethod
    def unregister_widget(cls, widget):
        """Unregister a widget (allows garbage collection).
        
        Args:
            widget: QWidget instance to unregister
        """
        with cls._get_lock():
            if widget in cls._stax_widget_references:
                cls._stax_widget_references.remove(widget)
                print("[ReferenceManager] Unregistered widget: {} (total: {})".format(
                    widget.__class__.__name__, len(cls._stax_widget_references)
                ))
    
    @classmethod
    def get_all_widgets(cls):
        """Get all registered widgets.
        
        Returns:
            list: List of registered widgets
        """
        with cls._get_lock():
            return list(cls._stax_widget_references)
    
    @classmethod
    def clear_all(cls):
        """Clear all registered widgets (use with caution)."""
        with cls._get_lock():
            count = len(cls._stax_widget_references)
            cls._stax_widget_references.clear()
            print("[ReferenceManager] Cleared all {} widgets".format(count))


class DCCBaseMixin(object):
    """
    Abstract base mixin for all DCC-specific GUI implementations.
    Provides standardized functions for window retrieval and widget wrapping.
    """
    
    def __init__(self):
        """Initialize DCC base mixin."""
        self._shiboken_version = None
        self._pyside_version = None
        self._detect_qt_bindings()
    
    def _detect_qt_bindings(self):
        """Detect active Qt binding version (PySide vs PySide2, Shiboken vs Shiboken2)."""
        try:
            # Try PySide2 first
            import PySide2
            from shiboken2 import wrapInstance, getCppPointer
            self._pyside_version = 2
            self._shiboken_version = 2
            self._wrap_func = wrapInstance
            self._get_pointer_func = getCppPointer
            print("[DCCBaseMixin] Detected PySide2/Shiboken2")
        except ImportError:
            try:
                # Fallback to PySide
                import PySide
                from shiboken import wrapInstance, getCppPointer
                self._pyside_version = 1
                self._shiboken_version = 1
                self._wrap_func = wrapInstance
                self._get_pointer_func = getCppPointer
                print("[DCCBaseMixin] Detected PySide/Shiboken")
            except ImportError:
                print("[DCCBaseMixin] WARNING: No PySide bindings found!")
                self._pyside_version = None
                self._shiboken_version = None
                self._wrap_func = None
                self._get_pointer_func = None
    
    def get_main_window_handle(self):
        """
        Retrieve the host application's primary window pointer.
        Must be implemented by DCC-specific subclasses.
        
        Returns:
            long/int: Native window pointer (platform-specific)
        """
        raise NotImplementedError("Subclass must implement get_main_window_handle()")
    
    def wrap_ptr(self, ptr, QClass):
        """
        Safely wrap a native C++ pointer into a Python Qt widget instance.
        Uses detected Shiboken version automatically.
        
        Args:
            ptr: Native C++ pointer (long/int)
            QClass: Qt widget class to wrap into (e.g., QWidget)
            
        Returns:
            QWidget instance or None if wrapping fails
        """
        if not self._wrap_func:
            print("[DCCBaseMixin] ERROR: No Shiboken available for wrapping")
            return None
        
        try:
            # Ensure ptr is long (cross-platform compatibility)
            if sys.version_info[0] < 3:
                ptr = long(ptr)
            else:
                ptr = int(ptr)
            
            widget = self._wrap_func(ptr, QClass)
            print("[DCCBaseMixin] Successfully wrapped pointer {} to {}".format(ptr, QClass.__name__))
            return widget
        except Exception as e:
            print("[DCCBaseMixin] ERROR: Failed to wrap pointer: {}".format(e))
            import traceback
            traceback.print_exc()
            return None
    
    def create_widget(self, widget_class, parent=None, register=True):
        """
        Create a widget and optionally register it with ReferenceManager.
        
        Args:
            widget_class: QWidget class to instantiate
            parent: Optional parent widget
            register (bool): Whether to register with ReferenceManager
            
        Returns:
            QWidget instance
        """
        widget = widget_class(parent)
        
        if register:
            # Only register top-level widgets (no parent)
            if parent is None:
                ReferenceManager.register_widget(widget)
        
        return widget
    
    def get_shiboken_version(self):
        """Get detected Shiboken version (1 or 2)."""
        return self._shiboken_version
    
    def get_pyside_version(self):
        """Get detected PySide version (1 or 2)."""
        return self._pyside_version

