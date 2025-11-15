# Stax - GUI Features Guide

## Main Window Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ File   View   Help                                    [_ □ X]       │
├─────────────────────────────────────────────────────────────────────┤
│ ┌─────────────┬─────────────────────────────────────────────────┐  │
│ │ Stacks &    │ [Search...] [Gallery][List] Size: [====|====]   │  │
│ │ Lists       ├─────────────────────────────────────────────────┤  │
│ │             │                                                  │  │
│ │ ▼ Plates    │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐        │  │
│ │   Cityscape │  │ IMG1 │  │ IMG2 │  │ IMG3 │  │ IMG4 │        │  │
│ │   Explosions│  │      │  │      │  │      │  │      │        │  │
│ │             │  └──────┘  └──────┘  └──────┘  └──────┘        │  │
│ │ ▼ 3D Assets │                                                  │  │
│ │   Characters│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐        │  │
│ │   Props     │  │ SEQ1 │  │ SEQ2 │  │ TOOL │  │ GEO1 │        │  │
│ │             │  │      │  │      │  │      │  │      │        │  │
│ │[+Stack]     │  └──────┘  └──────┘  └──────┘  └──────┘        │  │
│ │[+List ]     │                                                  │  │
│ └─────────────┴─────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│ Ready                                                               │
└─────────────────────────────────────────────────────────────────────┘
```

## Panel: Stacks & Lists (Left Sidebar)

**Purpose**: Navigate your asset hierarchy

**Features**:
- Tree view showing Stacks → Lists
- Click any List to view its elements
- `+ Stack` button: Create new primary category
- `+ List` button: Create new sub-category
- Automatic expansion on load

**Usage**:
1. Click a List name to load elements in center panel
2. Click `+ Stack` to add categories like "Plates", "3D Assets", "Toolsets"
3. Click `+ List` to add sub-categories like "Explosions", "Characters"

## Panel: Media Display (Center)

**Purpose**: View and manage elements

**View Modes**:

### Gallery View (Default)
- Large thumbnail grid
- Visual preview of assets
- Size slider to adjust thumbnail size (64px - 512px)
- Double-click element to insert into Nuke

### List View
- Tabular data display
- Columns: Name, Format, Frames, Type, Size, Comment
- Sortable columns
- Good for metadata review

**Search Bar**:
- Live filtering as you type
- Searches element names
- Works in both view modes

**Actions**:
- Single click: Select element
- Double click: Insert into Nuke (creates Read/ReadGeo/Paste)
- Search: Filter elements in real-time

## Panel: History (Ctrl+2)

**Purpose**: Track all ingestion activities

**Features**:
- Chronological list of ingestion events
- Columns: Date/Time, Action, Source, Target, Status
- Color-coded status (green = success, red = error)
- Export to CSV button
- Refresh button to update

**Usage**:
1. Press `Ctrl+2` to toggle visibility
2. View recent ingestion history
3. Click "Export CSV" to save complete history
4. Use for auditing and troubleshooting

## Panel: Settings (Ctrl+3)

**Purpose**: Configure application behavior

**Sections**:

### Ingestion Settings
- **Default Copy Policy**: 
  - `soft` = Store reference to original location
  - `hard` = Copy files to repository
- **Auto-detect Sequences**: Automatically find frame sequences
- **Generate Previews**: Create thumbnails during ingestion

### Custom Processors
Configure Python scripts for pipeline hooks:
- **Pre-Ingest Hook**: Run before file copy (validation, naming)
- **Post-Ingest Hook**: Run after cataloging (notifications, metadata)
- **Post-Import Hook**: Run after Nuke node creation (OCIO, expressions)

**Usage**:
1. Press `Ctrl+3` to toggle visibility
2. Modify settings as needed
3. Click "Save" to apply changes
4. Click "Reset to Defaults" to restore original values

## Menu Bar

### File Menu
- **Ingest Files... (Ctrl+I)**: Open file selection dialog to ingest assets
- **Exit (Ctrl+Q)**: Close application

### View Menu
- **History Panel (Ctrl+2)**: Toggle history panel
- **Settings Panel (Ctrl+3)**: Toggle settings panel

### Help Menu
- **About**: Show application version and info

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+I` | Ingest files |
| `Ctrl+2` | Toggle History panel |
| `Ctrl+3` | Toggle Settings panel |
| `Ctrl+Q` | Exit application |

