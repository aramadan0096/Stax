# -*- coding: utf-8 -*-
"""
Test script for nuke_launcher.py
Tests StaX panel in standalone mode (simulating Nuke environment)
"""

import sys
from PySide2 import QtWidgets

# Import the nuke launcher
import nuke_launcher

def test_stax_panel():
    """Test launching StaX panel in standalone mode."""
    print("\n=== StaX Nuke Launcher Test ===\n")
    
    # Check if running in Nuke mode
    print("Nuke mode detected: {}".format(nuke_launcher.NUKE_MODE))
    
    # Create Qt application
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)
    
    print("Creating StaXPanel...")
    
    # Create panel
    panel = nuke_launcher.StaXPanel()
    
    print("Panel created successfully!")
    print("Panel size: {}x{}".format(panel.width(), panel.height()))
    print("Panel title: {}".format(panel.windowTitle()))
    
    # Show panel
    panel.show()
    
    print("\nPanel displayed. Close the window to end test.\n")
    print("Test Controls:")
    print("  - Login dialog should appear")
    print("  - Toolbar should have all action buttons")
    print("  - Try browsing stacks/lists")
    print("  - Try ingesting a file")
    print("  - Check if video preview works")
    
    # Run event loop
    sys.exit(app.exec_())


if __name__ == '__main__':
    test_stax_panel()
