# StaX Debugging Session Summary

**Date:** Current Session  
**Issue:** Nuke crashes when opening StaX panel  
**Objective:** Add comprehensive debugging to identify crash cause

---

## Problem Statement

User reported: "there are something wrong since nuke craches once I open StaX, please implement any debugging, printing or log functions for detecting the issues"

**Symptoms:**
- Nuke crashes when pressing `Ctrl+Alt+S` (Open StaX Panel)
- No error messages visible to user
- Crash occurs during panel initialization or opening

**Suspected Causes:**
1. Module import failure (PySide2, src modules, UI widgets)
2. Qt application conflicts (Nuke already has QApplication)
3. Database connection issues on first access
4. Missing dependencies or file paths
5. PySide2 version incompatibility

---

## Solution Implemented

### 1. Centralized Logging Infrastructure

**Created: `stax_logger.py` (160 lines)**

```python
class StaXLogger:
    """Centralized logging for StaX with dual output (console + file)."""
    
    def __init__(self):
        self.log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = os.path.join(self.log_dir, 'stax_{}.log'.format(timestamp))
```

**Features:**
- **Dual Output**: Console (print) + timestamped log files
- **Log Levels**: debug, info, warning, error, critical, exception
- **Automatic Tracebacks**: `exception()` method captures full stack traces
- **Log Location**: `logs/stax_YYYYMMDD_HHMMSS.log`
- **Format**: `[HH:MM:SS.mmm] [LEVEL] message`
- **Singleton Pattern**: `get_logger()` returns shared instance

**Usage Example:**
```python
logger = get_logger()
logger.info("Operation started")
try:
    risky_operation()
except Exception as e:
    logger.exception("Operation failed")  # Auto-captures traceback
```

---

### 2. Init Script Debugging (`init.py`)

**Updated: 78 lines (was ~20 lines)**

**Additions:**
- Logger initialization at module load
- Plugin path verification with `os.path.exists()` checks
- Success/failure indicators: ✓ ✗ ⚠
- Full plugin path listing output
- Critical error handler with traceback

**Example Output:**
```
[init.py] StaX Plugin Initialization
==================================================
[init.py] Logger initialized
[init.py] Plugin base directory: C:\Users\user\.nuke\StaX
[init.py] ✓ Base directory exists
[init.py] Adding plugin paths...
[init.py]   ✓ Added: C:\Users\user\.nuke\StaX\src
[init.py]   ✓ Added: C:\Users\user\.nuke\StaX\resources
[init.py]   ✓ Added: C:\Users\user\.nuke\StaX\tools
[init.py] Nuke plugin paths:
  - C:\Users\user\.nuke\StaX\src
  - C:\Users\user\.nuke\StaX\resources
  - C:\Users\user\.nuke\StaX\tools
[init.py] ✓ Initialization complete
```

**What This Catches:**
- Missing plugin directories
- Incorrect installation path
- Permission issues accessing directories
- Plugin path configuration failures

---

### 3. Menu Configuration Debugging (`menu.py`)

**Updated: 139 lines (was ~80 lines)**

**Additions:**
- Logger initialization
- Per-command try/except blocks
- Individual success/failure reporting
- Critical error section with full traceback
- Continues even if individual commands fail

**Example Output:**
```
[menu.py] Creating StaX Menu
========================================
[menu.py] Logger initialized
[menu.py] Creating top-level 'StaX' menu...
[menu.py]   ✓ Menu created
[menu.py] Adding menu commands...
[menu.py]   ✓ Added: Open StaX Panel (Ctrl+Alt+S)
[menu.py]   ✓ Added: Quick Ingest (Ctrl+Shift+I)
[menu.py]   ✓ Added separator
[menu.py]   ✓ Added: Register Toolset (Ctrl+Shift+T)
[menu.py]   ✓ Added: Advanced Search (Ctrl+F)
[menu.py] ✓ StaX menu configuration complete
```

**What This Catches:**
- Menu creation failures
- Command registration errors
- Icon loading problems
- Keyboard shortcut conflicts
- Import errors in nuke_launcher module

---

### 4. Nuke Launcher Import Debugging (`nuke_launcher.py`)

**Updated: Import section now ~200 lines (was ~50 lines)**

**Additions:**
- Logger initialization at module load
- PySide2 import with error handling
- Nuke environment detection logging
- sys.path configuration logging
- **Every import wrapped individually** in try/except
- Progress indicators for each import
- Immediate failure if critical import fails

