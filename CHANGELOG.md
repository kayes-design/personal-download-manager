# Changelog

All notable changes to the Personal Download Manager (PDM) project will be documented in this file.

## [Startup & Memory Optimization] - 2026-11-09
### Changed
- Load yt-dlp and imageio-ffmpeg only when media extraction or FFmpeg functionality is needed.
- Skip yt-dlp extractor initialization for common direct-download file types.
- Keep FFmpeg bundled so media downloads and merges remain available offline.
### Verified
- Tray-mode memory benchmark decreased from 135.7 MB to 126.1 MB working set and from 73.7 MB to 62.1 MB private memory.

## [Download Dialog & Sidebar Refresh] - 2026-11-08
### Added
- Added a Pictures category with image-type detection and a matching sidebar icon.
- Added sidebar filters for Downloading, Completed, Paused, In Queue, Failed, and Cancelled while keeping Unfinished and Finished shortcuts.
- Restyled the Download File Info dialog to show URL, Name, Size, Cat, and editable Save To fields with a folder picker and IDM-style action buttons.
- Kept connection count and remembered-folder controls under More options; show known size when available and Unknown otherwise.

## [Reliability & Stress Audit] - 2026-11-02
### Fixed
- Forwarded browser-login cookies with their original domain/path scope to media extraction, and use the originating supported video page when resolving a detected stream.
- Enabled the top-level PDM video controls on Facebook pages without injecting into Facebook's nested frames.
- Keep incomplete HTTP and media downloads in a hidden same-volume staging folder and atomically publish their final paths only after successful assembly/download.
- Prevented the browser progress card from jumping during its entrance animation and made drag positioning override the card's centered coordinates.
- Made single-resolution floater downloads and "Download Selected" start immediately, opening the active download HUD without an extra confirmation card.
- Fixed the browser download HUD polling contract so progress and completion statuses reach the card; terminal errors and cancellations no longer leave a stale downloading card.
- Recentered the active download card when it replaces the confirmation card so it does not inherit a dragged or stale position.
- Prevented speed-limit deadlocks when a network chunk exceeds the token-bucket capacity.
- Validate each HTTP byte-range response and safely retry with one connection when the server ignores or changes ranges.
- Restored TLS certificate verification for media and playlist extraction.
- Removed synchronous media-title lookups from download creation to keep the UI responsive.
- Restored scheduler settings on startup and dispatch shutdown dialogs through the GUI thread.
- Ensure scheduler shutdown wakes and joins its worker thread; avoid leaking the installed-app smoke-test process.
### Verified
- Added regression coverage for 32-connection downloads, range fallback, limiter pressure, scheduler persistence/triggers, TLS settings, and GUI thread dispatch.

## [IDM Categories Sidebar & Link Interceptor Release] - 2026-10-30
### Added
- **IDM Hierarchical Categories Tree (`pdm/gui/icons.py`, `pdm/gui/main_window.py`):**
  - Designed matching IDM tree structure: `All Downloads` (expanded `[-]`), `Unfinished` (collapsed `[+]`), and `Finished` (collapsed `[+]`).
  - Added dedicated category sub-groups under each root: `Compressed`, `Documents`, `Music`, `Programs`, `Video`.
  - Built custom vector-rendered antialiased icons: Zipper archive, Document sheet, Music eighth-notes, Program window, Film strip, and Down-arrow/Checkmark badged folders.
  - Added "Categories" header with '✕' collapse button and toolbar restore toggle.
  - Implemented dual status & category filtering in `DatabaseManager.list_downloads`.
- **IDM-Style Website Link Interceptor (`extension/content.js`, `extension/manifest.json`):**
  - Added global click interceptor capturing `.zip`, `.exe`, `.msi`, `.iso`, `.rar`, `.7z`, `.mp4`, `.pdf` and `download` attribute clicks.
  - Assigned fixed cryptographic extension key and registered exact origin in `com.pdm.native_host.json`.

## [Floating Video Grabber Release] - 2026-10-30
### Added
- **Floating Video Player Grabber Panel (`extension/content.js`, `extension/floating.css`):**
  - Content script observing HTML5 `<video>` and `<audio>` elements across web pages.
  - Injects a sleek, modern glassmorphic floating button (`[⬇ Download Video]`) positioned seamlessly at the top-right corner of video players.
  - Dynamic dropdown menu listing all detected video/audio streams and sizes.
  - 1-click download dispatch directly to PDM desktop application via Native Messaging host.
- **Background Media Request Sniffer (`extension/background.js`):**
  - Added `chrome.webRequest.onHeadersReceived` listener inspecting `content-type` (`video/*`, `audio/*`, `application/vnd.apple.mpegurl`) and `content-length`.
  - Automatically feeds intercepted streaming video URLs and format qualities to the active player's floating panel.
