# StaX Roadmap

This document outlines the high-level roadmap, release phases, planned features, milestones, and suggested owners for the StaX project. It is intended to be a living document and should be updated as priorities shift.

## Vision

Provide a professional-grade, extensible media browser and asset management hub optimized for VFX pipelines and integration with Foundry Nuke. Support collaborative workflows, fast ingest, robust search, and programmable extensibility.

## Release Phases

- Alpha (MVP) — Core functionality, local-only operation, minimal GUI, ingestion, basic SQLite DB, and simple Nuke Bridge simulation.
- Beta — Add network-aware database behavior, complete GUI features (gallery/list views, history, settings), preview generation, and basic extensibility hooks.
- Release Candidate — Stability improvements, performance tuning, full processor hook support, automated tests, packaging, and documentation.
- Stable — Production-ready integration, cross-platform packaging, user management, and enterprise features.

## Phase: Alpha (MVP)
Timeline: 2–4 weeks (initial sprint)

Goals:
- Implement core data model and `db_manager.py` with schema creation for Stacks, Lists, Elements, and Favorites.
- Implement `ingestion_core.py` supporting drag-and-drop ingestion, sequence detection, metadata extraction, soft/hard copy policy, and preview thumbnail creation (mocked/resampled images acceptable for MVP).
- Add `nuke_bridge.py` with simulated Read/ReadGeo/Paste functions for local testing (no Nuke dependency required for Alpha).
- Basic `main.py` using PySide2 with Stacks/Lists navigation, media display area, simple list/gallery toggle, and history panel.
- Create minimal unit tests for DB and ingestion core.

Suggested owners: Backend lead (db, ingestion), UI dev (PySide2 layout), QA (tests).

Milestones:
- M1: Schema and DB manager implemented.
- M2: Ingest single file and add Element to DB, generate preview.
- M3: Basic GUI that can display Elements from DB.

## Phase: Beta
Timeline: 4–8 weeks

Goals:
- Full GUI features (element sizing slider, media info popup, reveal/insert actions wired to `nuke_bridge` simulated functions).
- Implement Playlists, per-user Favorites, advanced search and live filtering.
- Extensibility: `extensibility_hooks.py` with pre/post ingest processors and import processors; settings panel to configure processor scripts.
- Network-aware SQLite usage (file locking, configuration for shared repo path) and improved error handling.
- Implement preview generation for sequences and short video previews for animated media where feasible.

Milestones:
- M4: Extensibility hooks integrated into ingestion workflow.
- M5: Advanced search and live filtering implemented.
- M6: Settings panel complete with processor configuration.

## Phase: Release Candidate
Timeline: 2–4 weeks

Goals:
- Automated tests for ingestion, DB operations, and processor hook execution.
- Simulate or integrate with a Nuke environment for more realistic Read/ReadGeo operations (optional mocks for CI).
- Packaging scripts and platform-specific installers or wheels.
- Performance tuning for large catalogs; lazy-loading thumbnails and pagination.

Milestones:
- M7: Test coverage reaches target (e.g., 70%+ for core modules).
- M8: Packaging and installer prototypes.

## Phase: Stable
Timeline: ongoing

Goals:
- Production hardening, user management, permissions, and audit trails.
- Integrations: external asset management and CI hooks, cloud-storage backends, and multi-user concurrency improvements.
- Documentation: user guides, API docs for processor hooks, and deployment guides.

Milestones:
- M9: Production deployment checklist completed.
- M10: Enterprise integrations documented.

## Feature List (by priority)

High Priority:
- SQLite schema & DB manager
- Ingestion pipeline with sequence detection
- PySide2 GUI with gallery/list toggle and element sizing
- Basic Nuke Bridge simulation
- Extensibility hooks (pre/post ingest, post-import)

Medium Priority:
- Preview video generation for sequences
- Playlists and Favorites
- Live filtering and advanced search
- Auto-register renderings from simulated Write nodes

Low Priority / Future:
- User/permission management
- Cloud storage backends
- Integrated remote indexing service

## Risks & Mitigations
- Nuke integration is environment-specific: mitigate with a clear abstraction layer (`nuke_bridge`) and mock implementations for development and CI.
- File-lock/concurrency on SQLite: mitigate with careful file locking strategies and guidance for networked SQLite usage.
- Preview generation can be slow on large assets: implement async processing and queue workers for heavy tasks.

## Owners & Contacts
- Ahmed Ramadan

## Notes
Update this roadmap at the start of each sprint. Use `changelog.md` to record releases and significant merges to track progress against the roadmap.
