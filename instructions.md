## Advanced AI Agent Development Prompt: Clone of VFX Asset Management Pipeline (`StaX`)

This prompt instructs an AI coding agent to develop a clone of the Cragl smartElements application, herein referred to as the **Target Application**. The clone must adhere strictly to the identified functionality and architecture detailed in the "Analyzing SmartElements Documentation" research.

---

### I. Project Mandate & Technical Stack

**Project Goal:** Develop a feature-complete, highly extensible media browser and asset management system clone designed for professional VFX pipeline integration.

**Target Name:** `StaX`

**Core Technology Stack:**

| Component | Specification | Rationale |
|---|---|---|
| **Programming Language** | Python 2.7 | Industry standard for VFX pipeline tools and Nuke interaction. |
| **GUI Framework** | PySide2 | Required for cross-platform GUI and Nuke's embedded Qt environment. |
| **Database** | SQLite (File-based, network shared) | Simple, file-based database for managing centralized metadata across networked machines. |
| **Asset Storage** | Network File System (Simulated via config) | Must read/write to a configurable base repository path to simulate shared stacks. |
| **Host Application** | Foundry Nuke (Simulated via Python API calls) | Requires a dedicated *Nuke Bridge* module to handle DAG operations. |

### II. Software Architecture and Data Model

The agent must implement a modular, three-tier architecture: **GUI (PySide2)**, **Core Logic (Python)**, and **Data Layer (SQLite)**.

#### A. Data Layer Design (SQLite Schema)

The database must be designed to support the Target Application's hierarchical categorization and collaborative features:

**Table 1: Stacks (Primary Categories)**

| Field | Data Type | Constraints | Description |
|---|---|---|---|
| `stack_id` | INTEGER | PRIMARY KEY, AutoIncrement | Unique Stack identifier. |
| `name` | TEXT | UNIQUE, NOT NULL | e.g., "Plates," "3D Assets." |
| `path` | TEXT | UNIQUE, NOT NULL | Physical path on the network where assets for this stack are stored. |

**Table 2: Lists (Sub-Categories)**

| Field | Data Type | Constraints | Description |
|---|---|---|---|
| `list_id` | INTEGER | PRIMARY KEY, AutoIncrement | Unique List identifier. |
| `stack_fk` | INTEGER | FOREIGN KEY (Stacks) | Links list to its parent stack. |
| `name` | TEXT | NOT NULL | e.g., "Cityscape," "Explosions." |

**Table 3: Elements (Assets)**

| Field | Data Type | Constraints | Description |
|---|---|---|---|
| `element_id` | INTEGER | PRIMARY KEY, AutoIncrement | Unique asset identifier. |
| `list_fk` | INTEGER | FOREIGN KEY (Lists) | The specific sub-category list. |
| `name` | TEXT | NOT NULL | Display name of the asset. |
| `type` | TEXT | NOT NULL | Enum: `2D`, `3D`, `Toolset`. |
| `filepath_soft` | TEXT | | Original path (used for soft copy). |
| `filepath_hard` | TEXT | | Repository path (used for hard copy). |
| `is_hard_copy` | BOOLEAN | NOT NULL | True if physical copy, False if soft copy/reference.[1] |
| `frame_range` | TEXT | | Detected frame range (e.g., `1001-1150`).[1] |
| `format` | TEXT | | File format (e.g., `.exr`, `.abc`, `.mov`).[1] |
| `comment` | TEXT | | User-defined comment.[1] |
| `tags` | TEXT | | Comma-separated tags for advanced searching.[2] |
| `preview_path` | TEXT | | Path to generated thumbnail/video preview file.[1] |
| `is_deprecated` | BOOLEAN | DEFAULT False | Feature for asset lifecycle management.[2] |

**Table 4: Playlists, Tags, and Favorites (Collaborative/User Data)**

Design required supporting Playlists (shared collaborative lists) and local Favorites (per-user/per-machine data).[2, 1]

#### B. Software Modules

1.  **`db_manager.py`:** Handles all SQLite interactions (CRUD operations, schema management). Must be network-aware.
2.  **`ingestion_core.py`:** Manages file system operations (copy/reference), metadata extraction, image sequence detection, and preview generation.[1]
3.  **`nuke_bridge.py`:** Contains functions executed *within* the Nuke environment for insertion (`ReadNode`, `ReadGeoNode`, Paste nodes) and registration (toolsets, media nodes).[1]
4.  **`extensibility_hooks.py`:** Defines the Custom Processor architecture (see Section V).
5.  **`gui_main.py`:** The primary PySide2 application, handling D&D, viewing modes, and UI elements.

### III. Core GUI and Interaction Features

The PySide2 application must implement the following UI elements and behaviors:

1.  **Dual Operation:** Must function as a standalone application and a callable Nuke panel.[2]
2.  **Main Window Layout:** Must include dedicated, toggleable panels:
    *   **Stacks/Lists Navigation Panel:** Left sidebar for selecting Stacks and Lists.[2]
    *   **Media Display Area:** Center pane for viewing elements.
    *   **History Panel:** Separate toggleable panel (accessible via simulated `Ctrl + 2`) for logging ingestion events.[1]
    *   **Settings Panel:** Separate toggleable panel (accessible via simulated `Ctrl + 3`) for configuring ingest defaults and processors.[1]
