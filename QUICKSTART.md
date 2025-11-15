# VFX Asset Hub - Quick Start Guide

## Installation & Setup

### Option 1: Python 3 (Recommended for Development)

```powershell
# Navigate to project directory
cd d:\Scripts\modern-stock-browser

# Create virtual environment with Python 3
python -m venv .venvPy3

# Activate virtual environment
.\.venvPy3\Scripts\activate

# Install Python 3 compatible dependencies
pip install PySide2 Pillow

# Run the application
python gui_main.py
```

### Option 2: Python 2.7 (VFX Pipeline Compatibility)

```powershell
# Navigate to project directory
cd d:\Scripts\modern-stock-browser

# Create virtual environment with Python 2.7
python2.7 -m virtualenv .venv

# Activate virtual environment
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python gui_main.py
```

## First Run

When you first run the application:

1. **Database is auto-created** at `./data/vah.db`
2. **Configuration file** is created at `./config/config.json`
3. **Preview directory** is created at `./previews/`

## Creating Your First Stack and List

1. In the left sidebar, click **"+ Stack"**
2. Enter a name (e.g., "Plates") and repository path (e.g., `./repository/plates`)
3. Click **"+ List"** to create a list within the stack
4. Enter a list name (e.g., "Explosions")

## Ingesting Assets

### Method 1: File Menu
1. Go to **File → Ingest Files...** (or press `Ctrl+I`)
2. Select one or more files
3. Choose target list
4. Files will be ingested with automatic sequence detection

### Method 2: Drag & Drop (Coming in Beta)
- Drag files from file explorer directly onto the list

## Viewing Elements

- **Gallery View**: Large thumbnails (default)
- **List View**: Table with metadata
- Toggle between views using the Gallery/List buttons
- Use the **Size slider** to adjust thumbnail size in Gallery view
- **Search bar**: Live filter elements by name

## Keyboard Shortcuts

- `Ctrl+I` - Ingest files
- `Ctrl+2` - Toggle History panel
- `Ctrl+3` - Toggle Settings panel
- `Ctrl+Q` - Exit application

## Inserting Elements into Nuke

Double-click any element to insert it into Nuke:
- **2D assets** → Creates Read node
- **3D assets** → Creates ReadGeo node
- **Toolsets** → Pastes node graph

*(In Alpha, this runs in mock mode - displays a message instead of actually creating nodes)*

## Viewing History

1. Press `Ctrl+2` or go to **View → History Panel**
2. See all ingestion events with timestamps
3. Click **"Export CSV"** to save history to a file

## Configuring Settings

1. Press `Ctrl+3` or go to **View → Settings Panel**
2. Configure:
   - **Copy Policy**: Soft (reference) or Hard (physical copy)
   - **Sequence Detection**: Auto-detect frame sequences
   - **Preview Generation**: Generate thumbnails
   - **Custom Processors**: Add Python scripts for pipeline hooks

## Custom Processors

Create Python scripts to extend the ingestion pipeline:

### Example: Pre-Ingest Validation
Create `validate_naming.py`:
```python
# -*- coding: utf-8 -*-
import re

# Validate naming convention
if not re.match(r'^[A-Z]{3}_\d{4}', context['name']):
    result = {
        'continue': False,
        'message': 'File name must match pattern: XXX_####'
    }
else:
    result = {'continue': True}
```

Then in Settings, set **Pre-Ingest Hook** to the path of this script.

## Database Location

The SQLite database is stored at:
```
./data/vah.db
```

You can change this in `./config/config.json`:
```json
{
    "database_path": "\\\\network\\share\\vah.db"
}
```

## Troubleshooting

### Import Errors
If you see import errors for `PySide2` or `PIL`:
```powershell
pip install PySide2 Pillow
```

### Database Locked
If you get "database is locked" errors:
- Close other instances of the application
- Check network connection if using shared database
- The system has built-in retry logic (5 attempts)

### Preview Generation Fails
- Ensure Pillow is installed: `pip install Pillow`
- Check that source images are in supported formats (JPG, PNG, EXR, etc.)

## Next Steps

- Read `instructions.md` for complete technical details
- Check `Roadmap.md` for upcoming features
- Run `python example_usage.py` to test core modules without GUI

## Support

For issues or questions, refer to the documentation:
- `README.md` - Overview and quick start
- `instructions.md` - Complete technical specification
- `.github/copilot-instructions.md` - AI agent guidance
