# Complete Permission Error Fix - All Three Locations

## Overview

This document summarizes the complete resolution of the `PermissionError: [WinError 5] Access is denied` issue that prevented StaX from loading in Nuke on Windows.

## The Problem

When running StaX as a Nuke plugin, **relative paths fail** because:

1. **Nuke's working directory**: `C:\Program Files\Nuke15.2v1\`
2. **StaX installation**: `D:\Scripts\modern-stock-browser\`
3. **Relative paths** like `./data` resolve to `C:\Program Files\Nuke15.2v1\data`
4. **User has no write permissions** to Program Files directory
5. **Result**: `PermissionError` when trying to create directories

## Three Locations Fixed

### 1. Config.ensure_directories() - FIRST FIX
**File:** `src/config.py`  
**Lines:** 165-195  
**Directories affected:** `./data`, `./repository`, `./previews`, `./logs`

**Before:**
```python
for directory in directories:
    if directory and not os.path.exists(directory):
        os.makedirs(directory)  # Fails with relative paths
```

**After:**
```python
for directory in directories:
    if directory and not os.path.exists(directory):
        # Convert relative to absolute
        script_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(script_dir)
        abs_directory = os.path.join(root_dir, directory)
        os.makedirs(abs_directory)
```

### 2. DatabaseManager.__init__() - SECOND FIX
**File:** `src/db_manager.py`  
**Lines:** 37-76  
**Directory affected:** `./data` (database location)

**Before:**
```python
db_dir = os.path.dirname(db_path)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir)  # Fails with './data'
```

**After:**
```python
db_dir = os.path.dirname(db_path)
if db_dir and not os.path.exists(db_dir):
    # Convert relative to absolute
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    abs_db_dir = os.path.join(root_dir, db_dir)
    os.makedirs(abs_db_dir)
    
    # Update internal database path
    self.db_path = os.path.join(root_dir, self.db_path)
    self.lock_file_path = self.db_path + '.lock'
```

### 3. IngestionCore.__init__() - THIRD FIX (Latest)
**File:** `src/ingestion_core.py`  
**Lines:** 314-350  
**Directory affected:** `./previews` (thumbnail storage)

**Before:**
```python
self.preview_dir = config.get('preview_dir', './previews')
if not os.path.exists(self.preview_dir):
    os.makedirs(self.preview_dir)  # Fails with './previews'
```

**After:**
```python
self.preview_dir = config.get('preview_dir', './previews')
if not os.path.exists(self.preview_dir):
    # Convert relative to absolute
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    abs_preview_dir = os.path.join(root_dir, self.preview_dir)
    os.makedirs(abs_preview_dir)
    
    # Update internal preview path
    self.preview_dir = abs_preview_dir
```

## Path Resolution Logic

All three fixes use the same logic:

```python
# 1. Get script location
script_dir = os.path.dirname(os.path.abspath(__file__))
# Example: D:\Scripts\modern-stock-browser\src

# 2. Calculate root directory (one level up from src/)
root_dir = os.path.dirname(script_dir)
# Example: D:\Scripts\modern-stock-browser

# 3. Join with relative path
abs_path = os.path.join(root_dir, relative_path)
# Example: D:\Scripts\modern-stock-browser\previews
```

## Execution Flow

When user presses `Ctrl+Alt+S` in Nuke:

```
1. menu.py calls show_stax_panel()
2. show_stax_panel() calls nukescripts.panels.registerWidgetAsPanel()
3. Nuke instantiates StaXPanel()
4. StaXPanel.__init__() creates Config()
5. Config.ensure_directories() → FIX #1 (creates data/, repository/, previews/, logs/)
6. StaXPanel.__init__() creates DatabaseManager()
7. DatabaseManager.__init__() → FIX #2 (creates data/ and updates db_path)
8. StaXPanel.__init__() creates IngestionCore()
9. IngestionCore.__init__() → FIX #3 (creates previews/ and updates preview_dir)
10. Panel initialization completes successfully!
```

## Expected Console Output

After all three fixes, you should see:

```
[StaXPanel.__init__] Initializing core components...
[StaXPanel.__init__]   [OK] Config initialized

[Config] Creating directory: D:\Scripts\modern-stock-browser\data
[Config]   [OK] Directory created successfully
[Config] Creating directory: D:\Scripts\modern-stock-browser\repository
[Config]   [OK] Directory created successfully
[Config] Creating directory: D:\Scripts\modern-stock-browser\previews
[Config]   [OK] Directory created successfully
[Config] Creating directory: D:\Scripts\modern-stock-browser\logs
[Config]   [OK] Directory created successfully

[StaXPanel.__init__]   [OK] Directories ensured
[StaXPanel.__init__] Database path: ./data/vah.db

