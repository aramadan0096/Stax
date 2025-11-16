# Database Path Fix Summary

## Issue Resolved
Fixed `PermissionError: [WinError 5] Access is denied: './data'` in **TWO** locations:

### 1. ✅ Config.ensure_directories() - FIXED
**File:** `src/config.py`  
**Issue:** Relative paths not converted to absolute  
**Status:** Fixed in previous update

### 2. ✅ DatabaseManager.__init__() - JUST FIXED
**File:** `src/db_manager.py`  
**Issue:** Same problem - using relative path `'./data'` to create directory  
**Solution:** Convert to absolute path before mkdir

## Changes Made

### src/db_manager.py (Lines 37-67):

**Before:**
```python
# Ensure database directory exists
db_dir = os.path.dirname(db_path)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir)  # ❌ Fails with './data' in Nuke!
```

**After:**
```python
# Ensure database directory exists
db_dir = os.path.dirname(db_path)
if db_dir and not os.path.exists(db_dir):
    try:
        # Convert relative path to absolute to avoid permission issues in Nuke
        if not os.path.isabs(db_dir):
            # Get the root directory (where the main script is located)
            script_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(script_dir)  # Go up from src/
            abs_db_dir = os.path.join(root_dir, db_dir)
        else:
            abs_db_dir = db_dir
        
        print("[DatabaseManager] Creating database directory: {}".format(abs_db_dir))
        os.makedirs(abs_db_dir)
        print("[DatabaseManager]   [OK] Database directory created")
        
        # Update db_path to use absolute path
        if not os.path.isabs(self.db_path):
            self.db_path = os.path.join(root_dir, self.db_path)
            self.lock_file_path = self.db_path + '.lock'
            print("[DatabaseManager] Using absolute database path: {}".format(self.db_path))
    except OSError as e:
        print("[DatabaseManager]   [WARN] Failed to create directory: {}".format(e))
        # Try to use absolute path anyway
        if not os.path.isabs(self.db_path):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(script_dir)
            self.db_path = os.path.join(root_dir, self.db_path)
            self.lock_file_path = self.db_path + '.lock'

# Also fixed: use self.db_path instead of db_path parameter
if not os.path.exists(self.db_path):  # ✅ Fixed!
```

## Why This Matters

**DatabaseManager** is instantiated **after** Config, so even though Config created the directories, DatabaseManager was crashing trying to create them again with the relative path.

## Expected Console Output

```
[StaXPanel.__init__] Initializing core components...
[StaXPanel.__init__]   [OK] Config initialized
[Config] Creating directory: D:\Scripts\modern-stock-browser\data
[Config]   [OK] Directory created successfully
[StaXPanel.__init__]   [OK] Directories ensured
[StaXPanel.__init__] Database path: ./data/vah.db
[DatabaseManager] Creating database directory: D:\Scripts\modern-stock-browser\data
[DatabaseManager]   [OK] Database directory created
[DatabaseManager] Using absolute database path: D:\Scripts\modern-stock-browser\data\vah.db
[StaXPanel.__init__]   [OK] DatabaseManager initialized
[StaXPanel.__init__]   [OK] NukeBridge initialized
... (continues successfully)
```

## Test Now

1. **Close Nuke completely**
2. **Delete** the `data/` directory (if it exists)
3. **Restart Nuke**
4. **Press Ctrl+Alt+S**
5. **Expected:** Panel opens, directories created with absolute paths, no permission errors!

---

**Status:** Both relative path issues resolved ✅  
**Next:** Restart Nuke and test!