3.  **Viewing Modes:** Must support a toggle for:
    *   **Gallery View / Thumbnail View:** Large visual preview.[2, 1]
    *   **List View:** Displays tabular data columns: `name`, `format`, `frames`, `type`, `size`, `comment`.[1]
    *   *Element Sizing:* Implement a slider to dynamically control the size of elements in the display area.[1]
4.  **Media Information Preview:** Implement a non-modal popup panel activated by hovering over an element while holding the `Alt` key.[1] This panel must contain:
    *   Large media preview (with video toggle for animated sequences).
    *   Extracted metadata.
    *   **Insert** button (calls Nuke Bridge).
    *   **Reveal** button (opens OS file explorer to the media location).[1]

### IV. Essential Pipeline Workflows

The clone must replicate the sophisticated ingestion and retrieval mechanisms:

#### A. Ingestion Workflow (`ingestion_core.py`)

1.  **Input Handling:** Accept drag-and-drop of single files, multiple files, or folders.[1]
2.  **Sequence Detection:** If a single image file is dropped, the system must automatically detect and confirm the whole image sequence and its frame range.[1]
3.  **Custom Code Execution:** Call the **Custom Pre-Ingest Processor Hook** (see Section V).
4.  **Core Ingestion Steps:**
    *   **Data Copy Policy:** Based on user settings, perform a **hard copy** (physical file duplication to the Stack repository) or a **soft copy** (store reference path only).[1]
    *   **Preview Generation:** Generate and store a low-resolution thumbnail preview (for footage/2D media).[1]
    *   **Metadata Extraction:** Extract and store properties (`frame_range`, `format`, `size`, etc.).[1]
5.  **Custom Code Execution:** Call the **Custom Post-Ingest Processor Hook** (see Section V).
6.  **Logging:** Record the ingestion event in the History section and generate an exportable **Ingestion CSV log**.[1, 3]

#### B. Nuke Integration and Retrieval (`nuke_bridge.py`)

1.  **Insertion into DAG (Drag & Drop):**
    *   When an element is dropped into a simulated Nuke DAG, the system must:
        *   If **2D/Footage:** Create and configure a Nuke `Read` node pointing to the correct path/frame range.[1]
        *   If **3D Data** (`.abc`, `.obj`, `.fbx`): Create and configure a Nuke `ReadGeo` node.[1]
        *   If **Toolset** (`.nk` fragment): Execute a paste function to add the nodes to the DAG.[1]
2.  **Toolset Creation:** Implement the `register selection as toolset` command, which launches a configuration dialog to capture `Name`, target `List`, `Comment`, and optional `Preview` image/video, then saves the selected node structure as a reusable asset.[1]
3.  **Auto Registering Renderings:** Implement a configuration toggle in the Settings panel (`Ctrl + 3`) to hook into a simulated Nuke `Write` node's execution and automatically ingest the output as a new Element upon render completion.[1] This hook must include logic for selecting a default target list for the rendering.

### V. Advanced Features and Extensibility

#### A. Search and Filtering

Implement robust asset discovery mechanisms:

1.  **Live Filter:** Implement instantaneous filtering of the element display as the user types.[2, 3]
2.  **Advanced Search:** Implement a search bar allowing the user to construct criteria based on three parameters:
    *   **Property Selection:** Target `name`, `format`, `frames`, `type`, or `comment`.[1]
    *   **Match Type:** Choose between `loose` (partial match) or `strict` (exact match).[1]
3.  **Favorites:** Implement a local, per-user Favorites system for quick access to frequently used media.[1]

#### B. Custom Processor Architecture (Critical Extensibility)

The application must support the execution of external, user-defined Python scripts at key moments in the workflow. This is mandatory for professional pipeline integration.[2]

1.  **Ingest Processors:**
    *   **Pre-Ingest Hook:** Execute a script *before* the hard copy and metadata extraction (e.g., for file validation, naming enforcement).[2]
    *   **Post-Ingest Hook:** Execute a script *after* the asset is cataloged (e.g., for injecting project-specific metadata, notifying external asset management systems).[2]
2.  **Import Processors:**
    *   **Post-Import Hook:** Execute a script *after* the Nuke Read/ReadGeo/Paste operation, allowing custom code to configure the newly created nodes (e.g., automatically setting OCIO transforms, applying expressions).[2]

The Settings Panel must include specific configuration fields (`Ingest processor settings`, `Import processor settings`) to define the file paths to these custom Python scripts.[2]

## Project documentation files to create

Add the following documentation files to the repository root as part of the initial project setup. These files should be created and kept up-to-date by the development team.

1. Roadmap.md
    - Purpose: A high-level roadmap describing planned features, phased milestones, timelines, and owners for the `StaX` project.
    - Content guidance: Include sections for Vision, Release Phases (Alpha/Beta/Stable), Feature list by phase, Milestones & Dates (approximate), Dependencies, and Notes on risk/priority.
    - Location: Repository root, filename `Roadmap.md`.

2. changelog.md
    - Purpose: A chronological record of continuous changes, releases, and notable commits for the project.
    - Content guidance: Use the Keep a Changelog format (Unreleased, [Unreleased] heading, then versioned headings). Include date, summary of changes, and links to related issues/PRs where applicable.
    - Location: Repository root, filename `changelog.md`.

These two files should be created now as part of the initial commit and kept current with every significant change.