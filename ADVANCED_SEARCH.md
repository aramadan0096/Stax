# Advanced Search - User Guide

## Overview

The Advanced Search feature provides powerful property-based searching across your entire VFX asset catalog with flexible match types.

**Access:** 
- Menu: `Search → Advanced Search...`
- Keyboard: `Ctrl+F`

---

## Features

### Property-Based Search

Search within specific element properties:

| Property | Description | Example |
|----------|-------------|---------|
| **name** | Element filename | "explosion", "plate_0001" |
| **format** | File format/extension | "exr", "jpg", "mov" |
| **type** | Asset type | "2D Sequence", "3D Asset", "Toolset" |
| **comment** | User-added comments | "approved", "needs cleanup" |
| **tags** | User tags | "smoke", "outdoor", "hero shot" |

### Match Types

#### Loose Match (Default)
- Case-insensitive partial matching
- Uses SQL `LIKE` operator with wildcards
- Example: Searching "plate" matches "plate_0001", "PLATE_hero", "background_plate"

**Use when:**
- You remember part of the name
- Searching for common keywords
- Broad exploration of assets

#### Strict Match
- Exact case-sensitive matching
- No wildcards or partial matches
- Example: Searching "plate" only matches exactly "plate"

**Use when:**
- You know the exact property value
- Need precise results
- Avoiding false positives

---

## User Interface

### Search Criteria Section

```
┌─ Search Criteria ──────────────────────┐
│                                         │
│  Search Property: [name ▼]             │
│  Match Type:      [loose ▼]            │
│  Search Text:     [                  ] │
│                                         │
│           [ Search ]                    │
└─────────────────────────────────────────┘
```

**Fields:**
1. **Search Property:** Dropdown to select which property to search
2. **Match Type:** Toggle between loose (partial) and strict (exact) matching
3. **Search Text:** Enter your search query
4. **Search Button:** Execute search (or press Enter)

### Results Table

```
┌─ Search Results: ──────────────────────────────────────────┐
│ Name              │ Type        │ Format │ Frames   │ Com… │
├───────────────────┼─────────────┼────────┼──────────┼──────┤
│ explosion_0001    │ 2D Sequence │ exr    │ 1-120    │      │
│ explosion_bg_0001 │ 2D Sequence │ exr    │ 1-90     │      │
│ smoke_explosion   │ 3D Asset    │ abc    │          │      │
└───────────────────────────────────────────────────────────┘
```

**Columns:**
- **Name:** Element filename
- **Type:** Asset type (2D Sequence, 3D Asset, Toolset)
- **Format:** File extension
- **Frames:** Frame range (if applicable)
- **Comment:** User comment (abbreviated)

**Interactions:**
- **Double-click row:** Inserts element into Nuke
- **Sortable columns:** Click header to sort
- **Selection:** Single-row selection

---

## Workflow Examples

### Example 1: Find All EXR Files

1. Open Advanced Search (`Ctrl+F`)
2. Set **Search Property:** `format`
3. Set **Match Type:** `loose`
4. Enter **Search Text:** `exr`
5. Click **Search**
6. Results show all EXR sequences/images

### Example 2: Find Exact Element by Name

1. Open Advanced Search (`Ctrl+F`)
2. Set **Search Property:** `name`
3. Set **Match Type:** `strict`
4. Enter **Search Text:** `hero_plate_0001`
5. Click **Search**
6. Results show only exact matches

### Example 3: Search by Comment

1. Open Advanced Search (`Ctrl+F`)
2. Set **Search Property:** `comment`
3. Set **Match Type:** `loose`
4. Enter **Search Text:** `approved`
5. Click **Search**
6. Results show all elements with "approved" in comments

### Example 4: Find 3D Assets

1. Open Advanced Search (`Ctrl+F`)
2. Set **Search Property:** `type`
3. Set **Match Type:** `loose`
4. Enter **Search Text:** `3D`
5. Click **Search**
6. Results show all 3D assets (.abc, .obj, .fbx)

---

## Search Tips

### Effective Search Strategies

1. **Start Broad, Then Narrow:**
   - Begin with loose match on `name`
   - If too many results, switch to strict or different property

