# StaX Debugging Quick Reference

Quick guide for interpreting debugging output and diagnosing Nuke crashes.

---

## Output Symbols

```
[OK]     Success - Operation completed successfully
[ERROR]  Failure - Operation failed (usually critical)
[WARN]   Warning - Non-critical issue (operation continues)
====     Separator - Major section boundary
```

---

## Execution Sequence

When Nuke starts with StaX installed, this is the order of execution:

```
1. init.py         → Plugin path setup
2. menu.py         → Menu creation
3. nuke_launcher.py → Module imports (when menu is accessed)
4. show_stax_panel() → Panel registration (when Ctrl+Alt+S pressed)
5. StaXPanel.__init__() → Panel initialization
6. setup_ui()      → UI construction
7. show_login()    → Login dialog
```

---

## Console Output Sections

### Section 1: init.py (Plugin Initialization)
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
```

**What to look for:**
- All paths show ✓ (success)
- Base directory exists
- No ✗ markers

**Common issues:**
- `✗ Base directory does not exist` → Wrong installation path
- `✗ Failed to add path` → Permission issues
- No output at all → init.py not being executed (wrong location)

---

### Section 2: menu.py (Menu Creation)
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
```

**What to look for:**
- Menu created successfully
- All 4 commands added
- No ✗ markers

**Common issues:**
- `✗ Failed to create menu` → Nuke API issue
- `✗ Failed to add command` → Import error in nuke_launcher
- Menu appears but no commands → Commands failed individually

---

### Section 3: nuke_launcher.py (Module Imports)
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
[nuke_launcher] Importing core modules...
[nuke_launcher]   ✓ Config
[nuke_launcher]   ✓ DatabaseManager
[nuke_launcher]   ✓ IngestionCore
...
[nuke_launcher] Importing UI modules...
[nuke_launcher]   ✓ AdvancedSearchDialog
[nuke_launcher]   ✓ AddStackDialog
...
[nuke_launcher]   ✓ All UI modules imported (16 widgets)
[nuke_launcher] ✓ All imports successful
```

**What to look for:**
- PySide2 imports successfully
- NUKE_MODE = True
- All core modules import
- All 16 UI widgets import
- Final "All imports successful" message

**Common issues:**
- `✗ Failed to import PySide2` → PySide2 not installed for Nuke's Python
- `✗ Failed to import Config` → Missing src/ directory in plugin path
- `✗ Failed to import AdvancedSearchDialog` → Missing UI module
- Stops at specific import → That module has syntax/dependency error

---

### Section 4: show_stax_panel() (Panel Registration)
```
================================================================================
[show_stax_panel] Function called
================================================================================
[show_stax_panel] Getting QApplication instance...
[show_stax_panel]   ✓ QApplication instance found
[show_stax_panel] Loading stylesheet...
[show_stax_panel]   ✓ Stylesheet applied (1234 chars)
[show_stax_panel] Checking NUKE_MODE: True
[show_stax_panel] Using nukescripts.panels.registerWidgetAsPanel...
[show_stax_panel]   ✓ Panel registered
[show_stax_panel] Adding panel to pane...
[show_stax_panel]   ✓ Panel added to pane
[show_stax_panel] ✓ Panel shown successfully
```

**What to look for:**
- QApplication instance found
- Panel registered successfully
- Panel added to pane
- No ✗ markers

**Common issues:**
- `⚠ No QApplication instance` → Unusual but not fatal
- `✗ Failed to register panel` → nukescripts API issue
- `✗ Failed to add pane` → Nuke panel system issue
- Falls back to standalone dialog → Panel registration failed

---

### Section 5: StaXPanel.__init__() (Panel Initialization)
```
[StaXPanel.__init__] Initialization started...
================================================================================
[StaXPanel.__init__]   ✓ QWidget superclass initialized
[StaXPanel.__init__] Initializing core components...
[StaXPanel.__init__]   ✓ Config initialized
[StaXPanel.__init__]   ✓ Directories ensured
[StaXPanel.__init__]   ✓ DatabaseManager initialized
[StaXPanel.__init__]   ✓ NukeBridge initialized
[StaXPanel.__init__]   ✓ NukeIntegration initialized
[StaXPanel.__init__]   ✓ IngestionCore initialized
[StaXPanel.__init__]   ✓ ProcessorManager initialized
[StaXPanel.__init__] Setting up UI...
[StaXPanel.__init__]   ✓ UI setup complete
[StaXPanel.__init__] ✓ Initialization complete!
```

**What to look for:**
- QWidget initialized
- All components initialize successfully
- UI setup completes
- Final "Initialization complete!" message

**Common issues:**
- `✗ Failed to initialize Config` → Config file issue
- `✗ Failed to initialize DatabaseManager` → **MOST COMMON** - Database connection issue
- `✗ Failed to initialize NukeBridge` → Nuke API compatibility issue
- `✗ Failed to setup UI` → Qt widget creation issue
- Stops at specific component → That component is causing the crash

---

## Crash Location Diagnosis

### If Nuke crashes DURING startup:
- **Check:** init.py output
- **Likely cause:** Plugin path setup issue
- **Look for:** Last ✓ before crash

### If Nuke crashes when OPENING menu:
- **Check:** menu.py output
- **Likely cause:** Menu command registration issue
- **Look for:** Which command failed to add

### If Nuke crashes when SELECTING menu item:
- **Check:** nuke_launcher.py import section
- **Likely cause:** Module import failure
- **Look for:** Last imported module before crash

### If Nuke crashes when PANEL OPENS:
- **Check:** show_stax_panel() output
- **Likely cause:** Panel registration or QApplication issue
- **Look for:** registerWidgetAsPanel() call result

### If Nuke crashes DURING panel initialization:
- **Check:** StaXPanel.__init__() output
- **Likely cause:** Component initialization failure (usually Database)
- **Look for:** Last component to show ✓ before crash

---

## Log File Location

**Console Output:** Nuke Script Editor (bottom panel)  
**Log Files:** `StaX/logs/stax_YYYYMMDD_HHMMSS.log`

To find the most recent log:
1. Navigate to StaX installation directory
2. Open `logs/` folder
3. Sort by date modified (newest first)
4. Open most recent `stax_*.log` file

---

## Reading Log Files

### Find the crash point:
```bash
# Search for ERROR or CRITICAL
grep -i "error\|critical" stax_20240115_102345.log

