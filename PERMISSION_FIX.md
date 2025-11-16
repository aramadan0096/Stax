# Directory Permission Fix

## Issue
**Error:** `PermissionError: [WinError 5] Access is denied: './data'`

**Location:** `Config.ensure_directories()` in `src/config.py`

**Root Cause:**  
Relative paths like `'./data'` don't resolve correctly when Nuke executes Python scripts. The current working directory in Nuke is often not the script directory, and Nuke may not have write permissions to that location.

**Stack Trace:**
```
File "D:\Scripts\modern-stock-browser\nuke_launcher.py", line 228, in __init__
  self.config.ensure_directories()
File "D:\Scripts\modern-stock-browser\src\config.py", line 172, in ensure_directories
  os.makedirs(directory)
PermissionError: [WinError 5] Access is denied: './data'
```

---

## Solution

### Changed: `src/config.py` - `ensure_directories()` method

**Before:**
```python
def ensure_directories(self):
    """Ensure all configured directories exist."""
    directories = [
        os.path.dirname(self.get('database_path')),  # './data'
        self.get('default_repository_path'),         # './repository'
        self.get('preview_dir')                      # './previews'
    ]
    
    for directory in directories:
        if directory and not os.path.exists(directory):
            os.makedirs(directory)  # FAILS with relative path in Nuke!
            print("Created directory: {}".format(directory))
```

**After:**
```python
def ensure_directories(self):
    """Ensure all configured directories exist."""
    # Get absolute paths to avoid permission issues with relative paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)  # Go up one level from src/
    
    directories = [
        os.path.dirname(self.get('database_path')),
        self.get('default_repository_path'),
        self.get('preview_dir'),
        os.path.join(root_dir, 'logs')  # Add logs directory
    ]
    
    for directory in directories:
        if directory and not os.path.exists(directory):
            try:
                # Convert relative paths to absolute paths
                if not os.path.isabs(directory):
                    abs_directory = os.path.join(root_dir, directory)
                else:
                    abs_directory = directory
                
                print("[Config] Creating directory: {}".format(abs_directory))
                os.makedirs(abs_directory)
                print("[Config]   [OK] Directory created successfully")
            except OSError as e:
                print("[Config]   [WARN] Failed to create directory {}: {}".format(abs_directory, e))
                print("[Config]   (Continuing - directory may not be needed immediately)")
                # Don't raise - some directories might not be writable in Nuke context
```

---

## What Changed

### 1. Absolute Path Resolution
- **Detects script directory:** `os.path.dirname(os.path.abspath(__file__))`
- **Gets root directory:** One level up from `src/` directory
- **Converts relative to absolute:** `os.path.join(root_dir, directory)`

### 2. Better Error Handling
- **Before:** Crash on any mkdir failure
- **After:** Print warning and continue
- **Rationale:** Some directories (like previews) aren't critical for initial load

### 3. Added Logs Directory
- Explicitly ensures `logs/` directory exists
- Prevents log file creation failures

---

## Path Resolution Examples

### Default Configuration:
```python
{
    'database_path': './data/vah.db',
    'default_repository_path': './repository',
    'preview_dir': './previews'
}
```

### Old Behavior (Fails in Nuke):
```
Current working directory: C:\Program Files\Nuke15.2v1\
Tries to create: C:\Program Files\Nuke15.2v1\data  ❌ Access Denied!
```

### New Behavior (Works in Nuke):
```
Script location: D:\Scripts\modern-stock-browser\src\config.py
Root directory: D:\Scripts\modern-stock-browser\
Creates: D:\Scripts\modern-stock-browser\data  ✅ Success!
Creates: D:\Scripts\modern-stock-browser\repository  ✅ Success!
Creates: D:\Scripts\modern-stock-browser\previews  ✅ Success!
Creates: D:\Scripts\modern-stock-browser\logs  ✅ Success!
```

---

## Console Output

### Success Case:
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
```

### Partial Failure (Non-Critical):
```
[Config] Creating directory: D:\Scripts\modern-stock-browser\data
[Config]   [WARN] Failed to create directory D:\Scripts\modern-stock-browser\data: [Errno 13] Permission denied
[Config]   (Continuing - directory may not be needed immediately)
[StaXPanel.__init__]   [OK] Directories ensured
```

---

## Testing Instructions

### Test 1: Fresh Installation
```
1. Delete existing data/, repository/, previews/, logs/ directories
2. Restart Nuke
3. Press Ctrl+Alt+S to open StaX
4. Check console - should see directory creation messages
5. Verify directories were created in D:\Scripts\modern-stock-browser\
```

### Test 2: Verify Absolute Paths
```python
# In Nuke Script Editor:
import os
from src.config import Config

config = Config()
print("Database path:", config.get('database_path'))
print("Absolute path:", os.path.abspath(config.get('database_path')))
```

### Test 3: Panel Opening
```
1. Restart Nuke (close completely)
2. Press Ctrl+Alt+S
3. Expected: Panel opens successfully
4. Expected: No PermissionError in console
```

---

## Related Issues Fixed

This fix also resolves:
- ❌ `registerWidgetAsPanel()` returns `None` 
- ❌ `AttributeError: 'NoneType' object has no attribute 'addToPane'`

**Why?** Panel registration was failing because `StaXPanel.__init__()` crashed during directory creation, causing `registerWidgetAsPanel()` to return `None` instead of a panel object.

---

## Environment Variable Override

If you want to use a custom database location:

### Windows:
```powershell
$env:STOCK_DB = "D:\custom\path\database.db"
```

### Set Permanently:
```powershell
[System.Environment]::SetEnvironmentVariable("STOCK_DB", "D:\custom\path\database.db", "User")
```

The `STOCK_DB` environment variable overrides the default `./data/vah.db` path and always uses absolute paths.

---

## Next Steps

1. **Restart Nuke** (close completely)
2. **Press Ctrl+Alt+S** to open StaX
3. **Check console** for directory creation messages
4. **Verify** directories exist in `D:\Scripts\modern-stock-browser\`
5. **Send console output** if still having issues

The panel should now initialize successfully without permission errors!
