# Personal Download Manager (PDM)

An independent, high-performance, modern Windows desktop download manager inspired by Internet Download Manager (IDM) and built using clean-room software engineering.

---

## Key Highlights

- **Multi-Connection Dynamic Segmentation:** Divides downloads across parallel connection threads (RFC 7233 HTTP Range requests) and dynamically balances work across active workers.
- **Fail-Safe Resumption:** Checkpoints segment state to local SQLite database in WAL mode; seamlessly resumes paused or dropped downloads after validating `ETag` and `Last-Modified`.
- **Single-Connection Fallback:** Automatically falls back to single-stream linear downloading when a server does not support partial content.
- **Modern Windows 11 Desktop UI (PySide6 / Qt 6):**
  - Dark and Light Fluent theme options.
  - Real-time **Segment Visualizer Strip** widget displaying active network chunks.
  - Add URL dialog with automatic Windows Clipboard link detection.
  - High-performance virtual download table (`QTableView` + `QAbstractTableModel`).
  - Category sidebar (All, Compressed, Documents, Music, Programs, Video, Other).
  - Search filter bar, speed display, and system tray integration with completion notifications.
- **Queue & Bandwidth Limiting:**
  - Enforces concurrent download limits (e.g. 3 active files at once, remainder queued).
  - Built-in token-bucket rate limiter for global and per-download throttling.
- **Cryptographic File Integrity:**
  - Built-in Checksum Verifier (SHA-256 / MD5) to verify downloaded files against publisher hashes.
- **Browser Handoff Integration:**
  - Chrome, Edge, and Firefox WebExtensions Native Messaging host for user-approved one-click link handoff (zero unauthorized DLL injection).
- **Personal Use Guarantees:**
  - Zero accounts, subscriptions, licenses, paywalls, or telemetry.
  - 100% offline-first, strictly storing data locally in `downloads.db`.

---

## Running the Application

### From Source
```powershell
cd C:\Users\MrKayes\.gemini\antigravity\scratch\personal-download-manager
python pdm/main.py
```

### Command-Line Arguments
```powershell
# Download URL directly to Downloads folder
python pdm/main.py -d "https://example.com/largefile.zip"

# Download with custom folder and filename
python pdm/main.py -d "https://example.com/archive.tar.gz" -p "D:\Files" -f "backup.tar.gz"

# Start minimized to system tray
python pdm/main.py --tray

# Portable mode (stores database in current directory)
python pdm/main.py --portable
```

### Running the Automated Tests
```powershell
cd C:\Users\MrKayes\.gemini\antigravity\scratch\personal-download-manager
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest tests/ -v
```
