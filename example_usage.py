# -*- coding: utf-8 -*-
"""
VFX_Asset_Hub - Example Usage
Demonstrates core functionality without GUI
Python 2.7 compatible
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config import Config
from db_manager import DatabaseManager
from ingestion_core import IngestionCore, SequenceDetector
from nuke_bridge import NukeBridge, NukeIntegration
from extensibility_hooks import ProcessorManager


def main():
    """Example usage of VFX_Asset_Hub core modules."""
    
    print("=" * 60)
    print("VFX_Asset_Hub - Core Module Test")
    print("=" * 60)
    
    # Initialize configuration
    print("\n1. Loading configuration...")
    config = Config('./config/config.json')
    config.ensure_directories()
    
    # Initialize database
    print("\n2. Initializing database...")
    db = DatabaseManager(config.get('database_path'))
    
    # Create example stacks and lists
    print("\n3. Creating example stacks and lists...")
    
    # Check if data already exists
    existing_stacks = db.get_all_stacks()
    if not existing_stacks:
        # Create stacks
        plates_stack_id = db.create_stack('Plates', './repository/plates')
        assets_3d_stack_id = db.create_stack('3D Assets', './repository/3d_assets')
        
        # Create lists
        db.create_list(plates_stack_id, 'Cityscape')
        db.create_list(plates_stack_id, 'Explosions')
        db.create_list(assets_3d_stack_id, 'Characters')
        db.create_list(assets_3d_stack_id, 'Props')
        
        print("   Created 2 stacks and 4 lists")
    else:
        print("   Database already contains {} stacks".format(len(existing_stacks)))
    
    # Display stacks and lists
    print("\n4. Current database structure:")
    for stack in db.get_all_stacks():
        print("   Stack: {} ({})".format(stack['name'], stack['path']))
        lists = db.get_lists_by_stack(stack['stack_id'])
        for lst in lists:
            print("      - List: {}".format(lst['name']))
            elements = db.get_elements_by_list(lst['list_id'])
            print("        Elements: {}".format(len(elements)))
    
    # Initialize Nuke bridge in mock mode
    print("\n5. Initializing Nuke bridge (mock mode)...")
    nuke_bridge = NukeBridge(mock_mode=True)
    nuke_integration = NukeIntegration(nuke_bridge, db)
    print("   Mock mode: {}".format(nuke_bridge.mock_mode))
    
    # Test Nuke operations
    print("\n6. Testing Nuke operations...")
    read_node = nuke_bridge.create_read_node(
        filepath='/path/to/shot.####.exr',
        frame_range='1001-1150',
        node_name='TestRead'
    )
    print("   Created node: {}".format(read_node.get('name')))
    
    # Initialize processor manager
    print("\n7. Initializing processor hooks...")
    processor_manager = ProcessorManager(config.get_all())
    hook_status = processor_manager.get_hook_status()
    print("   Pre-ingest hook: {}".format(
        'Enabled' if hook_status['pre_ingest']['enabled'] else 'Disabled'
    ))
    print("   Post-ingest hook: {}".format(
        'Enabled' if hook_status['post_ingest']['enabled'] else 'Disabled'
    ))
    print("   Post-import hook: {}".format(
        'Enabled' if hook_status['post_import']['enabled'] else 'Disabled'
    ))
    
    # Test sequence detection
    print("\n8. Testing sequence detection...")
    test_files = [
        'shot_0001.exr',
        'comp.1001.dpx',
        'render_####.png',
        'single_file.jpg'
    ]
    for filename in test_files:
        # Create a mock path for testing
        test_path = os.path.join('./test', filename)
        result = SequenceDetector.FRAME_PATTERN.match(filename)
        if result:
            print("   {} - Detected pattern: {}".format(
                filename, 
                "{}[padding{}]{}".format(result.group(1), len(result.group(2)), result.group(3))
            ))
        else:
            print("   {} - Not a sequence".format(filename))
    
    # Show history
    print("\n9. Ingestion history:")
    history = db.get_ingestion_history(limit=10)
    if history:
        for entry in history:
            print("   [{status}] {action}: {source_path}".format(**entry))
    else:
        print("   No history entries yet")
    
    print("\n" + "=" * 60)
    print("Core modules initialized successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("  - Run with GUI: python gui_main.py")
    print("  - Configure processors in: {}".format(config.config_path))
    print("  - View database at: {}".format(config.get('database_path')))


if __name__ == '__main__':
    main()
