# Fix NumPy Compatibility Issue

## Problem
```
A module that was compiled using NumPy 1.x cannot be run in
NumPy 2.0.2 as it may crash.
```

PySide2 (and its underlying shiboken2 module) was compiled against NumPy 1.x and is **incompatible** with NumPy 2.0+.

## Quick Fix

### Option 1: Downgrade NumPy (Recommended)
```powershell
pip install "numpy<2.0.0"
```

This will install the latest NumPy 1.x version (1.26.4) which is compatible with PySide2.

### Option 2: Install Specific NumPy Version
```powershell
pip install numpy==1.26.4
```

### Option 3: Reinstall All Dependencies
```powershell
pip install -r requirements.txt --force-reinstall
```

## Verify Fix

After downgrading NumPy, test the application:
```powershell
python gui_main.py
```

The application should launch without errors.

## Why This Happens

**Root Cause:**
- PySide2's `shiboken2` module (C++ bindings) was compiled with NumPy 1.x headers
- NumPy 2.0 introduced breaking ABI changes
- Modules compiled against NumPy 1.x cannot load with NumPy 2.x installed

**Affected Packages:**
- PySide2 (all versions up to 5.15.x)
- PySide6 (newer versions are NumPy 2.x compatible)
- Any package with C extensions using NumPy's C API

## Long-Term Solutions

### For Development (Python 3.9+)
Consider migrating to PySide6 which has better NumPy 2.x support:
```powershell
pip uninstall PySide2
pip install PySide6
# Update imports in code: from PySide2 -> from PySide6
```

### For Production (VFX Pipeline)
- Pin `numpy<2.0.0` in requirements.txt (already done)
- VFX pipelines typically use Python 2.7 or 3.7 with older NumPy anyway
- This ensures consistent behavior across all workstations

## Verification Command

Check your current NumPy version:
```powershell
python -c "import numpy; print(numpy.__version__)"
```

Should output something like `1.26.4` (not `2.0.x`)

## Related Links
- [NumPy 2.0 Migration Guide](https://numpy.org/devdocs/numpy_2_0_migration_guide.html)
- [PySide2 Documentation](https://doc.qt.io/qtforpython-5/)
- [PySide6 Migration](https://doc.qt.io/qtforpython-6/porting_from2.html)

---

**Status:** Issue identified and fix provided  
**Impact:** Prevents application from launching  
**Severity:** High  
**Resolution Time:** < 1 minute