**Example Output:**
```
==================================================
[nuke_launcher] Module Load Starting
==================================================
[nuke_launcher] Initializing logger...
[nuke_launcher]   ✓ Logger initialized
[nuke_launcher] Importing PySide2...
[nuke_launcher]   ✓ PySide2 imported
[nuke_launcher] Detecting Nuke environment...
[nuke_launcher]   NUKE_MODE = True (running in Nuke)
[nuke_launcher] Configuring sys.path...
[nuke_launcher]   ✓ sys.path configured (3 paths added)
[nuke_launcher] Importing core modules...
[nuke_launcher]   ✓ Config
[nuke_launcher]   ✓ DatabaseManager
[nuke_launcher]   ✓ IngestionCore
[nuke_launcher]   ✓ NukeBridge
[nuke_launcher]   ✓ NukeIntegration
[nuke_launcher]   ✓ ProcessorManager
[nuke_launcher] Importing UI modules...
[nuke_launcher]   ✓ AdvancedSearchDialog
[nuke_launcher]   ✓ AddStackDialog
[nuke_launcher]   ✓ AddListDialog
... (16 widgets total)
[nuke_launcher]   ✓ All UI modules imported (16 widgets)
[nuke_launcher] ✓ All imports successful
==================================================
```

**What This Catches:**
- Missing Python dependencies
- PySide2 version incompatibility
- Import errors in src/ modules
- UI widget import failures
- Path configuration issues

---

### 5. StaXPanel Initialization Debugging

**Updated: `StaXPanel.__init__()` method now ~150 lines (was ~40 lines)**

**Additions:**
- Initialization start/complete markers
- QWidget superclass initialization tracking
- **Every component creation wrapped in try/except**:
  - Config initialization
  - Directory creation
  - Mock mode configuration
  - DatabaseManager initialization
  - NukeBridge creation
  - NukeIntegration setup
  - IngestionCore initialization
  - ProcessorManager setup
- Window property setting tracking
- Icon loading with fallback
- UI setup tracking
- Login dialog scheduling tracking

**Example Output:**
```
[StaXPanel.__init__] Initialization started...
================================================================================
[StaXPanel.__init__]   ✓ QWidget superclass initialized
[StaXPanel.__init__] Initializing core components...
[StaXPanel.__init__]   ✓ Config initialized
[StaXPanel.__init__]   ✓ Directories ensured
[StaXPanel.__init__] Disabling mock mode (running in Nuke)
[StaXPanel.__init__] Database path: D:\data\vah.db
[StaXPanel.__init__]   ✓ DatabaseManager initialized
[StaXPanel.__init__] Creating NukeBridge (mock_mode=False)...
[StaXPanel.__init__]   ✓ NukeBridge initialized
[StaXPanel.__init__]   ✓ NukeIntegration initialized
[StaXPanel.__init__]   ✓ IngestionCore initialized
[StaXPanel.__init__]   ✓ ProcessorManager initialized
[StaXPanel.__init__]   ✓ User authentication variables set
[StaXPanel.__init__]   ✓ Window properties set
[StaXPanel.__init__]   ✓ Window icon set
[StaXPanel.__init__] Setting up UI...
[StaXPanel.__init__]   ✓ UI setup complete
[StaXPanel.__init__] Scheduling login dialog...
[StaXPanel.__init__]   ✓ Login dialog scheduled
[StaXPanel.__init__] ✓ Initialization complete!
```

**What This Catches:**
- Config file loading errors
- Database connection failures
- Directory permission issues
- NukeBridge initialization problems
- Component instantiation failures
- UI setup errors
- QTimer scheduling issues

---

### 6. Panel Registration Debugging (`show_stax_panel()`)

**Updated: Function now ~100 lines (was ~30 lines)**

**Additions:**
- Function entry/exit logging
- QApplication instance detection
- Stylesheet loading with file checks
- NUKE_MODE verification
- nukescripts.panels.registerWidgetAsPanel() tracking
- addToPane() tracking
- Fallback error handling
- Standalone mode debugging

