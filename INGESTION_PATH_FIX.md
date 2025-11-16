# IngestionCore Preview Directory Permission Fix

## Issue Resolved

**Third location of permission error** discovered in `src/ingestion_core.py`:

```
PermissionError: [WinError 5] Access is denied: './previews'
```

## Root Cause

The `IngestionCore.__init__()` method was creating the preview directory using a relative path:

```python
self.preview_dir = config.get('preview_dir', './previews')
if not os.path.exists(self.preview_dir):
    os.makedirs(self.preview_dir)  # Fails in Nuke context
```

In Nuke's execution context:
- Current working directory: `C:\Program Files\Nuke15.2v1\`
- Relative path `./previews` resolves to: `C:\Program Files\Nuke15.2v1\previews`
- Result: **Permission denied** (no write access to Program Files)

## Solution Applied

Updated `src/ingestion_core.py` lines 314-328 to convert relative paths to absolute:

### Before:
```python
def __init__(self, db_manager, config):
    self.db = db_manager
    self.config = config
    self.preview_dir = config.get('preview_dir', './previews')
    
    # Ensure preview directory exists
    if not os.path.exists(self.preview_dir):
        os.makedirs(self.preview_dir)
```

### After:
```python
def __init__(self, db_manager, config):
    self.db = db_manager
    self.config = config
    self.preview_dir = config.get('preview_dir', './previews')
    
    # Ensure preview directory exists
    if not os.path.exists(self.preview_dir):
        try:
            # Convert relative path to absolute to avoid permission issues in Nuke
            if not os.path.isabs(self.preview_dir):
                # Get the root directory (where the main script is located)
                script_dir = os.path.dirname(os.path.abspath(__file__))
                root_dir = os.path.dirname(script_dir)  # Go up from src/
                abs_preview_dir = os.path.join(root_dir, self.preview_dir)
            else:
                abs_preview_dir = self.preview_dir
            
            print("[IngestionCore] Creating preview directory: {}".format(abs_preview_dir))
            os.makedirs(abs_preview_dir)
            print("[IngestionCore]   [OK] Preview directory created")
            
            # Update preview_dir to use absolute path
            self.preview_dir = abs_preview_dir
            print("[IngestionCore] Using absolute preview path: {}".format(self.preview_dir))
        except OSError as e:
            print("[IngestionCore]   [WARN] Failed to create preview directory: {}".format(e))
            # Try to use absolute path anyway
            if not os.path.isabs(self.preview_dir):
                script_dir = os.path.dirname(os.path.abspath(__file__))
                root_dir = os.path.dirname(script_dir)
                self.preview_dir = os.path.join(root_dir, self.preview_dir)
```

## Path Resolution Example

**Before fix:**
```
Preview directory: ./previews
Resolved to: C:\Program Files\Nuke15.2v1\previews
Result: PermissionError
```

**After fix:**
```
Script location: D:\Scripts\modern-stock-browser\src\ingestion_core.py
Root directory: D:\Scripts\modern-stock-browser\
Preview directory: ./previews
Resolved to: D:\Scripts\modern-stock-browser\previews
Result: Success! (user has write permissions)
```

## Expected Console Output

When StaX panel initializes in Nuke, you should now see:

```
[StaXPanel.__init__] Initializing core components...
[StaXPanel.__init__]   [OK] Config initialized
[Config] Creating directory: D:\Scripts\modern-stock-browser\data
[Config]   [OK] Directory created successfully
...
[DatabaseManager] Using absolute database path: D:\Scripts\modern-stock-browser\data\vah.db
[StaXPanel.__init__]   [OK] DatabaseManager initialized
[IngestionCore] Creating preview directory: D:\Scripts\modern-stock-browser\previews
[IngestionCore]   [OK] Preview directory created
[IngestionCore] Using absolute preview path: D:\Scripts\modern-stock-browser\previews
[StaXPanel.__init__]   [OK] IngestionCore initialized
...
[show_stax_panel] [OK] Panel shown successfully
```

## Summary of All Permission Fixes

We've now fixed **three separate locations** with the same relative path issue:

1. **`src/config.py`** - `Config.ensure_directories()` method
   - Fixed: `./data`, `./repository`, `./previews`, `./logs`
   
2. **`src/db_manager.py`** - `DatabaseManager.__init__()` method
   - Fixed: `./data` (database directory)
   
3. **`src/ingestion_core.py`** - `IngestionCore.__init__()` method (THIS FIX)
   - Fixed: `./previews` (preview directory)

All three modules now properly convert relative paths to absolute paths before creating directories, ensuring compatibility with Nuke's execution context.

## Test Now

1. **Close Nuke completely** (very important!)
2. **Restart Nuke**
3. **Press `Ctrl+Alt+S`** to open StaX panel
4. **Check console output** for the new debug messages above
5. **Panel should open successfully** without permission errors

The panel should now initialize completely and be ready to use!
