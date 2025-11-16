# -*- coding: utf-8 -*-
"""Fix Unicode symbols in debug output for Windows console compatibility"""

import os
import codecs

def fix_unicode_in_file(filepath):
    """Replace Unicode symbols with ASCII equivalents in a file"""
    print("Processing: {}".format(filepath))
    
    # Read file with UTF-8 encoding
    with codecs.open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace Unicode symbols
    replacements = {
        '\u2713': '[OK]',      # ✓
        '\u2717': '[ERROR]',   # ✗
        '\u26a0': '[WARN]',    # ⚠
        '✓': '[OK]',
        '✗': '[ERROR]',
        '⚠': '[WARN]',
    }
    
    original_content = content
    for unicode_char, ascii_replacement in replacements.items():
        content = content.replace(unicode_char, ascii_replacement)
    
    # Write back with ASCII encoding (will work in Nuke's console)
    with codecs.open(filepath, 'w', encoding='ascii', errors='replace') as f:
        f.write(content)
    
    if content != original_content:
        print("  -> Fixed Unicode symbols")
    else:
        print("  -> No changes needed")

def main():
    """Fix Unicode in all Python files"""
    files_to_fix = [
        'init.py',
        'menu.py',
        'nuke_launcher.py',
        'stax_logger.py'
    ]
    
    for filename in files_to_fix:
        filepath = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(filepath):
            fix_unicode_in_file(filepath)
        else:
            print("File not found: {}".format(filepath))
    
    print("\nDone! All files updated for Windows console compatibility.")

if __name__ == '__main__':
    main()
