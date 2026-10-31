# Technical Architecture & System Design

## 1. Technology Stack Evaluation & Selection

### 1.1 Candidate Evaluation

| Criteria | C# (.NET 8/9 + WPF) | C# (WinUI 3 / App SDK) | Python 3.12 + PySide6 (Qt 6) |
|---|---|---|---|
| **Environment Readiness** | ❌ .NET SDK missing on machine | ❌ WinUI 3 SDK missing on machine |  **Installed & Fully Verified** (Python 3.12, PySide6 6.12, PyInstaller 6.22) |
| **GUI Quality & Ergonomics**| Good (Native Win32 controls) | Modern Fluent Design (Windows 11) |  Modern, responsive Qt 6 with custom styling, high-DPI support, dark/light modes |
| **Engine Decoupling** | High (Task Parallel Library) | High (C# async/await) |  **Exceptional** (Clean separation via Qt Signals/Slots and worker threads) |
| **Memory Footprint** | ~50–90 MB | ~80–150 MB |  **Low (~40–75 MB)** with native Qt C++ rendering backend |
| **Networking Performance** | Fast (`SocketsHttpHandler`) | Fast (`HttpClient`) |  **Fast (`httpx` / `httpcore` / streaming raw sockets)** |
| **Database & Persistence** | Microsoft.Data.Sqlite | Microsoft.Data.Sqlite |  **Built-in `sqlite3`** (WAL mode, zero extra dependencies) |
| **Standalone Distribution** | Single-file publish (needs SDK) | Complex MSIX / unpackaged setup |  **Clean portable `.exe` via PyInstaller** |
| **Development Cycle** | Requires installing multi-GB SDK | Requires Visual Studio / App SDK |  **Instant, iterative test-driven development** |

### 1.2 Architectural Recommendation
**Selected Stack: Python 3.12 + PySide6 (Qt 6)**
- **Rationale:** The environment already has Python 3.12, PySide6 6.12, `httpx`, and `pyinstaller` installed. PySide6 delivers production-grade desktop controls backed by Qt's C++ rendering engine. It satisfies every personal-use constraint: zero external cloud dependencies, lightweight memory footprint, robust thread synchronization, and seamless standalone portable `.exe` compilation.

---

## 2. High-Level Architectural Diagram

```
+-----------------------------------------------------------------------------------+
|                                 USER INTERFACE                                    |
|                               (PySide6 / Qt 6)                                    |
|                                                                                   |
|  +--------------------+  +----------------------+  +---------------------------+  |
|  |   Main Window      |  |   Add URL Dialog     |  |  Segment Progress Dialog  |  |
|  | - ToolBar / Menus  |  | - URL & Path picker  |  | - Real-time metrics       |  |
|  | - Category Tree    |  | - Credentials        |  | - Segment visualization   |  |
|  | - Download Table   |  | - Category auto-pick |  | - Pause / Resume / Cancel |  |
|  +---------+----------+  +----------+-----------+  +-------------+-------------+  |
|            |                        |                            |                |
|            +------------------------+----------------------------+                |
|                                     | Qt Signals / Slots                          |
+-------------------------------------v---------------------------------------------+
|                                CORE CONTROLLER                                    |
|  +-----------------------------------------------------------------------------+  |
|  |                            DownloadCoordinator                              |  |
|  | - Manages download queues (concurrency limits, priority)                    |  |
|  | - Routes UI commands to active DownloadTasks                               |  |
|  | - Emits state updates, aggregated speeds, and completion events             |  |
|  +-------------------+-----------------------------------+---------------------+  |
|                      |                                   |                        |
+----------------------v-----------------------------------v------------------------+
|               PERSISTENCE LAYER                |          NETWORK ENGINE          |
|  +------------------------------------------+  |  +----------------------------+  |
|  |             DatabaseManager              |  |  |        DownloadTask        |  |
|  | - SQLite (WAL mode, ACID)                |  |  | - Inspects headers (HEAD)  |  |
|  | - Schema: tasks, segments, settings      |  |  | - Allocates byte ranges    |  |
|  | - Transactional checkpointing            |  |  | - Manages worker threads   |  |
|  +------------------------------------------+  |  +-------------+--------------+  |
|                                                |                |                 |
|                                                |  +-------------v--------------+  |
|                                                |  |       SegmentWorker        |  |
|                                                |  | - HTTP Range GET requests  |  |
|                                                |  | - Streaming byte reader    |  |
|                                                |  | - Token bucket throttler   |  |
|                                                |  | - Writes to segment buffer |  |
|                                                |  +-------------+--------------+  |
+------------------------------------------------+----------------v-----------------+
|                                 STORAGE & I/O                                     |
|  +-----------------------------------------------------------------------------+  |
|  |                             FileManager                                     |  |
|  | - Safe filename resolution & anti-collision (`file (1).ext`)                |  |
|  | - Temporary chunk storage (`.pdm_part_N`)                                   |  |
|  | - Fast sequential segment assembly & stream merging                         |  |
|  | - Post-assembly SHA-256 integrity verification                              |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
|                          OPTIONAL BROWSER EXTENSION HOST                          |
|  +-----------------------------------------------------------------------------+  |
|  | Native Messaging Bridge (stdin / stdout JSON RPC)                           |  |
|  | - Receives user-approved URL handoffs from Chrome, Edge, and Firefox        |  |
+-----------------------------------------------------------------------------------+
```

---

## 3. Core Subsystems & Components

### 3.1 Storage & Persistence (`DatabaseManager`)
- **Technology:** Python `sqlite3` using **Write-Ahead Logging (WAL)** (`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`).
- **Entity Schema:**
  - `downloads`: `id`, `url`, `destination_path`, `filename`, `total_bytes`, `downloaded_bytes`, `status` (`Queued`, `Downloading`, `Paused`, `Completed`, `Error`), `etag`, `last_modified`, `supports_range`, `connections_count`, `category`, `created_at`, `completed_at`.
  - `segments`: `id`, `download_id`, `segment_index`, `start_byte`, `end_byte`, `downloaded_bytes`, `status`, `temp_filepath`.
  - `settings`: Key-value configuration table (default download path, max concurrent downloads, max connections per file, clipboard monitoring flag, global speed limit).
- **Integrity Guarantee:** Periodic atomic commits (every 1-2 seconds and on pause/stop) to guarantee that crash recovery resumes exactly from the last verified byte boundary.

### 3.2 Network Engine & Dynamic Segment Allocator
- **Probe Phase:**
  - Issues `HEAD` request (or `GET` with `Range: bytes=0-0` if `HEAD` is blocked) to determine:
    1. Content-Length (Total file size)
    2. Range acceptance (`Accept-Ranges: bytes` or `206 Partial Content`)
    3. Validators (`ETag`, `Last-Modified`)
    4. Suggested filename (`Content-Disposition: attachment; filename="..."`)
- **Dynamic Segment Allocation (IDM-Inspired In-Half Rule):**
  - If `supports_range == False` or file size is unknown (`Content-Length == None`), fallback to **1 connection** (single linear stream).
  - If `supports_range == True`:
    1. Initial segment starts at `[0, total_bytes - 1]`.
    2. Connection 1 begins reading from offset 0.
    3. As connection slots 2..$N$ open up (up to configured max, e.g. 8 connections):
       - Find the active segment with the largest remaining undownloaded range (`(end_byte - current_byte)`).
       - If `remaining >= MIN_SEGMENT_SIZE` (default 512 KB):
         - Split point: `mid = current_byte + (end_byte - current_byte) // 2`.
         - Original worker keeps `[current_byte, mid]`.
         - New worker is assigned `[mid + 1, end_byte]`.
    4. Worker reuse: When a worker finishes its assigned range, it queries the coordinator for another segment to split rather than idling.
- **Segment Writing & Assembly:**
  - Each worker writes to a dedicated segment part file: `<destination_path>.pdm_part_<segment_id>`.
  - Upon 100% completion of all segments:
    - Pre-allocate destination file.
    - Sequentially read from part files in 64 KB / 1 MB chunks and append to the final file.
    - Delete temporary part files.
    - Set final file modified time to match server's `Last-Modified` (if available).
    - Mark task `Completed` in SQLite.

### 3.3 Speed Limiter (Token Bucket Algorithm)
- Shared `TokenBucket` instance per task (and one global instance).
- Workers acquire byte tokens before reading from the response socket stream.
- If tokens are exhausted, the worker sleeps for the calculated interval, enforcing exact throughput caps smoothly without erratic jitter.

### 3.4 Decoupled GUI Architecture
- **Thread Safety:** The PySide6 GUI thread **never** touches network sockets or heavy disk I/O.
- **Signals/Slots Bridge:**
  - Download workers emit thread-safe signals:
    - `progress_updated(task_id, downloaded_bytes, speed_bps, eta_seconds)`
    - `segment_updated(task_id, segment_index, start, current, end)`
    - `status_changed(task_id, new_status, error_message)`
    - `download_completed(task_id, final_path)`
  - GUI updates are throttled (e.g. at 10 Hz / 100ms intervals) via Qt timer to prevent UI thread lockup even at gigabit network throughput.

---

## 4. Security Architecture & Threat Modeling

1. **Path Traversal Protection (`FileManager`):**
   - Server-supplied filenames via URL or `Content-Disposition` are strictly untrusted.
   - Filtered through a strict sanitization function:
     - Strips directory traversal sequences (`..`, `/`, `\`).
     - Removes Windows-reserved characters: `< > : " / \ | ? *` and control characters ($0 \le c < 32$).
     - Strips Windows-reserved device names: `CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`.
     - Canonicalizes destination directory with `os.path.realpath` and verifies that the output file resides strictly inside the user's chosen target directory.
2. **TLS Verification:**
   - Always enabled. Custom certificates and CA bundles verified through system store and `certifi`.
   - Never accept insecure flags or options to bypass TLS verification.
3. **No Automatic Code Execution:**
   - Downloaded executable files (`.exe`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.msi`) are saved passively.
   - PDM never executes downloaded files automatically. Launching requires explicit user interaction (*Open File*).
4. **Safe Temporary Files:**
   - Temporary segment files are isolated alongside the destination with `.pdm_part_*` suffix or inside a designated user-scoped cache folder with restricted permissions (`0o700`).
5. **Safe IPC (Browser Extension Handoff):**
   - Implements Chrome/Edge/Firefox Native Messaging standard (length-prefixed JSON on stdin/stdout).
   - Validates caller extension ID against an explicit allowlist.
   - Rejects any command that attempts arbitrary process execution or path overrides outside safe boundaries.
