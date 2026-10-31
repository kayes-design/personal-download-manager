# Changelog

All notable changes to the Personal Download Manager (PDM) project will be documented in this file.

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