2. **Use Tags for Categories:**
   - Tag elements with keywords ("smoke", "fire", "water")
   - Search by `tags` property for thematic browsing

3. **Search Comments for Notes:**
   - Add comments during ingestion ("final", "temp", "needs review")
   - Search by `comment` to filter by status

4. **Format-Based Organization:**
   - Search `format` = "mov" for video files
   - Search `format` = "exr" for high-quality sequences

### Keyboard Shortcuts

- **Open Advanced Search:** `Ctrl+F`
- **Execute Search:** `Enter` (when in search text field)
- **Close Dialog:** `Esc` or click Close button
- **Navigate Results:** Arrow keys in table

---

## Integration with Nuke

### Inserting from Search Results

**Method 1: Double-Click**
1. Perform search
2. Double-click desired element in results table
3. Element is inserted into Nuke at cursor position

**Method 2: Select + Insert**
1. Perform search
2. Single-click to select element
3. (Future enhancement: Insert button in dialog)

### Node Creation Behavior

| Asset Type | Node Created | Configuration |
|------------|--------------|---------------|
| 2D Sequence | `Read` node | Frame range auto-configured |
| 2D Image | `Read` node | Single frame |
| 3D Asset (.abc) | `ReadGeo` node | Alembic import |
| 3D Asset (.obj/.fbx) | `ReadGeo` node | Static geometry |
| Toolset (.nk) | Paste nodes | Full node graph |

**Post-Import Hook:**
If configured in Settings, the post-import processor runs after node creation for custom setup (OCIO, expressions, etc.).

---

## Database Query Details

### Loose Match Query
```sql
SELECT * FROM elements 
WHERE name LIKE '%search_text%' 
COLLATE NOCASE
```

### Strict Match Query
```sql
SELECT * FROM elements 
WHERE name = 'search_text'
```

**Performance Notes:**
- Loose matches scan entire property column
- For large catalogs (10,000+ elements), strict matches are faster
- Index exists on `name`, `type`, and `format` columns

---

## Non-Modal Behavior

The Advanced Search dialog is **non-modal**, meaning:
- ✅ You can interact with main window while search is open
- ✅ Perform multiple searches without closing dialog
- ✅ Continue browsing stacks/lists in background
- ✅ Search results persist until new search executed

**Tip:** Keep the search dialog open as a "quick find" tool while working.

---

## Troubleshooting

### No Results Found

**Possible Causes:**
1. **Typo in search text** → Double-check spelling
2. **Wrong match type** → Try loose instead of strict
3. **Wrong property** → Element property may be in different field
4. **Empty database** → Ingest files first

**Solutions:**
- Use loose match for exploration
- Try searching different properties
- Verify elements exist in database (check MediaDisplayWidget)

### Too Many Results

**Solutions:**
1. Switch to strict match type
2. Be more specific in search text
3. Use different property (e.g., `format` instead of `name`)
4. Add comments/tags to elements for better filtering

### Search is Slow

**If searching 10,000+ elements:**
- Use strict match (faster)
- Search indexed properties (`name`, `type`, `format`)
- Avoid searching `comment` field on large catalogs

---

## Future Enhancements (Beta/RC)

Planned features for upcoming releases:

- [ ] **Multi-property search:** Combine filters (name AND format)
- [ ] **Search history:** Recall previous searches
- [ ] **Saved searches:** Store frequently-used queries
- [ ] **Fuzzy matching:** Typo-tolerant searches
- [ ] **Date range filters:** Search by ingestion date
- [ ] **Preview in results:** Thumbnail column
- [ ] **Export results:** CSV export of search results

---

## Related Documentation

- **Basic Search:** See `GUI_GUIDE.md` for live search in MediaDisplayWidget
- **Media Info Popup:** `MEDIA_INFO_POPUP.md` for Alt+Hover element details
- **Database Schema:** `instructions.md` Section III.C for property definitions
- **Ingestion:** `QUICKSTART.md` for adding elements to search

---

**Version:** 0.1.0 (Beta)  
**Last Updated:** December 2024  
**Shortcut:** `Ctrl+F`
