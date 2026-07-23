# -*- coding: utf-8 -*-
"""
StaX - Advanced solution for mass production stock footage management
"""

try:
	from version import __version__          # flat (src/ on sys.path)
except ImportError:                          # imported as a package
	from .version import __version__

__author__ = 'Ahmed Ramadan'