**Example Output:**
```
================================================================================
[show_stax_panel] Function called
================================================================================
[show_stax_panel] Getting QApplication instance...
[show_stax_panel]   ✓ QApplication instance found
[show_stax_panel] Loading stylesheet...
[show_stax_panel] Stylesheet path: C:\Users\user\.nuke\StaX\resources\style.qss
[show_stax_panel]   ✓ Stylesheet file exists
[show_stax_panel]   ✓ Stylesheet applied (1234 chars)
[show_stax_panel] Checking NUKE_MODE: True
[show_stax_panel] Using nukescripts.panels.registerWidgetAsPanel...
[show_stax_panel] Calling registerWidgetAsPanel('nuke_launcher.StaXPanel', ...)
[show_stax_panel]   ✓ Panel registered
[show_stax_panel] Adding panel to pane...
[show_stax_panel]   ✓ Panel added to pane
[show_stax_panel] ✓ Panel shown successfully
================================================================================
```

**What This Catches:**
- QApplication conflicts
- Stylesheet loading failures
- nukescripts API errors
- Panel registration failures
- Pane addition problems
- Fallback dialog creation issues

---

### 7. Main Function Debugging

**Updated: `main()` function for standalone testing**

**Additions:**
- QApplication creation/retrieval tracking
- Panel creation monitoring
- Panel display tracking
- Qt event loop execution logging
- Exit code reporting

**Example Output:**
```
================================================================================
[main] Standalone launcher starting
================================================================================
[main] Getting/creating QApplication...
[main]   Creating new QApplication instance...
[main]   ✓ QApplication created
[main] Creating StaXPanel...
[main]   ✓ StaXPanel created
[main] Showing panel...
[main]   ✓ Panel shown
[main] Starting Qt event loop...
================================================================================

... (app runs) ...

[main] Qt event loop exited with code: 0
```

---

## Debugging Workflow

### Phase 1: Initial Load (Nuke Startup)
```
Nuke starts
↓
init.py executes
  - Verifies plugin paths
  - Adds src/, resources/, tools/ to sys.path
  - Logs all operations
↓
menu.py executes
  - Creates StaX menu
  - Registers 4 commands
  - Logs each command registration
↓
nuke_launcher.py loads (module import)
  - Imports PySide2
  - Detects Nuke environment
  - Imports all src/ modules
  - Imports all UI widgets
  - Logs every import step
```

### Phase 2: Panel Opening (User Action)
```
User presses Ctrl+Alt+S
↓
menu.py calls nuke_launcher.show_stax_panel()
↓
show_stax_panel() function
  - Gets QApplication instance
  - Loads stylesheet
  - Calls registerWidgetAsPanel()
    ↓
    StaXPanel.__init__() executes
      - Initializes QWidget
      - Creates Config
      - Connects to Database
      - Creates NukeBridge
      - Sets up UI
      - Schedules login dialog
    ↓
  - Adds panel to pane
  - Returns panel object
```

### Phase 3: Crash Analysis

**If crash occurs, check log file in `logs/` directory:**

1. **Last successful operation** - Find the last ✓ marker
2. **First failure** - Find the first ✗ marker
3. **Exception details** - Review full traceback
4. **Component responsible** - Identify module/class/function

**Common crash locations:**
- Import phase: Missing dependency
- Database init: File lock or permission issue
- NukeBridge: Nuke API version mismatch
- UI setup: Qt widget compatibility issue
- Panel registration: nukescripts API problem

---

## Log File Structure

**Location:** `logs/stax_YYYYMMDD_HHMMSS.log`

**Example Log File:**
```
[10:23:45.123] [INFO] ================================================================================
[10:23:45.124] [INFO] init.py - StaX Plugin Initialization
[10:23:45.125] [INFO] ================================================================================
[10:23:45.126] [INFO] Logger initialized
[10:23:45.127] [INFO] Plugin base directory: C:\Users\user\.nuke\StaX
[10:23:45.128] [INFO] Base directory exists: True
[10:23:45.129] [INFO] Added plugin path: C:\Users\user\.nuke\StaX\src
[10:23:45.130] [INFO] Added plugin path: C:\Users\user\.nuke\StaX\resources
[10:23:45.131] [INFO] Added plugin path: C:\Users\user\.nuke\StaX\tools
[10:23:45.132] [INFO] ================================================================================
[10:23:45.133] [INFO] menu.py - Creating StaX Menu
[10:23:45.134] [INFO] ================================================================================
[10:23:45.135] [INFO] Logger initialized
[10:23:45.136] [INFO] Creating top-level 'StaX' menu
[10:23:45.137] [INFO] Menu created successfully
[10:23:45.138] [INFO] Adding menu command: Open StaX Panel
... (continues with all operations)
[10:23:46.456] [ERROR] Failed to initialize DatabaseManager
[10:23:46.457] [ERROR] Traceback (most recent call last):
[10:23:46.458] [ERROR]   File "nuke_launcher.py", line 234, in __init__
[10:23:46.459] [ERROR]     self.db = DatabaseManager(db_path)
[10:23:46.460] [ERROR]   File "db_manager.py", line 45, in __init__
[10:23:46.461] [ERROR]     self.conn = sqlite3.connect(db_path)
[10:23:46.462] [ERROR] sqlite3.OperationalError: unable to open database file
```