## Ingestion Workflow

### Step 1: Select Target List
1. Navigate to desired List in left sidebar
2. Click to select (highlights in blue)

### Step 2: Ingest Files
1. Press `Ctrl+I` or go to File → Ingest Files
2. Select one or more files from file dialog
3. Choose target List in popup dialog
4. Click OK

### Step 3: Processing
- Progress dialog shows ingestion status
- Automatic sequence detection if enabled
- Preview generation (if enabled)
- Metadata extraction

### Step 4: View Results
- Elements appear in Media Display
- History panel shows ingestion log
- Status bar shows summary

## Element Insertion (Nuke Integration)

### Insert Element into Nuke
1. Double-click any element in Gallery or List view
2. System determines element type:
   - **2D** (images/sequences) → Creates `Read` node
   - **3D** (geometry) → Creates `ReadGeo` node
   - **Toolset** (.nk files) → Pastes node graph

### Mock Mode (Alpha)
- In Alpha, Nuke operations display confirmation dialogs
- Actual Nuke node creation requires Nuke environment
- Set `nuke_mock_mode: false` in config to use real Nuke API

## Advanced Features

### Sequence Detection
When ingesting a single frame like `shot_0001.exr`:
1. System scans directory for matching pattern
2. Detects full sequence: `shot_0001.exr` through `shot_0150.exr`
3. Extracts frame range: `1-150`
4. Stores sequence path with padding: `shot_####.exr`

### Hard Copy vs Soft Copy
**Soft Copy** (Reference):
- Stores original file path
- No disk space used
- Fast ingestion
- Files stay in original location

**Hard Copy** (Physical):
- Copies files to repository
- Uses disk space
- Slower ingestion
- Files centralized for sharing

### Search & Filter
- Type in search box to filter elements
- Searches element names only (for now)
- Updates instantly (live filter)
- Works in both Gallery and List views

## Status Bar

Bottom of window shows current state:
- "Ready" - Idle state
- "Viewing: Stack > List" - Current selection
- "Inserted: element_name" - After inserting element
- Other contextual messages

## Dialogs

### Add Stack Dialog
- **Stack Name**: Display name (e.g., "Plates")
- **Repository Path**: Physical location for files
- Browse button to select directory

### Add List Dialog
- **Parent Stack**: Dropdown of available stacks
- **List Name**: Display name (e.g., "Explosions")

### Select Target List Dialog
- Tree view of all stacks and lists
- Only lists are selectable (not stacks)
- Used when ingesting files

### Progress Dialog
- Shows during multi-file ingestion
- Cancel button to abort
- Updates with current file being processed

## Tips & Best Practices

1. **Organize with Stacks**: Use Stacks for high-level categories
2. **Use Descriptive Names**: Name Lists and Elements clearly
3. **Check History**: Review ingestion logs for errors
4. **Test with Soft Copy First**: Use soft copy to test before committing
5. **Configure Processors**: Set up validation hooks for team standards
6. **Export History**: Regularly export history for records
7. **Search Efficiently**: Use search to quickly find elements
8. **Adjust Thumbnail Size**: Use slider for comfortable viewing

## Troubleshooting

### No Elements Showing
- Ensure you've selected a List (not a Stack)
- Check if List actually contains elements
- Try refreshing by clicking another List then back

### Ingestion Fails
- Check History panel for error messages
- Verify source files are accessible
- Check disk space if using hard copy
- Review Pre-Ingest processor output

### Previews Not Generating
- Ensure Pillow is installed
- Check source file format is supported
- Verify preview directory is writable
- Check Settings: "Generate Previews" is enabled

### Settings Not Saving
- Check file permissions on config directory
- Verify `config/config.json` is writable
- Look for error messages in console

## Future Features (Beta/RC)

Coming in future releases:
- Drag-and-drop ingestion from OS
- Alt+Hover media info popup with large preview
- Advanced search with property selection
- Favorites UI and quick access
- Playlists for collaborative workflows
- Auto-register Write node outputs
- Video preview playback
- Batch metadata editing
