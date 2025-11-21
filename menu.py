# -*- coding: utf-8 -*-
"""
StaX Menu Configuration for Nuke
Adds StaX panel to Nuke's menu system
"""

import sys
import os

import dependency_bootstrap

dependency_bootstrap.bootstrap()

print("\n" + "="*80)
print("[StaX menu.py] Starting menu configuration...")
print("="*80)

try:
    import nuke
    print("[StaX menu.py] [OK] Nuke module imported")
except ImportError as e:
    print("[StaX menu.py] [ERROR] ERROR: Failed to import nuke: {}".format(e))
    raise

try:
    import nukescripts
    print("[StaX menu.py] [OK] nukescripts module imported")
except ImportError as e:
    print("[StaX menu.py] [ERROR] ERROR: Failed to import nukescripts: {}".format(e))
    raise

try:
    # Initialize logger
    print("[StaX menu.py] Initializing logger...")
    stax_root = os.path.dirname(__file__)
    if stax_root not in sys.path:
        sys.path.insert(0, stax_root)
    
    from stax_logger import get_logger
    logger = get_logger()
    logger.info("="*80)
    logger.info("StaX menu.py starting")
    logger.info("="*80)
    print("[StaX menu.py] [OK] Logger ready")

except Exception as e:
    print("[StaX menu.py] [WARN] Logger initialization failed: {}".format(e))
    print("[StaX menu.py]   (Continuing without logger)")
    logger = None

