# Media Info Popup - Feature Guide

## Overview

The Media Info Popup is a quick preview feature that displays detailed information about any element without interrupting your workflow. It appears when you hold the `Alt` key and hover over an element.

## How to Use

### Basic Usage

1. **Navigate to any list** with elements
2. **Hold the Alt key** on your keyboard
3. **Hover over any element** (in Gallery or List view)
4. **Wait ~0.5 seconds** for the popup to appear
5. **Release Alt or click anywhere** to dismiss

### Popup Features

The popup displays:

#### Large Preview (380x280px)
- High-quality preview image with aspect ratio preserved
- Shows actual thumbnail from preview generation
- "No Preview Available" message if preview missing

#### Metadata Display
- **Name**: Element display name
- **Type**: 2D, 3D, or Toolset
- **Format**: File extension (.exr, .abc, .nk, etc.)
- **Frames**: Frame range for sequences (e.g., "1001-1150")
- **Size**: File size formatted in MB or GB
- **Path**: Full file path (selectable text)
- **Comment**: User comment or "No comment"

#### Action Buttons

**Insert into Nuke** (Blue button)
- Instantly inserts element into Nuke
- Same behavior as double-clicking element
- Creates Read/ReadGeo/Paste node based on type

**Reveal in Explorer** (Gray button)
- Opens OS file explorer to element location
- Selects the file in Windows Explorer
- Works on Windows, macOS, and Linux

## Visual Design

### Dark Theme
```
┌────────────────────────────────────────┐
│ Element Name                           │
├────────────────────────────────────────┤
│                                        │
│         [LARGE PREVIEW IMAGE]          │
│            380 x 280 px                │
│                                        │
├────────────────────────────────────────┤
│ Name:     element_name.exr             │
│ Type:     2D                           │
│ Format:   .exr                         │
│ Frames:   1001-1150                    │
│ Size:     245.3 MB                     │
│ Path:     /path/to/file.exr            │
│ Comment:  Beauty pass render           │
├────────────────────────────────────────┤
│ [Insert into Nuke] [Reveal in Explorer]│
└────────────────────────────────────────┘
```

