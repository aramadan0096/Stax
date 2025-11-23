# -*- coding: utf-8 -*-
"""
StaX Init Script for Nuke
Loads on Nuke startup to setup plugin paths
"""

import sys
import os

print("\n" + "="*80)
print("[StaX init.py] Starting initialization...")
print("="*80)

try:
    import nuke
    print("[StaX init.py] [OK] Nuke module imported successfully")
except ImportError as e:
    print("[StaX init.py] [ERROR] ERROR: Failed to import nuke: {}".format(e))
    raise

try:
    # Get the directory where this init.py is located (StaX root)
    stax_root = os.path.dirname(__file__)
    print("[StaX init.py] StaX root directory: {}".format(stax_root))
    
    # Verify directory exists
    if not os.path.exists(stax_root):
        print("[StaX init.py] [ERROR] ERROR: StaX root directory does not exist!")
    else:
        print("[StaX init.py] [OK] StaX root directory verified")
    
    # Add StaX root to plugin path so Nuke can find our modules
    print("[StaX init.py] Adding plugin paths...")
    nuke.pluginAddPath(os.path.join(stax_root, 'plugins', 'dccs', 'nuke'))
    print("[StaX init.py]   [OK] Added: {}".format(os.path.join(stax_root, 'plugins', 'dccs', 'nuke')))
    
    # Add subdirectories to plugin path
    subdirs = ['./tools', './src/ui', './src', './resources', './dependencies/ffpyplayer']
    for subdir in subdirs:
        try:
            nuke.pluginAddPath(subdir)
            full_path = os.path.join(stax_root, subdir.lstrip('./'))
            if os.path.exists(full_path):
                print("[StaX init.py]   [OK] Added: {} (exists)".format(subdir))
            else:
                print("[StaX init.py]   [WARN] Added: {} (NOT FOUND)".format(subdir))
        except Exception as e:
            print("[StaX init.py]   [ERROR] Failed to add {}: {}".format(subdir, e))
    
    # Print final plugin path
    print("[StaX init.py] Final plugin paths:")
    for path in nuke.pluginPath():
        print("[StaX init.py]   - {}".format(path))
    
    # Initialize logger
    print("[StaX init.py] Initializing logger...")
    try:
        # Add stax_root to sys.path temporarily to import logger
        if stax_root not in sys.path:
            sys.path.insert(0, stax_root)
        
        from stax_logger import init_logger
        logger = init_logger()
        logger.info("StaX init.py completed successfully")
        logger.info("Plugin paths configured")
        print("[StaX init.py] [OK] Logger initialized")
    except Exception as e:
        print("[StaX init.py] [WARN] Failed to initialize logger: {}".format(e))
        print("[StaX init.py]   (Continuing without logger)")
    
    print("[StaX init.py] [OK] Initialization complete")
    print("[StaX init.py] Ready to load. Menu will be available after startup.")
    print("="*80 + "\n")

except Exception as e:
    print("\n" + "="*80)
    print("[StaX init.py] [ERROR][ERROR][ERROR] CRITICAL ERROR DURING INITIALIZATION [ERROR][ERROR][ERROR]")
    print("="*80)
    print("[StaX init.py] Error: {}".format(e))
    
    import traceback
    print("[StaX init.py] Full traceback:")
    traceback.print_exc()
    print("="*80 + "\n")
    raise
