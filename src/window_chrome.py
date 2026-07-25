# -*- coding: utf-8 -*-
"""
Small platform helpers for native window chrome.
"""

import ctypes
import sys


def _colorref(hex_color):
    color = hex_color.strip().lstrip("#")
    if len(color) != 6:
        raise ValueError("Expected #RRGGBB color")

    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    return red | (green << 8) | (blue << 16)


def set_windows_title_bar_color(widget, caption_color="#000000", text_color="#ffffff"):
    if sys.platform != "win32":
        return False

    try:
        hwnd = int(widget.winId())
        dwmapi = ctypes.windll.dwmapi

        true_value = ctypes.c_int(1)
        for dark_mode_attribute in (20, 19):
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                dark_mode_attribute,
                ctypes.byref(true_value),
                ctypes.sizeof(true_value),
            )

        attributes = (
            (35, _colorref(caption_color)),
            (36, _colorref(text_color)),
            (34, _colorref(caption_color)),
        )
        for attribute, color in attributes:
            color_value = ctypes.c_int(color)
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                attribute,
                ctypes.byref(color_value),
                ctypes.sizeof(color_value),
            )
        return True
    except Exception:
        return False