### Color Scheme
- **Background**: Dark gray (#2b2b2b)
- **Border**: Medium gray (#555555)
- **Text Labels**: Light gray (#aaaaaa)
- **Text Values**: White (#ffffff)
- **Insert Button**: Blue (#4a90e2)
- **Reveal Button**: Gray (#5a5a5a)

## Behavior Details

### Hover Delay
- **500ms delay** before popup appears
- Prevents accidental popups during mouse movement
- Timer resets if you move to different element

### Positioning
- Appears near cursor with **20px offset** (right and down)
- Automatically stays on screen (Qt window management)
- Always on top of other windows

### Alt Key Detection
- Tracks Alt key state continuously
- Hides popup immediately when Alt released
- Works in both Gallery and List views

### Mouse Interaction
- **Hover**: Shows popup after delay
- **Click anywhere**: Dismisses popup
- **Leave widget**: Cancels pending popup

## Keyboard Shortcuts Integration

| Action | Shortcut |
|--------|----------|
| Show popup | Hold `Alt` + Hover |
| Dismiss popup | Release `Alt` or Click |
| Insert from popup | Click "Insert" button |
| Reveal location | Click "Reveal" button |

## Usage Scenarios

### Quick Preview Check
1. Hold Alt while browsing elements
2. Hover over thumbnails to see full previews
3. Check metadata without selecting

### Fast Asset Insertion
1. Hold Alt and hover over element
2. Click "Insert into Nuke" button
3. Element is inserted, popup closes

### Locate Files
1. Hold Alt and hover over element
2. Click "Reveal in Explorer"
3. File opens in OS explorer

### Compare Elements
1. Hold Alt continuously
2. Move mouse between elements
3. Popup updates to show each element
4. Compare previews and metadata side-by-side

## Tips & Best Practices

### Speed Up Workflow
- Keep Alt held while browsing multiple elements
- Use popup for quick insertion instead of double-click
- Check paths before ingesting duplicates

### Visual Inspection
- Use larger popup preview for quality checking
- Verify frame ranges before insertion
- Check file sizes to identify issues

### Keyboard-Centric Users
- Alt+Hover is faster than clicking for info
- Insert button avoids double-click precision
- No need to change selection state

## Technical Details

### Event Handling
- Event filter on viewport for mouse tracking
- Qt timer for hover delay
- Keyboard event tracking for Alt state

### Performance
- Lightweight popup creation
- Pixmap caching for preview images
- No database queries during hover (uses cached data)

### Cross-Platform Support
- **Windows**: `explorer /select,` command
- **macOS**: `open -R` command
- **Linux**: `xdg-open` command

## Troubleshooting

### Popup Not Appearing
**Issue**: Nothing happens when holding Alt and hovering

**Solutions**:
- Ensure mouse is over an element (not empty space)
- Wait full 0.5 seconds without moving mouse
- Check that Alt key is actually pressed
- Try in both Gallery and List views

### Preview Not Loading
**Issue**: "No Preview Available" message

**Solutions**:
- Check if preview was generated during ingestion
- Verify preview file exists at path in database
- Re-ingest element with "Generate Previews" enabled
- Check Pillow is installed for preview generation

### Reveal Not Working
**Issue**: Clicking "Reveal in Explorer" does nothing

**Solutions**:
- Verify file path exists on disk
- Check file hasn't been moved/deleted
- For soft copies, ensure original path is valid
- For hard copies, verify repository path is accessible

### Popup Stuck On Screen
**Issue**: Popup won't dismiss

**Solutions**:
- Click anywhere on the popup
- Click outside the popup
- Release and re-press Alt key
- Move mouse away from elements

### Wrong Element Showing
**Issue**: Popup shows different element than hovered

**Solutions**:
- Wait for hover timer to complete
- Move mouse slowly between elements
- Check element_id in database is correct

## Integration with Main Workflow

### Complements Double-Click
- Double-click: Direct insertion
- Alt+Hover: Preview first, then decide

### Works with Search
- Filter elements with search box
- Use Alt+Hover to preview filtered results
- Insert directly from popup

### Combines with View Modes
- **Gallery View**: Hover over thumbnails
- **List View**: Hover over table rows
- Consistent behavior in both modes

## Future Enhancements (Planned)

- Video playback in popup for sequences
- Metadata editing directly in popup
- Add to favorites button
- Copy path to clipboard button
- Custom field display configuration
- Fullscreen preview mode (F key)

## Code Reference

### MediaInfoPopup Class
Location: `gui_main.py` (lines 20-250)

Key methods:
- `show_element()`: Display popup with data
- `on_insert_clicked()`: Handle Insert button
- `on_reveal_clicked()`: Handle Reveal button

### MediaDisplayWidget Integration
Location: `gui_main.py` (lines 370-720)

Key additions:
- `eventFilter()`: Track Alt+Hover events
- `show_info_popup()`: Display popup after delay
- `on_popup_insert()`: Handle popup actions
- `on_popup_reveal()`: Open file in explorer

## Example Use Cases

### Use Case 1: Quality Control
Artist needs to verify renders before insertion:
1. Hold Alt and hover over sequence
2. Check preview for quality issues
3. Verify frame range is correct
4. Click Insert if approved

### Use Case 2: Finding Files
TD needs to locate asset on disk:
1. Search for asset name
2. Hold Alt and hover over result
3. Click "Reveal in Explorer"
4. File location opens

### Use Case 3: Quick Metadata Check
Compositor checking asset details:
1. Hold Alt while browsing library
2. Hover to see formats and sizes
3. Compare different versions
4. Select best option

### Use Case 4: Fast Batch Review
Supervisor reviewing multiple assets:
1. Hold Alt key continuously
2. Move mouse along elements row
3. Popup updates for each element
4. Quick visual inspection of entire list

## Accessibility Notes

- **Keyboard Accessible**: All features work with keyboard
- **No Focus Stealing**: Popup doesn't activate main window
- **Clear Visual Feedback**: Hover state and popup appearance
- **Escape Path**: Multiple ways to dismiss (Alt, click, move away)

## Configuration

Currently no configuration options for popup. Future enhancements may include:

- Hover delay duration setting
- Popup size customization
- Default position preference
- Preview quality setting
- Field visibility toggles

---

**Related Documentation**:
- [GUI_GUIDE.md](GUI_GUIDE.md) - Complete GUI features
- [QUICKSTART.md](QUICKSTART.md) - Getting started guide
- [instructions.md](instructions.md) - Technical specification
