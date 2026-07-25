# Bundled UI fonts

Fonts here are registered with Qt at startup and one family is applied as the
app-wide UI font (see [`src/font_manager.py`](../../src/font_manager.py)).

**Default:** `Inter` — [`Inter-Variable.ttf`](Inter-Variable.ttf), licensed under
the SIL Open Font License 1.1 ([`OFL.txt`](OFL.txt)).

## Replace / add a font

1. Drop a `.ttf` / `.otf` / `.ttc` into this folder (keep its license file, too).
   Every font here is auto-registered — no code change needed.
2. Make it the active UI font by setting the `ui_font_family` config key to the
   font's **family name** (e.g. `"Roboto"`), or by editing `DEFAULT_UI_FONT` in
   `src/font_manager.py` if you replaced the bundled default outright.

To find a font file's exact family name:

```python
from PySide2 import QtWidgets, QtGui
app = QtWidgets.QApplication([])
fid = QtGui.QFontDatabase.addApplicationFont("resources/fonts/YourFont.ttf")
print(QtGui.QFontDatabase.applicationFontFamilies(fid))
```

The whole `resources/` tree ships with the frozen build (see `setup_freeze.py`),
so bundled fonts travel with the packaged app automatically.
