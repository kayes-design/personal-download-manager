# Implementation Roadmap & Milestone Plan

This roadmap outlines the phased development plan for the **Independent Personal Download Manager (PDM)**. 

Development is strictly incremental: each phase builds, tests, and verifies concrete deliverables before proceeding to the next.

---

## Phase 1: Foundation & Core Download Engine (No GUI)
**Objective:** Build and test a rock-solid, standalone network download engine that handles single-stream and multi-connection range downloads, crash-recovery persistence, and safe assembly.

- **Milestone 1.1: Local Test Server Harness & Security Primitives**
  - Implement a dedicated local HTTP test server (`tests/local_test_server.py`) supporting:
    - Normal full downloads (HTTP 200)
    - Byte range downloads (HTTP 206, `Range: bytes=X-Y`)
    - Servers explicitly disallowing Range (ignoring Range and returning full 200)
    - Simulated network disconnects, slow throttled streams, and redirects (301, 302, 307)
    - ETag and Last-Modified validation
  - Implement `security.py`: Safe URL parsing, path traversal blocker, Windows reserved filename sanitization, collision naming (`file (1).ext`).
- **Milestone 1.2: SQLite Persistence Layer (`DatabaseManager`)**
  - Schema setup (`downloads`, `segments`, `settings`) in WAL mode.
  - CRUD operations for download tasks, state checkpoints, and segment byte ranges.
- **Milestone 1.3: Dynamic Segment Allocator & Workers**
  - Implement `DownloadEngine`, `DownloadTask`, and `SegmentWorker`.
  - Dynamic in-half range splitting algorithm.
  - Sequential segment assembly with integrity validation.
  - Automated unit and integration tests passing against the local test harness.

---

## Phase 2: Core Desktop User Interface (PySide6)
**Objective:** Deliver a responsive, modern Windows desktop GUI connected cleanly to the Phase 1 engine.

- **Milestone 2.1: Main Window Shell & Navigation**
  - Top action toolbar: Add URL, Pause, Resume, Stop, Delete, Settings.
  - Left navigation panel: Category tree (All, Compressed, Documents, Music, Programs, Video) and Queues.
  - Status bar: Aggregated download speed, active task count, free disk space indicator.
- **Milestone 2.2: High-Performance Download Table**
  - Virtual `QTableView` backed by `QAbstractTableModel` for smooth scrolling.
  - Columns: File Name, Size, Progress Bar, Status, Speed, Time Left, Category, Date Added.
  - Right-click context menu (Pause, Resume, Open File, Open Folder, Delete from Disk, Properties).
- **Milestone 2.3: Dialogs & Custom Widgets**
  - **Add URL Dialog:** Auto-populates clipboard URL, category detector, save directory chooser.
  - **Download Progress Dialog:** Shows overall progress and the custom-painted **Segment Strip Widget** displaying active connection chunks in real-time.
  - **Download Complete Notification:** Toast / system notification with Open / Open Folder buttons.

---

## Phase 3: Advanced Download Features & Queue Management
**Objective:** Add user productivity features, queue scheduling, and bandwidth management.

- **Milestone 3.1: Queue Controller & Concurrency**
  - Global concurrent download limit (e.g. download 2 files concurrently, queue remaining).
  - Priority ordering (Move Up, Move Down).
- **Milestone 3.2: Bandwidth Limiter (Token Bucket)**
  - Configurable global speed limit and per-download speed limit.
- **Milestone 3.3: Clipboard Monitoring (Opt-in)**
  - Background clipboard watcher prompting the Add URL dialog when a download link is copied.
- **Milestone 3.4: File Integrity Checker**
  - Checksum dialog computing SHA-256 and MD5 on completed downloads.
- **Milestone 3.5: Optional Scheduled Start / Stop & System Shutdown**
  - Scheduled queue timer and safe shutdown trigger with user-cancel grace period.

---

## Phase 4: Browser Integration Module (Native Messaging)
**Objective:** Provide a lightweight, user-approved browser handoff module without invasive system hooks.

- **Milestone 4.1: Native Messaging Host**
  - Lightweight executable or Python script implementing Chrome/Edge/Firefox Native Messaging protocol (standard JSON on stdin/stdout).
  - Registers host manifest in `HKCU\Software\Google\Chrome\NativeMessagingHosts` and `HKCU\Software\Mozilla\NativeMessagingHosts`.
- **Milestone 4.2: WebExtension Proof-of-Concept**
  - Context menu item: "Download with PDM".
  - Passes target URL, referer, and cookies to PDM desktop application with explicit user consent.

---

## Phase 5: Packaging, Standalone Distribution & Verification
**Objective:** Build a self-contained, portable Windows executable and perform end-to-end audit.

- **Milestone 5.1: Standalone Portable Packaging**
  - PyInstaller configuration producing a single self-contained portable executable (`PDM.exe`).
  - Embedded application icon, version resource, and high-DPI manifest.
- **Milestone 5.2: End-to-End Stress & Verification Testing**
  - Large file test (multi-gigabyte downloads).
  - Power cut / sudden process termination recovery test.
  - Memory leak and CPU usage profiling during active multi-segment downloads.
