#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SVG Icon Loader
Utility for loading and managing SVG icons in the application.
"""

import os
from PySide2 import QtGui, QtSvg, QtCore


class IconLoader(object):
    """
    Utility class for loading SVG icons with caching.
    Provides consistent icon access throughout the application.
    """
    
    _instance = None
    _icon_cache = {}
    
    def __new__(cls):
        """Singleton pattern - only one instance exists."""
        if cls._instance is None:
            cls._instance = super(IconLoader, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize icon loader."""
        if self._initialized:
            return
        
        self._initialized = True
        
        # Get icons directory path
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.icons_dir = os.path.join(project_root, 'resources', 'icons')
        
        # Verify icons directory exists
        if not os.path.exists(self.icons_dir):
            print("WARNING: Icons directory not found: {}".format(self.icons_dir))
    
    def get_icon(self, icon_name, size=24, color=None):
        """
        Get a QIcon from an SVG file.
        
        Args:
            icon_name (str): Icon filename without extension (e.g., 'add', 'delete')
            size (int): Icon size in pixels (default: 24)
            color (str): Optional color override (hex format, e.g., '#ff0000')
        
        Returns:
            QtGui.QIcon: Loaded icon or default icon if not found
        """
        # Create cache key
        cache_key = "{}_{}_{}".format(icon_name, size, color or 'default')
        
        # Return cached icon if available
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]
        
        # Build icon file path
        icon_path = os.path.join(self.icons_dir, "{}.svg".format(icon_name))
        
        if not os.path.exists(icon_path):
            print("WARNING: Icon not found: {}".format(icon_path))
            # Return default Qt icon
            return QtGui.QIcon()
        
        try:
            # Load SVG and create pixmap
            renderer = QtSvg.QSvgRenderer(icon_path)
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(QtCore.Qt.transparent)
            
            painter = QtGui.QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            
            # Create icon from pixmap
            icon = QtGui.QIcon(pixmap)
            
            # Cache the icon
            self._icon_cache[cache_key] = icon
            
            return icon
        
        except Exception as e:
            print("ERROR loading icon {}: {}".format(icon_name, str(e)))
            return QtGui.QIcon()
    
    def get_pixmap(self, icon_name, size=24):
        """
        Get a QPixmap from an SVG file.
        
        Args:
            icon_name (str): Icon filename without extension
            size (int): Icon size in pixels
        
        Returns:
            QtGui.QPixmap: Loaded pixmap or default pixmap if not found
        """
        icon_path = os.path.join(self.icons_dir, "{}.svg".format(icon_name))
        
        if not os.path.exists(icon_path):
            return QtGui.QPixmap()
        
        try:
            renderer = QtSvg.QSvgRenderer(icon_path)
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(QtCore.Qt.transparent)
            
            painter = QtGui.QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            
            return pixmap
        
        except Exception as e:
            print("ERROR loading pixmap {}: {}".format(icon_name, str(e)))
            return QtGui.QPixmap()
    
    def clear_cache(self):
        """Clear the icon cache."""
        self._icon_cache.clear()


# Convenience function for global access
def get_icon(icon_name, size=24, color=None):
    """
    Get an icon using the global IconLoader instance.
    
    Args:
        icon_name (str): Icon filename without extension
        size (int): Icon size in pixels
        color (str): Optional color override
    
    Returns:
        QtGui.QIcon: Loaded icon
    """
    loader = IconLoader()
    return loader.get_icon(icon_name, size, color)


def get_pixmap(icon_name, size=24):
    """
    Get a pixmap using the global IconLoader instance.
    
    Args:
        icon_name (str): Icon filename without extension
        size (int): Icon size in pixels
    
    Returns:
        QtGui.QPixmap: Loaded pixmap
    """
    loader = IconLoader()
    return loader.get_pixmap(icon_name, size)
