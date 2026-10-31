# IDM Reference Audit & Non-Invasive Observation Report

## 1. Audit Overview & Ethics Boundary

This audit was conducted strictly using non-invasive observation methods:
- File metadata inspection via Windows API
- Publicly installed end-user documentation (`idman.chm`, `tips.txt`, `defexclist.txt`)
- Public protocol documentation and standard RFC compliance (RFC 9110 HTTP Semantics, RFC 7233 HTTP Range Requests)
- Visible UI workflows and standard user interactions

**Explicit Boundary Confirmations:**
- No proprietary binaries were decompiled, disassembled, cracked, patched, or reverse-engineered.
- No licensing, registration, or activation mechanisms were inspected or modified.
- No private credential vaults or DRM mechanisms were probed.
- All technical insights and implementations described in this project are clean-room, independently authored software using standard networking protocols.

---

## 2. Environment & Target Identification

- **Host Operating System:** Microsoft Windows 11 Pro / Enterprise (NT Kernel Version 10.0.26300.0, 64-bit)
- **Target Application:** Internet Download Manager (IDM)
- **Detected File Path:** `C:\Program Files (x86)\Internet Download Manager\IDMan.exe`
- **Detected Version:** `6.43.16.2` (Product Version 6.43 Build 16)
- **Target Architecture:** Win32 (x86 executable running on x64 OS)

---

## 3. Visible System & UI Observations

### 3.1 Main Window Layout
IDM uses a classic, functional Windows layout composed of three primary zones:
1. **Top Control Toolbar:**
   - Action buttons: *Add URL*, *Resume*, *Stop*, *Stop All*, *Delete*, *Delete Completed*, *Options*, *Scheduler*, *Start Queue*, *Stop Queue*.
   - Dynamic enablement: Toolbar actions dynamically enable or disable based on item selection and state (e.g., *Resume* is only enabled for paused/errored tasks; *Delete Completed* is only active when completed items exist).
2. **Left Navigation Tree (Categories & Queues):**
   - **Categories:** All Downloads, Compressed, Documents, Music, Programs, Video.
   - **Queues:** Main Download Queue, Synchronization Queue, and user-defined custom queues.
3. **Central Download Task Table:**
   - Columns: File Name, Size, Status, Time Left, Transfer Rate, Last Try / Date, Category, Description, Queue indicator (`Q`).
   - Interactive behaviors: Sort by clicking column headers, double-click to open/execute (or open file properties), right-click context menu for granular operations.

### 3.2 Workflow & Dialog Flows
1. **Add URL Workflow:**
   - Triggered via Toolbar button, Clipboard detection, or Browser handoff.
   - Dialog automatically pre-fills URL detected in Windows Clipboard.
   - Fields: URL, Save Folder, File Name, Category (auto-detected by file extension), Authorization (HTTP Basic/Digest username and password), Checkbox to "Start Download Immediately" vs "Download Later (Add to Queue)".
2. **Active Download Progress Dialog:**
   - Displays real-time download metrics: Status, File Size, Downloaded Bytes, Transfer Rate, Time Left, Resume capability (`Yes` / `No`).
   - Dynamic segmentation visualization: A horizontal visual bar divided into segments, visually showing byte ranges being fetched across active network threads.
   - Granular controls: *Pause*, *Cancel*, speed limiter toggle, and "Hang up / Shutdown when done" options.
3. **Download Complete Dialog:**
   - Presents *Open*, *Open Folder*, and *Close* actions.

### 3.3 Core Network & Engine Mechanisms (As Stated in User Documentation)
From IDM's official user documentation (`Segmentation.htm`, `Options.htm`):
- **Dynamic File Segmentation:** Unlike static chunkers that divide a file into $N$ equal chunks at the start, IDM uses dynamic segmentation ("in-half division rule").
  - The first connection starts downloading from byte 0.
  - As new connections spin up or existing connections complete their assigned byte ranges, the engine identifies the largest remaining undownloaded contiguous byte range and splits it in half.
  - Idle connections are immediately reused to pull the latter half of the largest chunk.
  - Minimum segment threshold: Prevents splitting segments that are already very small (< 512 KB), avoiding TCP connection setup overhead for negligible gains.
- **Resumability Verification:**
  - Range support is detected via HTTP `Accept-Ranges: bytes` and `206 Partial Content` responses.
  - Resume state is persisted periodically to disk (byte offsets, temporary chunk boundaries) to survive application restarts, network disconnects, or sudden system halts.
  - Range validators: HTTP `ETag` and `Last-Modified` headers are checked on resume. If the server's ETag or timestamp changed, the file on server was modified, requiring restarting from byte 0 to prevent data corruption.
- **Segment Assembly:**
  - Once all segments reach 100%, segments are written/merged sequentially into the target destination file on the same storage volume.

---

## 4. Observations vs. Assumptions

| Feature / Aspect | Directly Observed / Documented | Assumption (Engineering Inference) |
|---|---|---|
| **Segmentation** | Dynamic split of largest remaining segment; minimum threshold avoids micro-splits. | Worker threads or async tasks coordinate over a shared byte-range allocator. |
| **Resumability** | Validated via `Accept-Ranges`, `ETag`, `Last-Modified`, and HTTP status `206`. | If a server returns `200 OK` on a Range request or changes ETag, engine must discard partial chunks and restart as single-stream. |
| **Temp Storage** | Temporary segment files are stored on disk and assembled upon completion. | Temporary segment parts can be written directly into pre-allocated sparse files or discrete `.partN` files and merged using streaming buffered I/O. |
| **Browser Handoff** | IDM uses browser extensions + native helper. | Modern browsers (Chrome, Edge, Firefox) prohibit arbitrary DLL injection and strictly require standard **WebExtensions Native Messaging** (JSON over stdin/stdout) to pass download URLs and cookies to desktop apps. |
| **Speed Limiting** | Global and per-task speed throttles are provided. | Implemented via token bucket algorithm or rate-limiting sleep cycles in socket read loops. |

---

## 5. What Could NOT Be Verified (Unverifiable / Out of Scope)

1. **Low-Level Network Driver Filter:** IDM historically used proprietary TDI/WFP network filter drivers for legacy browser hooks. This is neither verifiable nor desirable for a modern, secure, independent Python/PySide6 application.
2. **Proprietary Segment File Formats:** IDM's internal temp file binary structure was not probed; our implementation will use standard, transparent `.part` chunks or contiguous sparse files managed through an ACID SQLite database.
3. **DRM / Protected Stream Decryption:** IDM's video grabber mechanics on encrypted/protected media are outside legitimate protocol boundaries and are explicitly excluded.
4. **License & Registration Internals:** Completely avoided; our tool is 100% free, personal, and open.

---

## 6. Conclusions & Recommendations for Our Implementation

1. **Protocol Standards Only:** All downloading must strictly follow standard RFC 9110 (HTTP Semantics) and RFC 7233 (Range Requests).
2. **Dynamic Segment Allocator:** Implement an in-memory segment manager that starts with 1 connection, discovers server partial-content capabilities, expands to $N$ configured connections (e.g. 4 to 8 connections per download), and dynamically splits the largest remaining byte range.
3. **Safe Assembly & Disk Hygiene:** Cleanly assemble segments on completion, verify SHA-256 / MD5 checksums if provided, and safely handle filename collision using `file (1).ext` convention without data loss.
4. **Independent, Clean UI:** Deliver a fast, responsive, modern Windows interface built on Qt 6 / PySide6 with zero external cloud dependencies.
