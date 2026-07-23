#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SVG Icon Loader
Utility for loading and managing SVG icons in the application.
"""

import os
import logging
from collections import OrderedDict
from PySide2 import QtGui, QtSvg, QtCore


log = logging.getLogger(__name__)


class IconLoader(object):
    """
    Utility class for loading SVG icons with a bounded LRU cache.
    Provides consistent icon access throughout the application.
    """
    
    _instance = None
    _icon_cache = OrderedDict()
    _MAX_CACHE_ENTRIES = 256
    _MISS = QtGui.QIcon()  # Shared sentinel for missing/failed icon loads
    
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
            log.warning("Icons directory not found: %s", self.icons_dir)
    
    def get_icon(self, icon_name, size=24, color=None):
        """
        Get a QIcon from an SVG file, with a bounded LRU cache.
        
        Args:
            icon_name (str): Icon filename without extension (e.g., 'add', 'delete')
            size (int): Icon size in pixels (default: 24)
            color (str): Optional color override (hex format, e.g., '#ff0000')
        
        Returns:
            QtGui.QIcon: Loaded icon or default icon if not found
        """
        cache_key = "{}_{}_{}".format(icon_name, size, color or 'default')

        cached = self._icon_cache.get(cache_key)
        if cached is not None:
            self._icon_cache.move_to_end(cache_key)
            return cached
        
        # Build icon file path
        icon_path = os.path.join(self.icons_dir, "{}.svg".format(icon_name))

        if not os.path.exists(icon_path):
            log.warning("Icon not found: %s", icon_path)
            return self._store_icon(cache_key, self._MISS)

        try:
            renderer = QtSvg.QSvgRenderer(icon_path)
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(QtCore.Qt.transparent)

            painter = QtGui.QPainter(pixmap)
            renderer.render(painter)
            painter.end()

            return self._store_icon(cache_key, QtGui.QIcon(pixmap))

        except Exception as e:
            log.exception("Error loading icon %s: %s", icon_name, str(e))
            return self._store_icon(cache_key, self._MISS)

    def _store_icon(self, cache_key, icon):
        """Insert an icon into the bounded LRU cache and evict oldest entries."""
        self._icon_cache[cache_key] = icon
        self._icon_cache.move_to_end(cache_key)
        while len(self._icon_cache) > self._MAX_CACHE_ENTRIES:
            self._icon_cache.popitem(last=False)
        return icon
    
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