# Or manually scroll to find first ✗ marker
```

### Typical crash log excerpt:
```
[10:23:45.456] [INFO] [StaXPanel.__init__]   ✓ Config initialized
[10:23:45.457] [INFO] [StaXPanel.__init__]   ✓ Directories ensured
[10:23:45.458] [INFO] [StaXPanel.__init__] Database path: D:\data\vah.db
[10:23:45.459] [ERROR] [StaXPanel.__init__]   ✗ Failed to initialize DatabaseManager: unable to open database file
[10:23:45.460] [ERROR] Traceback (most recent call last):
[10:23:45.461] [ERROR]   File "nuke_launcher.py", line 234, in __init__
[10:23:45.462] [ERROR]     self.db = DatabaseManager(db_path)
[10:23:45.463] [ERROR]   File "db_manager.py", line 45, in __init__
[10:23:45.464] [ERROR]     self.conn = sqlite3.connect(db_path)
[10:23:45.465] [ERROR] sqlite3.OperationalError: unable to open database file
```

**Analysis:**
- Last successful: "Directories ensured"
- First failure: "Failed to initialize DatabaseManager"
- Root cause: `sqlite3.OperationalError: unable to open database file`
- Fix needed: Check database file path and permissions

---

## Common Crash Scenarios

### Scenario 1: Database Connection Failure
**Symptoms:**
```
[StaXPanel.__init__]   ✗ Failed to initialize DatabaseManager
sqlite3.OperationalError: unable to open database file
```
**Causes:**
- Database file doesn't exist
- No permission to read database
- Database path is incorrect
- Database is locked by another process

**Solutions:**
- Create database file if missing
- Check file permissions
- Verify `STOCK_DB` environment variable
- Close other connections to database

---

### Scenario 2: PySide2 Import Failure
**Symptoms:**
```
[nuke_launcher]   ✗ Failed to import PySide2
ImportError: No module named PySide2
```
**Causes:**
- PySide2 not installed for Nuke's Python
- Using system Python instead of Nuke's Python

**Solutions:**
- Install PySide2 in Nuke's Python: `nuke_python -m pip install PySide2`
- Check Nuke's Python path

---

### Scenario 3: UI Widget Import Failure
**Symptoms:**
```
[nuke_launcher]   ✗ Failed to import UI modules
ImportError: cannot import name AdvancedSearchDialog
```
**Causes:**
- Missing UI module file
- Syntax error in UI module
- Missing dependency in UI module

**Solutions:**
- Verify all files in `src/ui/` exist
- Check for Python syntax errors in failing module
- Review import statements in failing module

---

### Scenario 4: Panel Registration Failure
**Symptoms:**
```
[show_stax_panel]   ✗ Failed to register panel
AttributeError: 'module' object has no attribute 'panels'
```
**Causes:**
- Nuke version doesn't support panels
- nukescripts not available
- Incorrect API usage

**Solutions:**
- Check Nuke version (panels require Nuke 7+)
- Verify nukescripts module exists
- Use fallback dialog mode

---

### Scenario 5: Mock Mode Still Enabled
**Symptoms:**
- Panel opens but "Insert into Nuke" doesn't work
- Read nodes not created
**Log shows:**
```
[StaXPanel.__init__] Mock mode remains enabled (not in Nuke)
```
**Causes:**
- NUKE_MODE detection failed
- Running in standalone mode by accident

**Solutions:**
- Verify running inside Nuke, not standalone
- Check NUKE_MODE = True in logs
- Restart Nuke

---

## Quick Diagnostic Commands

### Check if StaX loaded:
```python
# In Nuke Script Editor
import sys
print([p for p in sys.path if 'StaX' in p])
```

### Check if modules are available:
```python
# In Nuke Script Editor
import nuke_launcher
print(nuke_launcher.NUKE_MODE)
```

### Manually trigger panel:
```python
# In Nuke Script Editor
import nuke_launcher
nuke_launcher.show_stax_panel()
```

### Check log directory:
```python
# In Nuke Script Editor
import os
log_dir = os.path.join(os.path.expanduser('~'), '.nuke', 'StaX', 'logs')
print("Log directory:", log_dir)
print("Exists:", os.path.exists(log_dir))
if os.path.exists(log_dir):
    print("Files:", os.listdir(log_dir))
