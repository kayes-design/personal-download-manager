# Personal Download Manager (PDM)

<div align="center">

![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Platform: Windows 10 / 11](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078d4.svg)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg)
![Qt: PySide6](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-41CD52.svg)
![Extension: Manifest V3](https://img.shields.io/badge/Extension-Manifest%20V3-orange.svg)
![Privacy: 100% Offline](https://img.shields.io/badge/Privacy-100%25%20Offline-success.svg)

**A high-performance, modern, open-source Windows download accelerator and universal media grabber inspired by Internet Download Manager (IDM), built with clean-room software architecture.**

[Key Features](#-key-features) • [In-Page Download HUD](#-in-page-active-download-hud) • [Architecture](#-architecture) • [Installation](#-installation) • [Development](#-development--testing) • [License](#-license)

</div>

---

## ⚡ Overview

**Personal Download Manager (PDM)** is a standalone desktop application and companion browser extension designed to provide maximum download speeds through intelligent multi-segmented network streaming, paired with an elegant, modern in-browser downloading experience.

Unlike legacy download managers that rely on outdated Windows 98-era user interfaces, closed-source binaries, or kernel-level DLL injections, PDM is built strictly using clean-room standards, modern **PySide6 / Qt 6**, SQLite WAL persistence, and standard **Chromium Manifest V3 Native Messaging**.

---

## ✨ Key Features

### 🚀 High-Speed Acceleration & Segmentation Engine
* **Dynamic Connection Slicing:** Automatically splits files into parallel network streams (configurable up to 32 connections) utilizing RFC 7233 HTTP Range requests.
* **Fail-Safe Crash Resumption:** State is checkpointed to an ACID-compliant local SQLite database in WAL mode every 250ms. Interrupted or dropped downloads resume seamlessly by validating `ETag` and `Last-Modified` headers.
* **Safe File Publishing:** Incomplete downloads stay in a hidden same-volume staging folder; the final filename appears in the destination folder only after the download or media merge succeeds.
* **Single-Connection Fallback:** Automatically detects servers that do not support partial content ranges and smoothly falls back to reliable single-stream linear downloading.
* **Token-Bucket Bandwidth Limiter:** Global and per-task throttling controls to keep network bandwidth available for work or streaming.
* **Cryptographic Checksum Verifier:** Integrated SHA-256 and MD5 integrity verification directly from the GUI.

### 🌐 Universal 150+ File Type Interception
* **Exhaustive File Coverage:** Automatically intercepts downloads across all file categories:
  * **Archives:** `.zip`, `.rar`, `.7z`, `.tar`, `.gz`, `.bz2`, `.xz`, `.iso`, `.img`, `.bin`, `.cab`, `.wim`, `.dmg`
  * **Executables:** `.exe`, `.msi`, `.apk`, `.xapk`, `.deb`, `.rpm`, `.appimage`, `.bat`, `.ps1`
  * **Documents:** `.pdf`, `.docx`, `.xlsx`, `.pptx`, `.csv`, `.tsv`, `.txt`, `.rtf`, `.epub`, `.odt`
  * **Media:** `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`, `.mp3`, `.wav`, `.flac`, `.aac`, `.m4a`, `.opus`
  * **Creative & Graphics:** `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg`, `.psd`, `.ai`, `.raw`, `.heic`
  * **Developer & Data:** `.sql`, `.db`, `.sqlite`, `.json`, `.xml`, `.torrent`, `.whl`
* **Binary MIME Detection:** Intercepts dynamic server attachments (`application/octet-stream`, `application/zip`, etc.) even when URLs contain complex query strings.

### 🎬 Universal Media Sniffer & Video Grabber
* **Floating Video Action Button:** Compact, unobtrusive SVG icon button hovering over HTML5 video players on popular media portals and streaming sites.
* **Multi-Stream Resolution Selector:** Discovers all available video streams, audio tracks, and subtitles (HLS `.m3u8`, DASH `.mpd`, MP4, WebM, 1080p, 720p, 4K).
* **Social Media Title Sanitizer:** Automatically cleans noisy view counts, reactions, and timestamps from video titles on Facebook, YouTube, Instagram Reels, and TikTok to generate clean filenames.
* **Browser Session Support:** For sites where you are already signed in, the extension can pass the originating page and correctly scoped browser cookies to the media extractor. Downloads still depend on the site's available formats and access rules; DRM-protected media is not supported.
* **HTMLMediaElement Prototype Hook:** Intercepts dynamically created video players in complex Single Page Applications (SPAs) the moment `.play()` or `.load()` is invoked.
* **Video Playing Smart Dimming:** Fades button opacity to `0.28` during playback to eliminate viewing distraction, instantly restoring full opacity upon pause or hover.
* **Fullscreen Auto-Hide:** Automatically hides all overlays and HUD widgets during fullscreen HTML5 video playback.
* **Download Categories & Status Filters:** Organizes Pictures, Video, Music, Programs, and Compressed files, with direct filters for downloading, completed, paused, queued, failed, and cancelled tasks.
* **IDM-Style Download File Info:** Shows URL, name, size, category, editable save location, and Download Later / Start Download / Cancel actions in a compact dialog.

---

## 🎛️ In-Page Active Download HUD

PDM replaces annoying, transient notification toasts with a full-featured **Interactive In-Page Download Card (Floating HUD)** embedded directly in the web page:

```
┌─────────────────────────────────────────────────────────────┐
│ ⚡ Stage 1: Pre-Download Confirmation Card                  │
│ • File title, resolution badge, and size preview            │
│ • [ ⚡ Download Now ]          [ 🕒 Download Later (Queue) ]│
└──────────────────────────────┬──────────────────────────────┘
                               │ User selects "Download Now"
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 📊 Stage 2: Live Download Progress HUD                      │
│ • Animated progress bar (0% to 100%)                        │
│ • Live speed (e.g. 14.5 MB/s), Downloaded size, and ETA     │
│ • [ ⏸️ Pause / ▶️ Resume ]   [ ✕ Cancel ]    [ 🗕 Minimize ]│
└──────────────────────────────┬──────────────────────────────┘
                               │ On Download Complete
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ ✓ Stage 3: Instant Action Completed Card                    │
│ • "Download Complete" confirmation                          │
│ • [ 📂 Open File ]            [ 📁 Open Folder ]            │
└─────────────────────────────────────────────────────────────┘
```

* **Minimize to Floating Badge (🗕):** Collapse the active card into a sleek floating corner badge showing `%` and live speed (`⚡ 85% 12MB/s`). Click to expand back anytime.
* **Two-Way Real-Time Synchronization:** Seamlessly synchronized between the in-page browser card and the PDM desktop GUI via a local Native Messaging bridge and SQLite database. Controlling pauses or resumes on either side updates both in real time.

---

## 🏛️ Architecture

```mermaid
flowchart TD
    subgraph Browser ["Web Browser (Chrome / Edge / Brave / Opera / Firefox)"]
        CS["Content Script\n(Video Grabber & In-Page HUD)"]
        BG["Background Service Worker\n(Network Sniffer & Interceptor)"]
        CS <-->|Runtime Messaging| BG
    end

    subgraph Bridge ["Native Messaging Bridge"]
        NH["Native Messaging Host\n(pdm_host.exe / native_host.py)"]
        BG <-->|Standard I/O (JSON)| NH
    end

    subgraph Engine ["PDM Core Desktop Engine"]
        DB[("SQLite WAL Database\n(downloads.db)")]
        GUI["Desktop GUI Window\n(PySide6 / Qt 6)"]
        WORKER["Multi-Threaded Segmentation Engine\n(Dynamic Range Workers)"]
        
        NH <-->|Direct Query & Updates| DB
        NH -->|Local IPC Signal| GUI
        WORKER <-->|Read / Write State| DB
        GUI <-->|Model View| DB
    end
```

---

## 📦 Installation

### Option 1: Standalone All-in-One Installer (Recommended)
1. Download **`PDM_Setup.exe`** from the [Releases](https://github.com/your-username/personal-download-manager/releases) page.
2. Run the installer wizard. It will:
   * Install the PDM desktop application and dependencies.
   * Automatically register the Native Messaging host in the Windows Registry for Chrome, Edge, Brave, and Opera.
   * Automatically pop up the browser Extensions page (`chrome://extensions` or `edge://extensions`) and open the `extension/` folder side-by-side.
3. Turn on **Developer mode** in your browser and drag the `extension` folder into the browser window (or click **Load unpacked**).

### Option 2: Run from Source
```powershell
# Clone repository
git clone https://github.com/your-username/personal-download-manager.git
cd personal-download-manager

# Install Python dependencies
pip install -r requirements.txt

# Run Desktop Application
python pdm/main.py

# Run in System Tray mode
python pdm/main.py --tray
```

---

## 🧪 Development & Testing

PDM includes an automated test suite verifying file type classification, engine segmentation, native bridge operations, and JavaScript syntax:

```powershell
# Run backend engine and unit tests
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest tests/ -v

# Run browser extension syntax checks
node --check extension/background.js
node --check extension/content.js

# Build standalone distribution and installer
python build_payload.py
pyinstaller --noconfirm installer.spec
```

---

## 🔒 Security & Privacy Guarantees

* **100% Offline-First:** PDM runs completely locally. It requires zero cloud accounts, sends zero analytics, and contains zero trackers.
* **No Unauthorized DLL Injection:** Many commercial download managers inject invasive DLL hooks into every running Windows process. PDM relies exclusively on official, sanctioned browser WebExtensions and W3C standard APIs.
* **Zero Paywalls:** All power features (32 parallel connections, queueing, scheduler, media sniffer) are fully unrestricted.

---

## 📄 License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)** - see the [LICENSE](LICENSE) file for complete details. Anyone is free to use, modify, and build upon this software, provided all derivative works remain open source under the same license.