try:
    # Get the main Nuke menu
    print("[StaX menu.py] Getting Nuke menu...")
    nuke_menu = nuke.menu('Nuke')
    if logger:
        logger.info("Retrieved Nuke menu")
    print("[StaX menu.py] [OK] Got Nuke menu")

    # Create custom menu for StaX
    print("[StaX menu.py] Creating StaX menu...")
    stax_menu = nuke_menu.addMenu('StaX')
    if logger:
        logger.info("Created StaX menu")
    print("[StaX menu.py] [OK] Created StaX menu")

    # Add panel command
    print("[StaX menu.py] Adding menu commands...")
    
    # Command 1: Open StaX Panel
    try:
        stax_menu.addCommand(
            'Open StaX Panel',
            'import nuke_launcher; nuke_launcher.show_stax_panel()',
            'Ctrl+Alt+S',
            icon='folder.png'
        )
        if logger:
            logger.info("Added command: Open StaX Panel (Ctrl+Alt+S)")
        print("[StaX menu.py]   [OK] Open StaX Panel (Ctrl+Alt+S)")
    except Exception as e:
        print("[StaX menu.py]   [ERROR] Failed to add 'Open StaX Panel': {}".format(e))
        if logger:
            logger.error("Failed to add 'Open StaX Panel': {}".format(e))

    # Add separator
    try:
        stax_menu.addSeparator()
        print("[StaX menu.py]   [OK] Added separator")
    except Exception as e:
        print("[StaX menu.py]   [WARN] Failed to add separator: {}".format(e))

    # Command 2: Quick Ingest
    try:
        stax_menu.addCommand(
            'Quick Ingest...',
            'import nuke_launcher; panel = nuke_launcher.show_stax_panel(); panel.ingest_files()',
            'Ctrl+Shift+I'
        )
        if logger:
            logger.info("Added command: Quick Ingest (Ctrl+Shift+I)")
        print("[StaX menu.py]   [OK] Quick Ingest... (Ctrl+Shift+I)")
    except Exception as e:
        print("[StaX menu.py]   [ERROR] Failed to add 'Quick Ingest': {}".format(e))
        if logger:
            logger.error("Failed to add 'Quick Ingest': {}".format(e))

    # Command 3: Register Toolset
    try:
        stax_menu.addCommand(
            'Register Toolset...',
            'import nuke_launcher; panel = nuke_launcher.show_stax_panel(); panel.register_toolset()',
            'Ctrl+Shift+T'
        )
        if logger:
            logger.info("Added command: Register Toolset (Ctrl+Shift+T)")
        print("[StaX menu.py]   [OK] Register Toolset... (Ctrl+Shift+T)")
    except Exception as e:
        print("[StaX menu.py]   [ERROR] Failed to add 'Register Toolset': {}".format(e))
        if logger:
            logger.error("Failed to add 'Register Toolset': {}".format(e))

    # Command 4: Advanced Search
    try:
        stax_menu.addCommand(
            'Advanced Search...',
            'import nuke_launcher; panel = nuke_launcher.show_stax_panel(); panel.show_advanced_search()',
            'Ctrl+F'
        )
        if logger:
            logger.info("Added command: Advanced Search (Ctrl+F)")
        print("[StaX menu.py]   [OK] Advanced Search... (Ctrl+F)")
    except Exception as e:
        print("[StaX menu.py]   [ERROR] Failed to add 'Advanced Search': {}".format(e))
        if logger:
            logger.error("Failed to add 'Advanced Search': {}".format(e))

    # Register StaX panel in the Pane menu (dockable panel)
    try:
        print("[StaX menu.py] Setting up StaX panel in Pane menu...")

        class StaXPanelKnob(object):
            """Wrapper for creating StaXPanel widgets inside a Nuke PythonPanel."""

            def makeUI(self):
                print("[StaX menu.py]   [Pane] Creating StaXPanel widget...")
                try:
                    from nuke_launcher import StaXPanel as _StaXPanelWidget
                    self._widget = _StaXPanelWidget()
                    if logger:
                        logger.info("StaXPanel widget created via Pane knob")
                    return self._widget
                except Exception as knob_error:
                    print("[StaX menu.py]   [Pane][ERROR] Failed to create StaXPanel widget: {}".format(knob_error))
                    if logger:
                        logger.exception("Failed to create StaXPanel widget inside StaXPanelKnob.makeUI")
                    raise

        class StaXPanePythonPanel(nukescripts.PythonPanel):
            """PythonPanel wrapper that embeds StaXPanel using PyCustom_Knob."""

            def __init__(self):
                nukescripts.PythonPanel.__init__(
                    self,
                    title="StaX",
                    id="uk.co.thefoundry.StaXPanel"
                )
                try:
                    self._custom_knob = nuke.PyCustom_Knob("", "", "StaXPanelKnob()")
                    self.addKnob(self._custom_knob)
                    if logger:
                        logger.info("StaX Pane PythonPanel initialized with PyCustom_Knob")
                except Exception as panel_error:
                    print("[StaX menu.py]   [Pane][ERROR] Failed to initialize StaXPanePythonPanel: {}".format(panel_error))
                    if logger:
                        logger.exception("Failed to initialize StaXPanePythonPanel")
                    raise

        stax_panel_instance = StaXPanePythonPanel()
        nuke.menu('Pane').addCommand("StaX", "stax_panel_instance.addToPane()")
        print("[StaX menu.py]   [OK] StaX panel registered in Pane menu")
        if logger:
            logger.info("StaX panel registered in Pane menu")

    except Exception as pane_error:
        print("[StaX menu.py]   [ERROR] Failed to register StaX panel in Pane menu: {}".format(pane_error))
        if logger:
            logger.error("Failed to register StaX panel in Pane menu: {}".format(pane_error))

    print("[StaX menu.py] [OK] Menu installed successfully")
    print("[StaX menu.py] Press Ctrl+Alt+S to open StaX panel")
    
    if logger:
        logger.info("Menu configuration completed successfully")
        logger.separator()
    
    print("="*80 + "\n")

except Exception as e:
    print("\n" + "="*80)
    print("[StaX menu.py] [ERROR][ERROR][ERROR] CRITICAL ERROR IN MENU CONFIGURATION [ERROR][ERROR][ERROR]")
    print("="*80)
    print("[StaX menu.py] Error: {}".format(e))
    
    import traceback
    print("[StaX menu.py] Full traceback:")
    traceback.print_exc()
    
    if logger:
        logger.critical("Menu configuration failed")
        logger.exception("Error in menu.py")
    
    print("="*80 + "\n")
    raise
