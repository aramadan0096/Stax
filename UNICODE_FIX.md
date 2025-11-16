# Unicode Character Fix

## Issue
**Problem:** Nuke's Python console on Windows uses CP1252 encoding, which doesn't support Unicode characters like ✓ (U+2713), ✗ (U+2717), and ⚠ (U+26A0).

**Error:**
```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2713' in position 15: character maps to <undefined>
```

## Solution
Replaced all Unicode symbols with ASCII equivalents:

- `✓` → `[OK]`
- `✗` → `[ERROR]`
- `⚠` → `[WARN]`

## Files Updated
- `init.py` - Plugin initialization
- `menu.py` - Menu creation
- `nuke_launcher.py` - Panel implementation
- `stax_logger.py` - Logging system
- `DEBUGGING_QUICK_REFERENCE.md` - Documentation
- `DEBUGGING_SESSION_SUMMARY.md` - Documentation

## How to Apply
Run the `fix_unicode.py` script:
```bash
cd D:\Scripts\modern-stock-browser
python fix_unicode.py
```

This ensures all print statements use Windows-compatible ASCII characters.

## Testing in Nuke
After applying the fix, restart Nuke. You should now see:
```
[StaX init.py] [OK] Nuke module imported successfully
[StaX menu.py] [OK] Menu created successfully
```

Instead of the Unicode error.
