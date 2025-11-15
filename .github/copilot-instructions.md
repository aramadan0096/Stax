# Copilot Instructions for VFX_Asset_Hub

## Project Overview
VFX_Asset_Hub (VAH) is a professional VFX asset management pipeline clone targeting the Cragl smartElements feature set. This is a **greenfield project** currently in the planning/documentation phase with no implementation yet.

**Status:** Pre-Alpha (documentation complete, implementation pending)  
**Target:** Feature-complete media browser for VFX studios integrating with Foundry Nuke

## Critical Design Decisions

### Technology Stack Rationale
- **Python 2.7**: Hard requirement for VFX pipeline compatibility and Nuke integration (not Python 3)
- **PySide2**: Required for Qt-based GUI that embeds in Nuke's environment
- **SQLite**: File-based database designed for network sharing across workstations
- **No external asset management systems**: Self-contained solution with extensibility hooks

### Three-Tier Architecture
```
GUI Layer (gui_main.py)
    ↓
Core Logic (ingestion_core.py, extensibility_hooks.py)
    ↓
Data Layer (db_manager.py → SQLite)
    ↓
Nuke Bridge (nuke_bridge.py - abstraction for Nuke API)
```

**Key architectural pattern**: The `nuke_bridge.py` module must be a pure abstraction layer that can run in mock mode for development/testing without Nuke installed, but executes real Nuke Python API calls in production.

## Database Schema Hierarchy
The data model follows a strict 3-level hierarchy critical to all features:
```
Stacks (Primary Categories: "Plates", "3D Assets")
  └─ Lists (Sub-Categories: "Cityscape", "Explosions")
      └─ Elements (Individual Assets with metadata)
```

**Elements Table** is the richest entity with dual-path architecture:
- `filepath_soft`: Original location (for soft-copy references)
- `filepath_hard`: Repository location (for physical copies)
- `is_hard_copy`: Boolean determining which path to use

This dual-path system is fundamental to the "hard copy vs soft copy" ingestion policy.

## Core Workflows & Execution Order

### Ingestion Pipeline (Critical Sequence)
1. Drag & drop handling → Sequence detection (automatic frame range discovery)
2. **Pre-Ingest Processor Hook** (user script execution point)
3. Hard/soft copy operation based on settings
4. Preview thumbnail generation
5. Metadata extraction → Database insert
6. **Post-Ingest Processor Hook** (user script execution point)
7. History logging + CSV export

**Important**: Sequence detection must scan filesystem for `filename.####.ext` patterns and detect frame ranges automatically when a single frame is dropped.

### Nuke Integration Pattern
When dragging Elements from VAH into Nuke:
- **2D assets** → Create `Read` node with correct frame range
- **3D assets** (.abc, .obj, .fbx) → Create `ReadGeo` node
- **Toolsets** (.nk) → Paste node graph into DAG

All Nuke operations go through `nuke_bridge.py` with fallback to mock implementations.

## Extensibility System (Custom Processors)

The Custom Processor architecture is **mandatory** for professional pipeline integration:

### Three Hook Points
1. **Pre-Ingest**: Execute before file copy (validation, naming enforcement)
2. **Post-Ingest**: Execute after cataloging (external system notifications)
3. **Post-Import**: Execute after Nuke node creation (OCIO setup, expressions)

**Implementation requirement**: Settings panel must allow users to specify Python script paths for each hook. The system must safely execute these user scripts with proper error handling and context passing.

## GUI Patterns & Keyboard Shortcuts

### Panel System
All panels are toggleable and stored in user preferences:
- **Stacks/Lists Navigation**: Left sidebar (always visible in MVP)
- **Media Display**: Center pane with Gallery/List view toggle
- **History Panel**: `Ctrl + 2` toggle
- **Settings Panel**: `Ctrl + 3` toggle

### Media Info Popup (Non-Modal)
- Trigger: Hover over Element while holding `Alt` key
- Must include: Preview, metadata, Insert button, Reveal button
- **Reveal button** opens OS file explorer to asset location

### View Modes
- **Gallery View**: Large thumbnail grid with element sizing slider
- **List View**: Table with columns: name, format, frames, type, size, comment

## Development Workflow

### Current Phase: Alpha (MVP)
Focus on these modules in order:
1. `db_manager.py` - Schema creation and CRUD operations
2. `ingestion_core.py` - File operations and metadata extraction
3. `gui_main.py` - Basic PySide2 layout with Stacks/Lists navigation
4. `nuke_bridge.py` - Mock implementations for Read/ReadGeo/Paste

**Testing strategy**: All modules must work without Nuke installed. Use mock implementations and simulate Nuke API responses.

### Network-Aware SQLite
- Database file must support concurrent access from multiple workstations
- Implement file locking and retry logic in `db_manager.py`
- Configuration must specify shared network path for database location

### Preview Generation
- Generate low-res thumbnails for images (resample to ~512px)
- For sequences: Generate thumbnail from middle frame
- Video previews are Phase 2 (Beta) - use static thumbnails in Alpha

## Project Documentation Standards

### Living Documents (Update Regularly)
- `Roadmap.md`: Update at sprint start, reference current phase/milestones
- `changelog.md`: Update with every significant feature completion or bug fix
- Use Keep a Changelog format: `## [Unreleased]` → version headings on release

### When Adding Features
1. Check current phase in `Roadmap.md` - prioritize high-priority features
2. Update `changelog.md` under `[Unreleased]` section
3. Follow module structure defined in `instructions.md` Section II.B

## Common Pitfalls to Avoid
- Don't use Python 3 syntax/features (must be Python 2.7 compatible)
- Don't import `nuke` module outside `nuke_bridge.py` - maintain abstraction
- Don't implement async/await (not available in Python 2.7) - use threading
- Soft copy vs hard copy is not optional - dual-path system must work from Day 1
- Sequence detection is automatic and non-negotiable - never ask users to specify frame ranges manually

## Key Files Reference
- `instructions.md`: Complete technical specification (source of truth)
- `Roadmap.md`: Phase-based implementation plan and milestones
- `changelog.md`: Historical record of changes
