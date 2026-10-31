# Feature Comparison Matrix

This matrix compares the observable features of commercial Internet Download Manager (IDM) against our **Independent Personal Download Manager (PDM)**.

Legend:
- **Core PDM**: Included in foundational implementation phases.
- **Enhanced PDM**: Planned in intermediate/advanced phases.
- **Excluded**: Explicitly excluded to protect personal security, maintain low complexity, or adhere to personal-use constraints.

---

## 1. Network & Download Capabilities

| Feature | IDM (Observed) | PDM Plan | Feasibility & Technical Strategy |
|---|---|---|---|
| **HTTP / HTTPS Downloads** | Supported (SSL/TLS, HTTP 1.1 / 2) | **Core PDM** | Standard TCP / TLS via Python `httpx` / `httpcore` engine with system certificates. |
| **HTTP Range / Partial Content** | Dynamic segmentation (up to 32 connections) | **Core PDM** | RFC 7233 Range requests: `Range: bytes=start-end`. Auto-split largest remaining range. Configurable max connections (default 4-8). |
| **Resumability & Validation** | Resumes if server returns 206 and matching ETag/Last-Modified | **Core PDM** | Strict check: HTTP `Accept-Ranges: bytes`, `ETag`, `Last-Modified`. Fallback to full re-download if server returns 200 or invalidates range. |
| **Fallback to Single Stream** | Automatically falls back if Range is unsupported | **Core PDM** | If `HEAD` or initial `GET` returns 200 without Range support, download executes on a single linear stream safely. |
| **Redirect Handling** | Follows 301, 302, 303, 307, 308 | **Core PDM** | Canonicalize URLs, strictly validate redirect loops (max 10), and preserve range semantics across the final endpoint. |
| **HTTP Authentication** | Basic, Digest, NTLM | **Core PDM** | Support HTTP Basic & Digest authentication via user-provided credentials in Add URL dialog. |
| **Speed Limiter** | Global & per-task rate limiting | **Enhanced PDM** | Token-bucket rate limiter throttling byte throughput per interval in the download engine loop. |
| **Auto-Retry & Reconnect** | Retries on network timeout or drop | **Core PDM** | Exponential backoff with configurable retry attempts (e.g. 5 retries with 5s delay). |
| **FTP Protocol** | Legacy FTP supported | **Excluded** | Modern web has almost entirely deprecated plain FTP. HTTP/HTTPS covers 99.9% of user use-cases; avoids obsolete protocol bloat. |

---

## 2. Queue & Task Management

| Feature | IDM (Observed) | PDM Plan | Feasibility & Technical Strategy |
|---|---|---|---|
| **Multiple Queues** | Main Queue, Sync Queue, Custom Queues | **Core PDM** | Queue manager with customizable max concurrent active downloads (e.g., 1-5 downloads at a time). |
| **Task State Persistence** | Preserved across restarts in registry / disk | **Core PDM** | Robust SQLite database with Write-Ahead Logging (WAL) storing download metadata, byte ranges, and statuses. |
| **Pause / Resume All** | Global toolbar actions | **Core PDM** | Signal-based broadcast to worker threads to flush current buffer, pause, or resume queued items. |
| **Scheduler** | Time-based start/stop queues | **Enhanced PDM** | Background Qt `QTimer` checking scheduled start/stop execution times. |
| **Shutdown on Completion** | Optional system shutdown / sleep | **Enhanced PDM** | Windows API call (`InitiateSystemShutdownEx` or `shutdown /s /t 60`) on queue drain with user cancel countdown. |

---

## 3. User Interface & User Experience

| Feature | IDM (Observed) | PDM Plan | Feasibility & Technical Strategy |
|---|---|---|---|
| **Modern Windows UI** | Classic Win32 layout (dated look) | **Core PDM** | Modern PySide6 (Qt 6) application with clean typography, polished dark/light themes, and responsive layout. |
| **Download List Table** | Sortable columns with real-time stats | **Core PDM** | `QTableView` with virtual model (`QAbstractTableModel`) for zero-lag rendering even with hundreds of items. |
| **Visual Segment Progress** | Multi-colored segmented progress bar | **Core PDM** | Custom painted Qt widget showing real-time byte ranges for each active segment. |
| **Add URL Dialog** | Auto-detects clipboard URL | **Core PDM** | Standard dialog pre-filling clipboard if matching `http://` or `https://` schema. |
| **Categories Tree** | Auto-sorts by file extension | **Core PDM** | Default categories (Compressed, Documents, Music, Programs, Video, Other) with customizable extension mappings and folders. |
| **Search & Filter** | Keyword filter & category view | **Core PDM** | Fast live search filtering download table by filename, domain, or status. |
| **System Tray Integration** | Minimized to tray with notification | **Core PDM** | `QSystemTrayIcon` with context menu (Pause All, Resume All, Add URL, Exit) and desktop notifications on completion. |

---

## 4. Integration & Security

| Feature | IDM (Observed) | PDM Plan | Feasibility & Technical Strategy |
|---|---|---|---|
| **Browser Extension Handoff**| Browser extension + proprietary hook | **Enhanced PDM** | Standard **WebExtensions Native Messaging** host. Chrome, Edge, and Firefox support clean JSON message handoffs over stdin/stdout. Zero unauthorized hooks. |
| **Clipboard Monitoring** | Automatic clipboard sniffing | **Core PDM** | Opt-in toggle: listens to `QClipboard::dataChanged` and prompts user with Add URL dialog if valid URL is copied. |
| **Integrity Check (SHA-256)**| None / minimal | **Core PDM** | Built-in SHA-256 and MD5 hash validator dialog to verify downloaded file against author-provided checksums. |
| **Safe File Naming & Path** | Handles collisions via `(1)` | **Core PDM** | Strict filename sanitization: blocks path traversal (`../`, `..\`), strips illegal Windows characters (`<>:"/\|?*`), handles collisions. |
| **No Auto-Execution** | Options to run antivirus | **Core PDM** | PDM will **never** automatically execute or launch downloaded files without explicit user action (*Open File* button). |

---

## 5. Scope Boundaries (Personal Use Principle)

- **Excluded Bloat:**
  - No user accounts, registration, licenses, or paywalls.
  - No telemetry, analytics, or background telemetry services.
  - No continuous background auto-updater polling remote servers.
  - No invasive network drivers (LSP, TDI, WFP filter drivers).
- **Emphasized Strengths:**
  - Lightweight, clean, portable standalone binary.
  - High download throughput via multi-connection range downloads.
  - Rock-solid resume capability and corrupted chunk recovery.
  - Zero privacy leakage: all data remains strictly local in `downloads.db`.