---

## Testing Instructions

### Test 1: Installation Verification
```
1. Copy StaX to ~/.nuke/StaX/
2. Restart Nuke
3. Check Script Editor output for init.py messages
4. Verify all plugin paths show ✓ markers
```

### Test 2: Menu Creation
```
1. After Nuke starts, check top menu bar
2. Look for "StaX" menu
3. Check Script Editor for menu.py success messages
4. Verify all 4 commands show ✓ markers
```

### Test 3: Panel Opening
```
1. Press Ctrl+Alt+S or use StaX > Open StaX Panel
2. Watch Script Editor for show_stax_panel() output
3. Watch Script Editor for StaXPanel.__init__() output
4. If crash occurs, check logs/ directory for crash log
```

### Test 4: Log File Review
```
1. Navigate to StaX/logs/ directory
2. Find most recent log file (sorted by timestamp)
3. Open in text editor
4. Search for "[ERROR]" or "[CRITICAL]"
5. Review traceback for crash cause
```

---

## Known Issues & Solutions

### Issue 1: Database Lock Error
**Symptom:** `sqlite3.OperationalError: database is locked`  
**Log shows:** DatabaseManager initialization fails  
**Solution:** Check if database file is open elsewhere, implement file locking

### Issue 2: Missing PySide2
**Symptom:** `ImportError: No module named PySide2`  
**Log shows:** First import in nuke_launcher.py fails  
**Solution:** Install PySide2 for Nuke's Python interpreter

### Issue 3: Qt Application Conflict
**Symptom:** `RuntimeError: A QApplication instance already exists`  
**Log shows:** QApplication.instance() returns existing instance  
**Solution:** Use existing instance (already implemented)

### Issue 4: nukescripts API Error
**Symptom:** `AttributeError: 'module' object has no attribute 'panels'`  
**Log shows:** registerWidgetAsPanel() fails  
**Solution:** Check Nuke version, nukescripts availability

### Issue 5: Permission Denied
**Symptom:** `IOError: [Errno 13] Permission denied`  
**Log shows:** Directory creation or file access fails  
**Solution:** Check file/folder permissions for logs/ and data/ directories

---

## Next Steps

1. **User Action Required:**
   - Copy StaX to `~/.nuke/StaX/`
   - Restart Nuke
   - Attempt to open panel with `Ctrl+Alt+S`
   - Review console output and log files

2. **Agent Action Required:**
   - Wait for user to provide log file or error messages
   - Analyze crash location from logs
   - Implement targeted fix based on findings

3. **Potential Fixes:**
   - Database connection: Implement retry logic, file locking
   - Import errors: Add missing dependencies, fix import paths
   - Qt conflicts: Adjust QApplication usage
   - NukeBridge issues: Add Nuke version detection, API compatibility checks

---

## File Summary

**Files Created:**
- `stax_logger.py` (160 lines) - Logging infrastructure

**Files Modified:**
- `init.py` (78 lines) - Plugin path debugging
- `menu.py` (139 lines) - Menu creation debugging
- `nuke_launcher.py` (~900 lines) - Comprehensive debugging throughout
- `changelog.md` - Documented debugging session
- `DEBUGGING_SESSION_SUMMARY.md` (this file) - Complete session documentation

**Total Lines Added:** ~400+ lines of debugging code

**Log Output When Successful:** ~200 lines of console/log output showing all operations

---

## Conclusion

Comprehensive debugging infrastructure is now in place to identify the exact cause of Nuke crashes. Every critical operation from plugin initialization through panel creation is now logged with:

- ✓ Success indicators showing operations that complete
- ✗ Failure indicators showing operations that fail
- Full tracebacks for all exceptions
- Timestamped log files for post-crash analysis
- Console output for real-time monitoring

The next user action is to test in Nuke and provide the log file or console output, which will reveal the exact failure point.
