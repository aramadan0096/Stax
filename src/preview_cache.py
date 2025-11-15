# -*- coding: utf-8 -*-
"""
Preview Cache Manager for VFX_Asset_Hub
Implements LRU caching for preview thumbnails to reduce disk I/O
Python 2.7/3+ compatible
"""

import os
from collections import OrderedDict


class PreviewCache(object):
    """
    LRU (Least Recently Used) cache for preview images.
    Stores QPixmap objects in memory to avoid repeated disk reads.
    """
    
    def __init__(self, max_size=200, max_memory_mb=100):
        """
        Initialize preview cache.
        
        Args:
            max_size (int): Maximum number of previews to cache
            max_memory_mb (int): Approximate maximum memory usage in MB
        """
        self.max_size = max_size
        self.max_memory_mb = max_memory_mb
        self.cache = OrderedDict()  # Ordered dict for LRU behavior
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_requests': 0
        }
    
    def get(self, filepath):
        """
        Get cached preview for filepath.
        
        Args:
            filepath (str): Path to preview file
            
        Returns:
            QPixmap or None: Cached pixmap if available, None otherwise
        """
        self.cache_stats['total_requests'] += 1
        
        if filepath in self.cache:
            # Move to end (most recently used)
            self.cache.move_to_end(filepath)
            self.cache_stats['hits'] += 1
            return self.cache[filepath]
        
        self.cache_stats['misses'] += 1
        return None
    
    def put(self, filepath, pixmap):
        """
        Add preview to cache.
        
        Args:
            filepath (str): Path to preview file
            pixmap (QPixmap): Preview pixmap to cache
        """
        # Check if already exists
        if filepath in self.cache:
            # Update and move to end
            self.cache.move_to_end(filepath)
            self.cache[filepath] = pixmap
            return
        
        # Add new entry
        self.cache[filepath] = pixmap
        
        # Enforce size limit (LRU eviction)
        if len(self.cache) > self.max_size:
            # Remove oldest (first) item
            self.cache.popitem(last=False)
            self.cache_stats['evictions'] += 1
    
    def clear(self):
        """Clear all cached previews."""
        self.cache.clear()
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_requests': 0
        }
    
    def get_stats(self):
        """
        Get cache statistics.
        
        Returns:
            dict: Cache statistics including hit rate
        """
        total = self.cache_stats['total_requests']
        hit_rate = (self.cache_stats['hits'] / float(total) * 100) if total > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.cache_stats['hits'],
            'misses': self.cache_stats['misses'],
            'evictions': self.cache_stats['evictions'],
            'total_requests': total,
            'hit_rate': hit_rate
        }
    
    def remove(self, filepath):
        """
        Remove specific preview from cache.
        
        Args:
            filepath (str): Path to preview file
        """
        if filepath in self.cache:
            del self.cache[filepath]
    
    def preload(self, filepath_list, loader_func):
        """
        Preload multiple previews into cache.
        
        Args:
            filepath_list (list): List of filepaths to preload
            loader_func (callable): Function that takes filepath and returns QPixmap
        """
        for filepath in filepath_list:
            if filepath not in self.cache and os.path.exists(filepath):
                try:
                    pixmap = loader_func(filepath)
                    if pixmap:
                        self.put(filepath, pixmap)
                except Exception as e:
                    print("Error preloading {}: {}".format(filepath, str(e)))
    
    def get_memory_usage_estimate(self):
        """
        Estimate memory usage of cached previews.
        
        Returns:
            float: Estimated memory usage in MB
        """
        # Rough estimate: assume average 512x512 RGBA image = ~1MB each
        return len(self.cache) * 1.0  # MB
    
    def __repr__(self):
        """String representation."""
        stats = self.get_stats()
        return "<PreviewCache size={}/{} hit_rate={:.1f}%>".format(
            stats['size'],
            stats['max_size'],
            stats['hit_rate']
        )


# Global cache instance
_preview_cache = None

def get_preview_cache():
    """Get or create global preview cache singleton."""
    global _preview_cache
    if _preview_cache is None:
        _preview_cache = PreviewCache(max_size=200, max_memory_mb=200)
    return _preview_cache
