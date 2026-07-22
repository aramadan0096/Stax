#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick Verification Script - Run this to verify all features work
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def check_config():
    """Verify config has sequence_pattern."""
    from src.config import Config
    config = Config()
    
    print("="*60)
    print("CONFIGURATION CHECK")
    print("="*60)
    
    has_pattern = 'sequence_pattern' in config.config
    auto_detect = config.get('auto_detect_sequences', False)
    pattern = config.get('sequence_pattern', 'NOT SET')
    
    print("✓ Config has 'sequence_pattern' key: {}".format(has_pattern))
    print("✓ Auto-detect enabled: {}".format(auto_detect))
    print("✓ Current pattern: {}".format(pattern))
    
    valid_patterns = ['.####.ext', '_####.ext', ' ####.ext', '-####.ext']
    if pattern in valid_patterns:
        print("✓ Pattern is valid")
    else:
        print("✗ Pattern is invalid (should be one of: {})".format(', '.join(valid_patterns)))
    
    return has_pattern and pattern in valid_patterns


def check_sequence_detector():
    """Verify SequenceDetector has all patterns."""
    from src.ingestion_core import SequenceDetector
    
    print("\n" + "="*60)
    print("SEQUENCE DETECTOR CHECK")
    print("="*60)
    
    has_map = hasattr(SequenceDetector, 'PATTERN_MAP')
    has_order = hasattr(SequenceDetector, 'PATTERN_ORDER')
    
    print("✓ Has PATTERN_MAP: {}".format(has_map))
    print("✓ Has PATTERN_ORDER: {}".format(has_order))
    
    if has_map:
        patterns = SequenceDetector.PATTERN_MAP.keys()
        print("✓ Available patterns: {}".format(', '.join(patterns)))
        
        for pattern_key in patterns:
            info = SequenceDetector.PATTERN_MAP[pattern_key]
            print("  - {}: separator='{}', regex={}".format(
                pattern_key,
                info['separator'],
                'present' if 'regex' in info else 'MISSING'
            ))
    
    return has_map and has_order


def check_ingestion_core():
    """Verify IngestionCore reads pattern from config."""
    from src.config import Config
    from src.db_manager import DatabaseManager
    from src.ingestion_core import IngestionCore
    
    print("\n" + "="*60)
    print("INGESTION CORE CHECK")
    print("="*60)
    
    try:
        config = Config()
        db = DatabaseManager(config.get('database_path'))
        ingest = IngestionCore(db, config.config)
        
        has_auto_detect = hasattr(ingest, 'auto_detect_sequences')
        has_pattern = hasattr(ingest, 'sequence_pattern')
        
        print("✓ Has auto_detect_sequences: {} = {}".format(
            has_auto_detect,
            ingest.auto_detect_sequences if has_auto_detect else 'N/A'
        ))
        print("✓ Has sequence_pattern: {} = {}".format(
            has_pattern,
            ingest.sequence_pattern if has_pattern else 'N/A'
        ))
        
        return has_auto_detect and has_pattern
        
    except Exception as e:
        print("✗ Error initializing IngestionCore: {}".format(e))
        return False


def check_ui_settings():
    """Verify settings panel has pattern combobox."""
    print("\n" + "="*60)
    print("UI SETTINGS CHECK")
    print("="*60)
    
    try:
        # Just check if the file has the right components
        with open('src/ui/settings_panel.py', 'r') as f:
            content = f.read()
        
        has_combo = 'sequence_pattern_combo' in content
        has_toggle = 'on_auto_detect_sequences_toggled' in content
        has_save = 'sequence_pattern' in content and 'save_all_settings' in content
        
        print("✓ Has sequence_pattern_combo: {}".format(has_combo))
        print("✓ Has toggle handler: {}".format(has_toggle))
        print("✓ Saves sequence_pattern: {}".format(has_save))
        
        return has_combo and has_toggle and has_save
        
    except Exception as e:
        print("✗ Error checking settings panel: {}".format(e))
        return False


def main():
    """Run all checks."""
    print("\n" + "="*80)
    print(" "*20 + "STAX FEATURE VERIFICATION")
    print("="*80 + "\n")
    
    results = {
        'Configuration': check_config(),
        'Sequence Detector': check_sequence_detector(),
        'Ingestion Core': check_ingestion_core(),
        'UI Settings': check_ui_settings()
    }
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    all_passed = True
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print("{}: {}".format(name, status))
        if not passed:
            all_passed = False
    
    print("\n" + "="*80)
    if all_passed:
        print(" "*20 + "✓ ALL CHECKS PASSED!")
        print("\nYou can now:")
        print("1. Open Settings → Ingestion tab")
        print("2. Select your preferred sequence pattern")
        print("3. Drag/drop or bulk ingest image sequences")
        print("4. Sequences will auto-group based on pattern")
    else:
        print(" "*20 + "✗ SOME CHECKS FAILED")
        print("\nPlease review the errors above and fix any issues.")
    print("="*80 + "\n")
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