```

---

## Report Template

When reporting crashes to developer, include:

```
**Nuke Version:** [e.g., Nuke 13.2v5]
**OS:** [e.g., Windows 10, macOS 12.6, CentOS 7]
**StaX Location:** [e.g., C:\Users\user\.nuke\StaX]

**Console Output:**
[Paste last 50 lines from Script Editor]

**Log File:**
[Attach most recent log file from logs/ directory]

**Steps to Reproduce:**
1. Start Nuke
2. Press Ctrl+Alt+S
3. Nuke crashes

**Expected Behavior:**
StaX panel should open

**Additional Context:**
[Any other relevant information]
```

---

## Success Indicators

You know StaX is working correctly when you see:

```
✓ All plugin paths added (init.py)
✓ Menu created with 4 commands (menu.py)
✓ All imports successful (nuke_launcher.py)
✓ Panel registered (show_stax_panel)
✓ All components initialized (StaXPanel.__init__)
✓ UI setup complete (StaXPanel.__init__)
✓ Login dialog shown
```

**Total success markers:** ~50+ ✓ symbols with no ✗ symbols

---

## Emergency Fallback

If StaX won't load at all:

1. **Remove from Nuke:**
   ```
   Delete or rename: ~/.nuke/StaX/
   Delete or rename: ~/.nuke/init.py
   Delete or rename: ~/.nuke/menu.py
   ```

2. **Restart Nuke** - should load normally without StaX

3. **Test standalone:**
   ```bash
   cd path/to/StaX
   python main.py
   ```

4. **Review logs** in StaX/logs/ directory

5. **Report crash** using template above
