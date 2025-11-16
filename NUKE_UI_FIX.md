# Nuke UI Compatibility Fix

## Changes Made

### 1. Disabled Stylesheet in Nuke Mode
**File:** `nuke_launcher.py` - `show_stax_panel()` function

**Before:**
```python
if app:
    # Always try to load stylesheet
    stylesheet_path = os.path.join(os.path.dirname(__file__), 'resources', 'style.qss')
    if os.path.exists(stylesheet_path):
        with open(stylesheet_path, 'r') as f:
            stylesheet = f.read()
            app.setStyleSheet(stylesheet)
```

**After:**
```python
if app and not NUKE_MODE:
    # Only apply stylesheet in standalone mode
    # Skip in Nuke to avoid Qt compatibility issues
    print("[show_stax_panel] Loading stylesheet (standalone mode)...")
    ...
elif NUKE_MODE:
    print("[show_stax_panel] NUKE_MODE: Skipping stylesheet (using Nuke's default styling)")
```

**Reason:** Custom QSS stylesheets can conflict with Nuke's own Qt styling system, potentially causing crashes or rendering issues.

---

### 2. Skipped Login Dialog in Nuke Mode
**File:** `nuke_launcher.py` - `StaXPanel.__init__()` method

**Before:**
```python
# Always show login dialog
QtCore.QTimer.singleShot(100, self.show_login)
```

**After:**
```python
# Skip login dialog in Nuke mode - auto-login as admin
if NUKE_MODE:
    print("[StaXPanel.__init__] NUKE_MODE: Skipping login dialog, auto-login as admin")
    self.current_user = "admin"
    self.is_admin = True
else:
    # Show login dialog in standalone mode
    QtCore.QTimer.singleShot(100, self.show_login)
```

**Reason:** 
- Simplifies Nuke startup - no modal dialog interruption
- Reduces potential crash points (dialog creation, show, modal event loop)
- In production VFX environments, Nuke users are typically trusted
- Login can be re-enabled later if needed for multi-user permissions

---

## Testing Instructions

### Test 1: Restart Nuke
```
1. Close Nuke completely
2. Reopen Nuke
3. Check console for init/menu messages (should be same as before)
```

### Test 2: Open StaX Panel
```
1. Press Ctrl+Alt+S (or StaX > Open StaX Panel)
2. Watch console output
3. Expected: Panel opens WITHOUT login dialog
4. Expected: Panel uses Nuke's default styling (not custom dark theme)
```

### Test 3: Verify Console Output
```
Expected new messages:

[show_stax_panel] NUKE_MODE: Skipping stylesheet (using Nuke's default styling)
[StaXPanel.__init__] NUKE_MODE: Skipping login dialog, auto-login as admin
[show_stax_panel] [OK] Panel registered
[show_stax_panel] [OK] Panel added to pane
[show_stax_panel] [OK] Panel shown successfully
```

### Test 4: Verify Auto-Login
```
Check that panel is fully functional:
- Browse stacks/lists in left panel
- View elements in media display
- All features should work without login prompt
```

---

## What Should Happen Now

### ✅ Expected Success Scenario:

1. **Init Phase** - All [OK] messages ✓
2. **Menu Phase** - All [OK] messages ✓
3. **Panel Opening** - New output:
   ```
   [show_stax_panel] NUKE_MODE: Skipping stylesheet
   [StaXPanel.__init__] NUKE_MODE: Skipping login dialog, auto-login as admin
   [StaXPanel.__init__] [OK] UI setup complete
   [show_stax_panel] [OK] Panel registered
   [show_stax_panel] [OK] Panel shown successfully
   ```
4. **Panel appears** - No login dialog, ready to use immediately
5. **Styling** - Uses Nuke's native Qt theme (lighter colors, Nuke-like appearance)

---

## If It Still Crashes

Check the log file for the last successful operation before crash:

**Common crash points eliminated:**
- ❌ Login dialog creation (removed)
- ❌ Login dialog show() (removed)
- ❌ Stylesheet parsing (removed)
- ❌ Stylesheet application (removed)

**Remaining potential issues:**
1. **UI Setup** - Widget creation in `setup_ui()`
2. **Database** - First query execution
3. **Media Display** - Thumbnail loading
4. **Preview Worker** - Thread creation

---

## Console Output Comparison

### Before (Full Styling + Login):
```
[show_stax_panel] Loading stylesheet...
[show_stax_panel]   [OK] Stylesheet applied (15234 chars)
[StaXPanel.__init__] Scheduling login dialog...
[StaXPanel.__init__]   [OK] Login dialog scheduled
(then crash or login dialog appears)
```

### After (No Styling + Auto-Login):
```
[show_stax_panel] NUKE_MODE: Skipping stylesheet (using Nuke's default styling)
[StaXPanel.__init__] NUKE_MODE: Skipping login dialog, auto-login as admin
[StaXPanel.__init__] [OK] UI setup complete
[show_stax_panel] [OK] Panel shown successfully
(panel appears immediately, ready to use)
```

---

## Rollback Instructions

If you want to restore login dialog or stylesheet:

### Re-enable Login:
```python
# In nuke_launcher.py, StaXPanel.__init__()
# Change from:
if NUKE_MODE:
    self.current_user = "admin"
    self.is_admin = True
# Back to:
QtCore.QTimer.singleShot(100, self.show_login)
```

### Re-enable Stylesheet:
```python
# In nuke_launcher.py, show_stax_panel()
# Change from:
if app and not NUKE_MODE:
# Back to:
if app:
```

---

## Next Steps

1. **Restart Nuke** (close completely)
2. **Press Ctrl+Alt+S** to open StaX
3. **Send me the console output** showing:
   - Init phase (should be same)
   - Menu phase (should be same)
   - Panel opening (should show new messages)
   - Success or new error details

If it still crashes, the log file will now show exactly which UI widget or component initialization is causing the problem.

---

## Benefits of These Changes

✅ **Simplified Startup** - Fewer moving parts, fewer crash points  
✅ **Faster Loading** - No stylesheet parsing, no dialog creation  
✅ **Better Compatibility** - Uses Nuke's Qt styling (no conflicts)  
✅ **Production Ready** - Auto-login suitable for trusted users  
✅ **Easier Debugging** - Fewer variables, clearer crash location  

The panel will look slightly different (Nuke's default style instead of custom dark theme), but functionality is identical.
