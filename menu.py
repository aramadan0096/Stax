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