[DatabaseManager] Creating database directory: D:\Scripts\modern-stock-browser\data
[DatabaseManager]   [OK] Database directory created
[DatabaseManager] Using absolute database path: D:\Scripts\modern-stock-browser\data\vah.db

[StaXPanel.__init__]   [OK] DatabaseManager initialized
[StaXPanel.__init__] Creating NukeBridge (mock_mode=False)...
[StaXPanel.__init__]   [OK] NukeBridge initialized
[StaXPanel.__init__]   [OK] NukeIntegration initialized

[IngestionCore] Creating preview directory: D:\Scripts\modern-stock-browser\previews
[IngestionCore]   [OK] Preview directory created
[IngestionCore] Using absolute preview path: D:\Scripts\modern-stock-browser\previews

[StaXPanel.__init__]   [OK] IngestionCore initialized
[StaXPanel.__init__]   [OK] ProcessorManager initialized
[StaXPanel.__init__]   [OK] User authentication variables set
[StaXPanel.__init__]   [OK] Window properties set
[StaXPanel.__init__]   [OK] Window icon set
[StaXPanel.__init__] Setting up UI...
[StaXPanel.__init__]   [OK] UI setup complete
[StaXPanel.__init__] NUKE_MODE: Skipping login dialog, auto-login as admin
[StaXPanel.__init__] [OK] Initialization complete!

[show_stax_panel] NUKE_MODE: Skipping stylesheet (using Nuke's default styling)
[show_stax_panel] [OK] Panel registered
[show_stax_panel] [OK] Panel added to pane
[show_stax_panel] [OK] Panel shown successfully
```

## Error Chain Breakdown

### Original Error #1 (Config):
```
PermissionError: [WinError 5] Access is denied: './data'
At: src/config.py, line 172, in ensure_directories
```

### Original Error #2 (DatabaseManager):
```
PermissionError: [WinError 5] Access is denied: './data'
At: src/db_manager.py, line 41, in __init__
```

### Original Error #3 (IngestionCore):
```
PermissionError: [WinError 5] Access is denied: './previews'
At: src/ingestion_core.py, line 328, in __init__
```

### Secondary Error:
```
AttributeError: 'NoneType' object has no attribute 'addToPane'
```
**Cause:** When `registerWidgetAsPanel()` fails during panel construction, it returns `None`. The code then tries to call `.addToPane()` on `None`.  
**Resolution:** Fixed by preventing the primary errors above.

## Testing Instructions

### Complete Test Sequence:

1. **Close Nuke completely**
   - Make sure all Nuke instances are closed
   - This ensures all modules are reloaded with the fixes

2. **Restart Nuke**
   - Launch Nuke 15.2v1 normally

3. **Open StaX Panel**
   - Press `Ctrl+Alt+S` (or use StaX menu → Open StaX Panel)

4. **Verify Console Output**
   - Check Script Editor for the expected debug messages above
   - All directory creation should show absolute paths
   - All operations should show `[OK]` status

5. **Verify Panel Functionality**
   - Panel should appear as a dockable pane in Nuke
   - Stacks/Lists navigation should work
   - No errors in console

6. **Test Basic Operations**
   - Browse existing stacks/lists (if any)
   - Try ingesting a test file (Ctrl+Shift+I)
   - Verify preview generation works

## Files Modified

### Core Fixes:
- `src/config.py` - Config.ensure_directories() method
- `src/db_manager.py` - DatabaseManager.__init__() method  
- `src/ingestion_core.py` - IngestionCore.__init__() method

### Documentation:
- `PERMISSION_FIX.md` - First fix (Config)
- `DB_PATH_FIX.md` - Second fix (DatabaseManager)
- `INGESTION_PATH_FIX.md` - Third fix (IngestionCore)
- `ALL_PERMISSION_FIXES.md` - This comprehensive summary
- `changelog.md` - Updated with all three fixes

## Why Three Separate Fixes Were Needed

Each module **independently** ensures its required directories exist:

1. **Config** ensures all application directories exist during initialization
2. **DatabaseManager** ensures database directory exists before connecting
3. **IngestionCore** ensures preview directory exists before generating thumbnails

This is good defensive programming - each module doesn't assume other modules have created directories it needs. However, it means the relative path bug existed in three places.

## Prevention

To prevent this issue in the future:

1. **Always use absolute paths** when creating directories
2. **Test in Nuke context** early (working directory is different from standalone)
3. **Add debug output** showing resolved paths
4. **Document** execution context differences between standalone and Nuke modes

## Completion Status

✅ **All three permission errors fixed**  
✅ **Documentation complete**  
✅ **Changelog updated**  
✅ **Ready for testing**

## Next Steps

**USER ACTION REQUIRED:**

1. Close Nuke completely
2. Restart Nuke
3. Press Ctrl+Alt+S
4. Report success or any new errors

The panel should now initialize completely without permission errors!
