// Personal Download Manager (PDM) Extension Content Script
// Dynamic Video Player Grabber, Multi-Stream Sniffer & Universal Link Interceptor

(function () {
  const host = (window.location.hostname || "").toLowerCase();
  if (host.includes("facebook.com") || host.includes("fb.com") || host.includes("fb.watch")) {
    return; // Completely disable video grabber floater on Facebook
  }

  if (window.__pdm_grabber_initialized) return;
  window.__pdm_grabber_initialized = true;

  const capturedStreams = [];
  const selectedStreamUrls = new Set();
  let globalOverlay = null;
  let currentMediaEl = null;
  let isDismissedForPage = false;
  let customOffsetX = null;
  let customOffsetY = null;
  let lastObservedUrl = window.location.href;

  // VnA-Inspired HTMLMediaElement Hook for Dynamic Player & SPA Sniffing
  try {
    const hookScript = document.createElement("script");
    hookScript.textContent = `
      (function() {
        const origPlay = HTMLMediaElement.prototype.play;
        HTMLMediaElement.prototype.play = function() {
          window.postMessage({ type: 'PDM_MEDIA_PLAY' }, '*');
          return origPlay.apply(this, arguments);
        };
        const origLoad = HTMLMediaElement.prototype.load;
        HTMLMediaElement.prototype.load = function() {
          window.postMessage({ type: 'PDM_MEDIA_LOAD' }, '*');
          return origLoad.apply(this, arguments);
        };
      })();
    `;
    (document.head || document.documentElement).appendChild(hookScript);
    hookScript.remove();
  } catch (e) {}

  window.addEventListener("message", (e) => {
    if (e.data && (e.data.type === "PDM_MEDIA_PLAY" || e.data.type === "PDM_MEDIA_LOAD")) {
      requestAnimationFrame(() => scanMediaElements());
    }
  });

  // Video Playing Dimming (Dim floater when playing, restore on pause or hover)
  document.addEventListener("playing", (e) => {
    if (e.target && e.target.tagName === "VIDEO") {
      document.querySelectorAll(".pdm-video-overlay").forEach(p => p.classList.add("pdm-playing-dim"));
    }
  }, true);

  document.addEventListener("pause", (e) => {
    if (e.target && e.target.tagName === "VIDEO") {
      document.querySelectorAll(".pdm-video-overlay").forEach(p => p.classList.remove("pdm-playing-dim"));
    }
  }, true);



  // 1. Identify high-level portals where page URLs are supported for audio+video muxing
  function isPopularMediaPortal(url) {
    if (!url) return false;
    const lower = url.toLowerCase();
    return (
      lower.includes("facebook.com") ||
      lower.includes("fb.watch") ||
      lower.includes("fb.com") ||
      lower.includes("youtube.com") ||
      lower.includes("youtu.be") ||
      lower.includes("instagram.com") ||
      lower.includes("tiktok.com") ||
      lower.includes("twitter.com") ||
      lower.includes("x.com") ||
      lower.includes("reddit.com") ||
      lower.includes("redd.it") ||
      lower.includes("vimeo.com") ||
      lower.includes("twitch.tv") ||
      lower.includes("dailymotion.com") ||
      lower.includes("bilibili.com") ||
      lower.includes("rumble.com")
    );
  }

  function getPortalVideoUrl(videoEl) {
    const currentUrl = window.location.href;
    const lower = currentUrl.toLowerCase();

    // 1. YouTube & Shorts
    if (lower.includes("youtube.com") || lower.includes("youtu.be")) {
      if (lower.includes("/watch?") || lower.includes("/shorts/")) {
        return currentUrl;
      }
      if (videoEl) {
        const item = videoEl.closest("ytd-rich-item-renderer, ytd-video-renderer, ytd-compact-video-renderer, ytd-grid-video-renderer, ytd-reel-video-renderer, ytd-notification-renderer, #movie_player");
        if (item) {
          const a = item.querySelector('a[href*="/watch?v="], a[href*="/shorts/"]');
          if (a && a.href) return a.href;
        }
      }
      return null;
    }

    // 2. Facebook Reels, Videos, Watch, Posts
    if (lower.includes("facebook.com") || lower.includes("fb.watch") || lower.includes("fb.com")) {
      if (lower.includes("/reel/") || lower.includes("/videos/") || lower.includes("/watch/")) {
        return currentUrl;
      }
      if (videoEl) {
        let p = videoEl.parentElement;
        let depth = 0;
        while (p && depth < 25) {
          const links = p.querySelectorAll('a[href*="/videos/"], a[href*="/reel/"], a[href*="/watch/"], a[href*="story.php"], a[href*="permalink.php"], a[href*="/posts/"]');
          for (const a of links) {
            if (a.href && !a.href.includes("comment") && !a.href.includes("reaction") && !a.href.includes("#")) {
              return a.href;
            }
          }
          p = p.parentElement;
          depth++;
        }
      }
      if (!currentUrl.endsWith("facebook.com/") && !currentUrl.endsWith("facebook.com")) {
        return currentUrl;
      }
      return null;
    }

    // 3. Instagram Reels, Posts, Stories
    if (lower.includes("instagram.com")) {
      if (videoEl) {
        const article = videoEl.closest("article, main");
        if (article) {
          const link = article.querySelector('a[href*="/p/"], a[href*="/reel/"]');
          if (link && link.href) return link.href;
        }
      }
      if (currentUrl === "https://www.instagram.com/" || currentUrl === "https://www.instagram.com") {
        return null;
      }
      return currentUrl;
    }

    // 4. TikTok, Twitter/X, Reddit, etc.
    if (lower.includes("tiktok.com") || lower.includes("x.com") || lower.includes("twitter.com") || lower.includes("reddit.com")) {
      return currentUrl;
    }

    return currentUrl;
  }

  // 2. SPA Navigation Reset (YouTube, Twitter, Reddit, etc.)
  function checkUrlChange() {
    if (window.location.href !== lastObservedUrl) {
      lastObservedUrl = window.location.href;
      isDismissedForPage = false;
      customOffsetX = null;
      customOffsetY = null;
      capturedStreams.length = 0;
      selectedStreamUrls.clear();
      if (globalOverlay) {
        globalOverlay.style.display = "none";
        const menu = globalOverlay.querySelector(".pdm-stream-menu");
        if (menu) menu.classList.remove("pdm-show");
      }
    }
  }

  function handleNavigation() {
    checkUrlChange();
    setTimeout(() => {
      scanMediaElements();
      updateBatchPill();
    }, 500);
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "PDM_MEDIA_DETECTED") {
      addStream(message.data);
    } else if (message.type === "PDM_PAGE_NAVIGATED") {
      handleNavigation();
    } else if (message.action === "OPEN_BATCH_MODAL") {
      openBatchModal(message.onlySelection);
    } else if (message.action === "SHOW_CONFIRM_CARD" && message.url) {
      let fn = (message.filename || "").trim();
      if (!fn) {
        try {
          const u = new URL(message.url);
          fn = decodeURIComponent(u.pathname.split("/").pop() || "");
        } catch (e) {
          fn = message.url.split("/").pop() || "";
        }
        fn = fn.split("?")[0].split("#")[0].trim();
      }
      if (!fn || fn.length === 0) {
        fn = (message.selectionText && message.selectionText.trim().substring(0, 50)) || getCleanTitle(currentMediaEl || document.querySelector("video")) || "Download_File";
      }
      const ext = getUrlExtension(message.url) || getUrlExtension(fn);
      if (ext && !fn.toLowerCase().endsWith(`.${ext}`)) {
        fn = `${fn}.${ext}`;
      } else if (!fn.includes(".")) {
        if (currentMediaEl || isPopularMediaPortal(window.location.href) || /video|stream|audio|\.m3u8|\.mpd/i.test(message.url)) {
          fn = `${fn}.mp4`;
        }
      }
      showPreDownloadCard({
        url: message.url,
        filename: fn,
        resolution: ext ? ext.toUpperCase() : "File",
        size: message.fileSize || 0,
        referer: window.location.href,
        origin: window.location.origin,
        user_agent: navigator.userAgent
      });
      sendResponse({ handled: true });
      return true;
    }
  });

  window.addEventListener("popstate", handleNavigation);
  window.addEventListener("yt-navigate-finish", handleNavigation);

  try {
    const originalPushState = history.pushState;
    history.pushState = function () {
      originalPushState.apply(this, arguments);
      setTimeout(handleNavigation, 250);
    };
    const originalReplaceState = history.replaceState;
    history.replaceState = function () {
      originalReplaceState.apply(this, arguments);
      setTimeout(handleNavigation, 250);
    };
  } catch (e) {}

  // 3. Resolution & Metadata Detectors
  function detectResolution(videoEl, url) {
    if (videoEl && videoEl.videoWidth && videoEl.videoHeight) {
      const w = videoEl.videoWidth;
      const h = videoEl.videoHeight;
      if (h >= 2160 || w >= 3840) return { tag: "4K", full: `4K Ultra HD (${w}x${h})` };
      if (h >= 1440 || w >= 2560) return { tag: "2K", full: `1440p 2K (${w}x${h})` };
      if (h >= 1080 || w >= 1920) return { tag: "1080p", full: `1080p Full HD (${w}x${h})` };
      if (h >= 720 || w >= 1280) return { tag: "720p", full: `720p HD (${w}x${h})` };
      if (h >= 480) return { tag: "480p", full: `480p SD (${w}x${h})` };
      if (h >= 360) return { tag: "360p", full: `360p (${w}x${h})` };
      if (h > 0) return { tag: `${h}p`, full: `${h}p (${w}x${h})` };
    }

    if (url) {
      const lower = url.toLowerCase();
      if (lower.includes("2160") || lower.includes("4k") || lower.includes("itag=313") || lower.includes("itag=401")) {
        return { tag: "4K", full: "4K Ultra HD (2160p)" };
      }
      if (lower.includes("1440") || lower.includes("2k") || lower.includes("itag=271") || lower.includes("itag=308")) {
        return { tag: "2K", full: "1440p 2K" };
      }
      if (lower.includes("1080") || lower.includes("dash_1080") || lower.includes("itag=137") || lower.includes("itag=299") || lower.includes("itag=303")) {
        return { tag: "1080p", full: "1080p Full HD" };
      }
      if (lower.includes("720") || lower.includes("dash_720") || lower.includes("itag=136") || lower.includes("itag=298") || lower.includes("itag=22")) {
        return { tag: "720p", full: "720p HD" };
      }
      if (lower.includes("480") || lower.includes("dash_480") || lower.includes("itag=135") || lower.includes("itag=244")) {
        return { tag: "480p", full: "480p SD" };
      }
      if (lower.includes("360") || lower.includes("dash_360") || lower.includes("itag=134") || lower.includes("itag=18")) {
        return { tag: "360p", full: "360p" };
      }
      if (lower.includes("240") || lower.includes("dash_240")) {
        return { tag: "240p", full: "240p" };
      }
      if (lower.includes("audio") || lower.includes("dash_audio") || lower.includes("itag=140") || lower.includes("itag=251")) {
        return { tag: "AUDIO", full: "Audio Track" };
      }
    }

    return null;
  }

  function estimateBytesFromDuration(durationSec, resTag) {
    if (!durationSec || !isFinite(durationSec) || durationSec <= 0) return null;
    let bytesPerSec = 450000; // ~3.6 Mbps default
    const tag = (resTag || "").toUpperCase();
    if (tag.includes("4K") || tag.includes("2160")) bytesPerSec = 2250000; // ~18 Mbps
    else if (tag.includes("2K") || tag.includes("1440")) bytesPerSec = 1000000; // ~8 Mbps
    else if (tag.includes("1080")) bytesPerSec = 562500; // ~4.5 Mbps
    else if (tag.includes("720")) bytesPerSec = 275000; // ~2.2 Mbps
    else if (tag.includes("480")) bytesPerSec = 125000; // ~1.0 Mbps
    else if (tag.includes("360")) bytesPerSec = 75000; // ~600 kbps
    else if (tag.includes("AUDIO")) bytesPerSec = 20000; // ~160 kbps

    return Math.round(durationSec * bytesPerSec);
  }

  function probeDirectStreamSize(stream) {
    if (stream.size && stream.size > 0) return;
    if (!stream.url || stream.url.startsWith("blob:") || stream.url === window.location.href) return;
    try {
      fetch(stream.url, { method: "HEAD" })
        .then((res) => {
          const cl = res.headers.get("content-length");
          if (cl) {
            const sz = parseInt(cl, 10);
            if (sz > 0) {
              stream.size = sz;
              updateAllOverlays();
            }
          }
        })
        .catch(() => {});
    } catch (e) {}
  }

  // 4. Register Detected Media Stream with Smart Priority & Anti-Clutter Deduplication
  function addStream(stream, videoEl = null, prepend = false) {
    if (!stream || !stream.url) return;

    const onPortal = isPopularMediaPortal(window.location.href);
    if (onPortal && !stream.isMasterStream) {
      const lower = stream.url.toLowerCase();
      // Drop raw fragments from video portals (they have no audio or are corrupted slice pieces)
      if (
        lower.includes("fbcdn.net") ||
        lower.includes("googlevideo.com") ||
        lower.includes("byteoversea.com") ||
        lower.includes("tiktokcdn.com")
      ) {
        return;
      }
    }

    // Drop numbered chunks, transport slices and byte-range slices
    const lowerUrl = stream.url.toLowerCase();
    if (
      lowerUrl.includes("bytestart=") ||
      lowerUrl.includes("byteend=") ||
      lowerUrl.includes("&range=") ||
      lowerUrl.includes("?range=") ||
      lowerUrl.includes("&sq=") ||
      lowerUrl.includes("initsegment") ||
      lowerUrl.includes(".m4s")
    ) {
      return;
    }

    if (!stream.referer) stream.referer = window.location.href;
    if (!stream.origin) {
      try {
        stream.origin = window.location.origin;
      } catch (e) {
        stream.origin = "";
      }
    }
    if (!stream.userAgent) stream.userAgent = navigator.userAgent;

    const res = detectResolution(videoEl, stream.url);
    if (res && !stream.resTag) {
      stream.resTag = res.tag;
      stream.resolution = res.full;
    }

    if (videoEl && videoEl.duration && isFinite(videoEl.duration)) {
      stream.duration = videoEl.duration;
    }

    const existing = capturedStreams.find((s) => s.url === stream.url);
    if (existing) {
      if (res && !existing.resTag) {
        existing.resTag = res.tag;
        existing.resolution = res.full;
        updateAllOverlays();
      }
      if (stream.size && !existing.size) {
        existing.size = stream.size;
        updateAllOverlays();
      }
      return;
    }

    // Deduplicate by resolution tag to prevent showing multiple redundant streams for the same quality
    if (stream.resTag && !stream.isMasterStream) {
      const sameRes = capturedStreams.find((s) => s.resTag === stream.resTag && !s.isMasterStream);
      if (sameRes) {
        if (stream.size && stream.size > (sameRes.size || 0)) {
          sameRes.url = stream.url;
          sameRes.size = stream.size;
          updateAllOverlays();
        }
        return;
      }
    }

    const isDirectMedia = stream.url.includes(".m3u8") ||
                          stream.url.includes(".mpd") ||
                          stream.url.includes(".mp4") ||
                          stream.url.includes(".webm") ||
                          stream.url.includes(".mkv") ||
                          (stream.type && stream.type.startsWith("video/"));

    if (stream.isMasterStream) {
      capturedStreams.unshift(stream);
      selectedStreamUrls.clear();
      selectedStreamUrls.add(stream.url);
    } else if (prepend || isDirectMedia) {
      capturedStreams.push(stream);
      if (selectedStreamUrls.size === 0) {
        selectedStreamUrls.add(stream.url);
      }
    } else {
      capturedStreams.push(stream);
      if (selectedStreamUrls.size === 0) {
        selectedStreamUrls.add(stream.url);
      }
    }

    probeDirectStreamSize(stream);
    updateAllOverlays();
  }

  // 5. Detect and populate standard resolution streams on video portals (YouTube, Reddit, etc.)
  
  // Core Text & Data Formatting Helpers
  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    let b = Number(bytes);
    while (b >= 1024 && i < units.length - 1) {
      b /= 1024;
      i++;
    }
    return `${b.toFixed(1)} ${units[i]}`;
  }

  function getCleanTitle(videoEl = null) {
    let title = "";
    if (videoEl) {
      const container = videoEl.closest && videoEl.closest('[role="article"], [data-pagelet], article, .post');
      if (container) {
        const textEl = container.querySelector('[data-ad-preview="message"], [data-testid="post_message"], h1, h2, h3, p');
        if (textEl && textEl.innerText && textEl.innerText.trim().length > 3) {
          title = textEl.innerText.trim().split("\n")[0];
        }
      }
    }
    if (!title) {
      title = (document.title || "").trim();
    }
    // VnA-Style social media statistics cleaner (strip views, reactions, comments, likes, watching, subscribers)
    title = title.replace(/[\d.]+[KMB]?\s*(views|reactions|comments|shares|likes|watching|subscribers)/gi, "");
    title = title.replace(/[•|·]/g, " ").replace(/\s+/g, " ").trim();

    const lower = title.toLowerCase();
    const genericWords = ["facebook", "youtube", "instagram", "video", "reel", "watch", "tiktok", "twitter"];
    if (!title || genericWords.some((w) => lower === w || lower.startsWith(`${w} -`) || lower.startsWith(`${w} :`))) {
      const now = new Date();
      const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}_${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}`;
      const prefix = document.title ? document.title.split("-")[0].trim() : "Video";
      title = `${prefix}_${dateStr}`;
    }
    return title.replace(/[<>:"/\\|?*\n\r\t]/g, "_").trim().substring(0, 100) || "Video";
  }


  function ensurePortalResolutionStreams() {
    if (!isPopularMediaPortal(window.location.href)) return;

    const portalMediaUrl = getPortalVideoUrl(currentMediaEl);
    if (!portalMediaUrl) return;

    if (capturedStreams.some((s) => s.isPortalResolution && s.baseUrl === portalMediaUrl)) {
      return;
    }

    // Clear older portal resolution entries
    for (let i = capturedStreams.length - 1; i >= 0; i--) {
      if (capturedStreams[i].isPortalResolution || capturedStreams[i].isMasterStream) {
        capturedStreams.splice(i, 1);
      }
    }

    const baseTitle = getCleanTitle(currentMediaEl);
    const dur = (currentMediaEl && currentMediaEl.duration && isFinite(currentMediaEl.duration) && currentMediaEl.duration > 0)
      ? currentMediaEl.duration
      : 300;

    const qualities = [
      { tag: "1080p", label: `${baseTitle} (1080p Full HD)`, res: "1080p • MP4", estMbps: 4.5 },
      { tag: "720p", label: `${baseTitle} (720p HD)`, res: "720p • MP4", estMbps: 2.2 },
      { tag: "480p", label: `${baseTitle} (480p Standard)`, res: "480p • MP4", estMbps: 1.0 },
      { tag: "360p", label: `${baseTitle} (360p Data Saver)`, res: "360p • MP4", estMbps: 0.6 },
      { tag: "AUDIO", label: `${baseTitle} (Audio Only)`, res: "Audio Track • M4A", estMbps: 0.16, isAudio: true },
      { tag: "SUB", label: `${baseTitle} (Subtitles / Captions)`, res: "Subtitles • SRT", estMbps: 0.001, isSubtitle: true }
    ];

    qualities.forEach((q, idx) => {
      const streamUrl = `${portalMediaUrl}#res=${q.tag.toLowerCase()}`;
      const estSize = Math.round(dur * (q.estMbps * 1000000 / 8));
      capturedStreams.push({
        url: streamUrl,
        baseUrl: portalMediaUrl,
        type: q.isAudio ? "audio/mp4" : "video/mp4",
        label: q.label,
        resTag: q.tag,
        resolution: q.res,
        size: estSize,
        duration: dur,
        referer: window.location.href,
        origin: window.location.origin,
        isPortalResolution: true
      });
      if (idx === 0 && selectedStreamUrls.size === 0) {
        selectedStreamUrls.add(streamUrl);
      }
    });

    updateAllOverlays();
  }

  // 6. Find Primary Media Element on page to anchor the single floater
  function getPrimaryMediaElement() {
    const candidates = [];
    document.querySelectorAll("video, audio").forEach((el) => candidates.push(el));
    document.querySelectorAll("shreddit-player-2, shreddit-async-loader").forEach((el) => {
      if (el.shadowRoot) {
        el.shadowRoot.querySelectorAll("video").forEach((vel) => candidates.push(vel));
      }
    });

    if (candidates.length === 0) return null;

    // A. Priority 1: Actively playing video
    for (const v of candidates) {
      if (!v.paused && !v.ended && v.readyState > 2) {
        const rect = v.getBoundingClientRect();
        if (rect.width >= 50 && rect.height >= 50 && rect.bottom > 15 && rect.top < window.innerHeight - 15) {
          return { el: v, rect };
        }
      }
    }

    // B. Priority 2: Largest visible video in viewport
    let best = null;
    let maxArea = 0;
    for (const v of candidates) {
      const rect = v.getBoundingClientRect();
      if (rect.width >= 120 && rect.height >= 70 && rect.bottom > 15 && rect.top < window.innerHeight - 15) {
        const area = rect.width * rect.height;
        if (area > maxArea) {
          maxArea = area;
          best = { el: v, rect };
        }
      }
    }
    if (best) return best;

    // C. Priority 3: Any candidate in viewport
    for (const v of candidates) {
      const rect = v.getBoundingClientRect();
      if (rect.width >= 40 && rect.height >= 40 && rect.bottom > 10 && rect.top < window.innerHeight - 10) {
        return { el: v, rect };
      }
    }

    return null;
  }

  // 7. Ensure Exactly ONE Global Floater Instance in DOM
  function ensureGlobalOverlay() {
    if (globalOverlay && document.contains(globalOverlay)) {
      return globalOverlay;
    }

    if (globalOverlay && !document.contains(globalOverlay)) {
      document.body.appendChild(globalOverlay);
      return globalOverlay;
    }

    const overlay = document.createElement("div");
    overlay.className = "pdm-video-overlay";
    overlay.style.display = "none";
    overlay.innerHTML = `
      <div class="pdm-floater-container">
        <div class="pdm-floater-bar">
          <div class="pdm-grab-drag" title="Drag to move floater">⋮⋮</div>
          <button class="pdm-grab-button" type="button" title="Click to choose quality & download">
            <svg class="pdm-grab-icon" viewBox="0 0 24 24">
              <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
            </svg>
            <span class="pdm-stream-badge" style="display:none;" title="Detected streams">0</span>
          </button>
          <button class="pdm-grab-close" type="button" title="Hide floater">&times;</button>
        </div>
        <div class="pdm-stream-menu">
          <div class="pdm-menu-header">
            <span class="pdm-header-title">Detected Resolutions</span>
            <span class="pdm-select-all">Select All</span>
          </div>
          <div class="pdm-stream-list"></div>
          <div class="pdm-action-row">
            <button class="pdm-action-btn pdm-action-download" title="Download selected immediately">
              Download Selected
            </button>
            <button class="pdm-action-btn pdm-action-queue" title="Add to queue for later">
              Add to Queue
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);
    globalOverlay = overlay;

    const floaterBar = overlay.querySelector(".pdm-floater-bar");
    const dragHandle = overlay.querySelector(".pdm-grab-drag");
    const grabBtn = overlay.querySelector(".pdm-grab-button");
    const grabBadge = overlay.querySelector(".pdm-stream-badge");
    const grabClose = overlay.querySelector(".pdm-grab-close");
    const menu = overlay.querySelector(".pdm-stream-menu");
    const selectAllBtn = overlay.querySelector(".pdm-select-all");
    const dlNowBtn = overlay.querySelector(".pdm-action-download");
    const queueBtn = overlay.querySelector(".pdm-action-queue");

    let isDragging = false;
    let hasMoved = false;
    let startX = 0, startY = 0;
    let startLeft = 0, startTop = 0;

    // Drag to reposition floater smoothly
    function initDrag(e) {
      if (e.button !== 0) return;
      isDragging = true;
      hasMoved = false;
      startX = e.clientX;
      startY = e.clientY;

      const oRect = overlay.getBoundingClientRect();
      startLeft = oRect.left;
      startTop = oRect.top;

      document.body.style.userSelect = "none";

      function onMouseMove(moveEvent) {
        if (!isDragging) return;
        const dx = moveEvent.clientX - startX;
        const dy = moveEvent.clientY - startY;

        if (Math.hypot(dx, dy) > 5) {
          hasMoved = true;
          overlay.classList.add("pdm-dragging");
        }

        if (hasMoved) {
          const newLeft = startLeft + dx;
          const newTop = startTop + dy;
          overlay.style.left = `${newLeft}px`;
          overlay.style.top = `${newTop}px`;

          const primary = getPrimaryMediaElement();
          if (primary && primary.rect) {
            customOffsetX = newLeft - primary.rect.left;
            customOffsetY = newTop - primary.rect.top;
          } else {
            customOffsetX = newLeft;
            customOffsetY = newTop;
          }
        }
      }

      function onMouseUp() {
        if (!isDragging) return;
        isDragging = false;
        document.body.style.userSelect = "";
        overlay.classList.remove("pdm-dragging");
        window.removeEventListener("mousemove", onMouseMove, true);
        window.removeEventListener("mouseup", onMouseUp, true);
        if (hasMoved) {
          setTimeout(() => { hasMoved = false; }, 120);
        }
      }

      window.addEventListener("mousemove", onMouseMove, true);
      window.addEventListener("mouseup", onMouseUp, true);
    }

    if (dragHandle) dragHandle.addEventListener("mousedown", initDrag);
    if (floaterBar) {
      floaterBar.addEventListener("mousedown", (e) => {
        if (e.target && e.target.closest && (e.target.closest(".pdm-grab-button") || e.target.closest(".pdm-grab-close"))) return;
        initDrag(e);
      });
    }

    // Dismiss / Close button (✕)
    grabClose.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      isDismissedForPage = true;
      overlay.style.transition = "opacity 0.2s ease, transform 0.2s ease";
      overlay.style.opacity = "0";
      overlay.style.transform = "scale(0.8)";
      setTimeout(() => {
        overlay.style.display = "none";
        overlay.style.opacity = "1";
        overlay.style.transform = "none";
      }, 200);
    });

    // Toggle resolution dropdown popup
    grabBtn.addEventListener("click", (e) => {
      if (hasMoved) {
        hasMoved = false;
        return;
      }
      e.stopPropagation();
      e.preventDefault();

      if (isPopularMediaPortal(window.location.href)) {
        ensurePortalResolutionStreams();
      }

      const willShow = !menu.classList.contains("pdm-show");
      if (willShow) {
        // Adjust dropdown position relative to viewport boundaries
        const rect = overlay.getBoundingClientRect();
        if (rect.bottom > window.innerHeight - 260) {
          menu.style.top = "auto";
          menu.style.bottom = "100%";
          menu.style.marginTop = "0";
          menu.style.marginBottom = "6px";
        } else {
          menu.style.top = "100%";
          menu.style.bottom = "auto";
          menu.style.marginTop = "6px";
          menu.style.marginBottom = "0";
        }
        if (rect.right < 320) {
          menu.style.right = "auto";
          menu.style.left = "0";
        } else {
          menu.style.right = "0";
          menu.style.left = "auto";
        }

        menu.classList.add("pdm-show");
        renderStreamList(overlay);
      } else {
        menu.classList.remove("pdm-show");
      }
    });

    // Toggle menu on badge click
    grabBadge.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      menu.classList.toggle("pdm-show");
      if (menu.classList.contains("pdm-show")) {
        renderStreamList(overlay);
      }
    });

    // Toggle menu on right-click anywhere on button
    grabBtn.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      e.stopPropagation();
      menu.classList.toggle("pdm-show");
      if (menu.classList.contains("pdm-show")) {
        renderStreamList(overlay);
      }
    });

    // Close menu when clicking outside
    document.addEventListener("click", (e) => {
      if (!overlay.contains(e.target)) {
        menu.classList.remove("pdm-show");
      }
    });

    menu.addEventListener("click", (e) => {
      e.stopPropagation();
    });

    // Select All toggle
    selectAllBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const allSelected = capturedStreams.length > 0 && capturedStreams.every((s) => selectedStreamUrls.has(s.url));
      if (allSelected) {
        selectedStreamUrls.clear();
      } else {
        capturedStreams.forEach((s) => selectedStreamUrls.add(s.url));
      }
      renderStreamList(overlay);
    });

    // Download Selected
    dlNowBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      menu.classList.remove("pdm-show");
      executeSelectedDownloads(true);
    });

    // Add to Queue
    queueBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      menu.classList.remove("pdm-show");
      executeSelectedDownloads(false);
    });

    return overlay;
  }

  // 8. Position the Single Floater Exactly on Active Video
  function repositionGlobalOverlay() {
    if (isDismissedForPage) {
      if (globalOverlay) globalOverlay.style.display = "none";
      return;
    }

    const primary = getPrimaryMediaElement();
    if (!primary || !primary.el || !primary.rect) {
      if (globalOverlay) globalOverlay.style.display = "none";
      return;
    }

    const overlay = ensureGlobalOverlay();
    const rect = primary.rect;
    currentMediaEl = primary.el;

    // Fullscreen support
    const fsEl = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement;
    if (fsEl) {
      if (overlay.parentElement !== fsEl) fsEl.appendChild(overlay);
    } else {
      if (overlay.parentElement !== document.body) document.body.appendChild(overlay);
    }

    overlay.style.position = "fixed";
    overlay.style.zIndex = "2147483647";
    overlay.style.display = "block";

    if (customOffsetX !== null && customOffsetY !== null) {
      overlay.style.left = `${Math.max(4, rect.left + customOffsetX)}px`;
      overlay.style.top = `${Math.max(4, rect.top + customOffsetY)}px`;
    } else {
      const barRect = overlay.getBoundingClientRect();
      const currentWidth = barRect.width > 20 ? barRect.width : 70;
      overlay.style.top = `${Math.max(8, rect.top + 10)}px`;
      overlay.style.left = `${Math.max(8, rect.right - currentWidth - 14)}px`;
    }
  }

  // 9. Scan for Media Elements across DOM
  function scanMediaElements() {
    checkUrlChange();

    const candidates = [];
    document.querySelectorAll("video, audio").forEach((el) => candidates.push(el));

    document.querySelectorAll("shreddit-player-2, shreddit-async-loader").forEach((el) => {
      if (el.shadowRoot) {
        el.shadowRoot.querySelectorAll("video").forEach((vel) => candidates.push(vel));
      }
      const src = el.getAttribute("src") || el.getAttribute("stream-url");
      if (src) {
        const vel = el.shadowRoot ? el.shadowRoot.querySelector("video") : null;
        const res = detectResolution(vel, src);
        addStream({
          url: src,
          type: "video/mp4",
          label: document.title || "Reddit Video",
          resTag: res ? res.tag : "",
          resolution: res ? res.full : ""
        }, vel);
      }
    });

    candidates.forEach((el) => {
      const src = el.currentSrc || el.src;
      const res = detectResolution(el, src);
      if (src && !src.startsWith("blob:")) {
        addStream({
          url: src,
          type: el.tagName ? el.tagName.toLowerCase() : "video/mp4",
          label: document.title || "Web Video",
          resTag: res ? res.tag : "",
          resolution: res ? res.full : ""
        }, el);
      }
      el.querySelectorAll("source").forEach((srcEl) => {
        if (srcEl.src && !srcEl.src.startsWith("blob:")) {
          const sRes = detectResolution(el, srcEl.src);
          addStream({
            url: srcEl.src,
            type: srcEl.type || "video/mp4",
            label: document.title || "Web Video",
            resTag: sRes ? sRes.tag : "",
            resolution: sRes ? sRes.full : ""
          }, el);
        }
      });
    });

    if (isPopularMediaPortal(window.location.href)) {
      ensurePortalResolutionStreams();
    }

    repositionGlobalOverlay();
  }

  function updateAllOverlays() {
    if (!globalOverlay) return;
    const badge = globalOverlay.querySelector(".pdm-stream-badge");
    if (badge) {
      badge.textContent = capturedStreams.length;
      badge.style.display = capturedStreams.length > 0 ? "inline-block" : "none";
    }
    const menu = globalOverlay.querySelector(".pdm-stream-menu");
    if (menu && menu.classList.contains("pdm-show")) {
      renderStreamList(globalOverlay);
    }
  }

  function renderStreamList(overlay) {
    const listEl = overlay.querySelector(".pdm-stream-list");
    if (!listEl) return;

    listEl.innerHTML = "";
    capturedStreams.forEach((stream, idx) => {
      const item = document.createElement("div");
      item.className = "pdm-stream-item";

      const isChecked = selectedStreamUrls.has(stream.url);
      const label = stream.label || `Video Stream ${idx + 1}`;
      const resTag = stream.resTag || "";
      const resText = stream.resolution || "";

      let sizeStr = "";
      if (stream.size && stream.size > 0) {
        sizeStr = formatBytes(stream.size);
      } else {
        const primaryVid = document.querySelector("video");
        const dur = (primaryVid && primaryVid.duration && isFinite(primaryVid.duration) && primaryVid.duration > 0)
          ? primaryVid.duration
          : (stream.duration || 0);
        const estBytes = estimateBytesFromDuration(dur, resTag || "1080p");
        if (estBytes) {
          sizeStr = `~${formatBytes(estBytes)}`;
        } else {
          sizeStr = stream.type && stream.type.includes("mp4") ? "MP4 Stream" : "Ready";
        }
      }

      item.innerHTML = `
        <input type="checkbox" class="pdm-stream-checkbox" ${isChecked ? "checked" : ""}>
        <div class="pdm-stream-info">
          <div class="pdm-stream-title-row">
            ${resTag ? `<span class="pdm-res-pill pdm-res-${escapeHtml(resTag.toLowerCase())}">${escapeHtml(resTag)}</span>` : ""}
            <span class="pdm-stream-label">${escapeHtml(label)}</span>
          </div>
          <div class="pdm-stream-meta-row">
            ${resText ? `<span class="pdm-res-text">${escapeHtml(resText)}</span> • ` : ""}
            <span class="pdm-stream-meta">${escapeHtml(sizeStr)}</span>
          </div>
        </div>
        <button class="pdm-stream-quick-dl" title="Download this stream immediately" style="background:transparent;border:none;color:#38bdf8;cursor:pointer;font-size:14px;padding:4px 6px;margin-left:auto;">
          ⬇
        </button>
      `;

      const cb = item.querySelector(".pdm-stream-checkbox");
      const quickDlBtn = item.querySelector(".pdm-stream-quick-dl");

      function triggerThisStream(e) {
        e.stopPropagation();
        const baseTitle = getCleanTitle(currentMediaEl || document.querySelector("video"));
        let ext = ".mp4";
        if (stream.resTag === "SUB" || stream.isSubtitle) {
          ext = ".srt";
        } else if (stream.type && stream.type.includes("audio")) {
          ext = ".m4a";
        }
        const filename = baseTitle.toLowerCase().endsWith(ext) ? baseTitle : `${baseTitle}${ext}`;
        const menu = overlay.querySelector(".pdm-stream-menu");
        if (menu) menu.classList.remove("pdm-show");

        showPreDownloadCard({
          url: stream.url,
          filename: filename,
          resolution: stream.resTag || stream.resolution || "HD Video",
          size: stream.size || 0,
          referer: stream.referer || window.location.href,
          origin: stream.origin || window.location.origin,
          user_agent: stream.userAgent || navigator.userAgent,
          cookies: stream.cookies || ""
        });
      }

      quickDlBtn.addEventListener("click", triggerThisStream);
      item.addEventListener("click", (e) => {
        if (e.target === cb) return;
        triggerThisStream(e);
      });

      cb.addEventListener("click", (e) => e.stopPropagation());
      cb.addEventListener("change", () => {
        if (cb.checked) {
          selectedStreamUrls.add(stream.url);
        } else {
          selectedStreamUrls.delete(stream.url);
        }
      });

      listEl.appendChild(item);
    });
  }

  function executeSelectedDownloads(autoStart) {
    const targets = capturedStreams.filter((s) => selectedStreamUrls.has(s.url));
    if (targets.length === 0) {
      if (capturedStreams.length > 0) {
        targets.push(capturedStreams[0]);
      } else {
        showToast("Please select at least one stream to download.");
        return;
      }
    }

    if (targets.length === 1) {
      const target = targets[0];
      const baseTitle = getCleanTitle(currentMediaEl || document.querySelector("video"));
      let ext = ".mp4";
      if (target.resTag === "SUB" || target.isSubtitle) ext = ".srt";
      else if (target.type && target.type.includes("audio")) ext = ".m4a";
      const filename = baseTitle.toLowerCase().endsWith(ext) ? baseTitle : `${baseTitle}${ext}`;
      const menu = overlay ? overlay.querySelector(".pdm-stream-menu") : null;
      if (menu) menu.classList.remove("pdm-show");
      showPreDownloadCard({
        url: target.url,
        filename: filename,
        resolution: target.resTag || target.resolution || "HD Video",
        size: target.size || 0,
        referer: target.referer || window.location.href,
        origin: target.origin || window.location.origin,
        user_agent: target.userAgent || navigator.userAgent,
        cookies: target.cookies || ""
      });
      return;
    }

    const baseTitle = getCleanTitle(currentMediaEl || document.querySelector("video"));
    const items = targets.map((target, idx) => {
      let ext = ".mp4";
      if (target.resTag === "SUB" || target.isSubtitle) {
        ext = ".srt";
      } else if (target.type && target.type.includes("audio")) {
        ext = ".m4a";
      }
      const label = target.resTag ? `_${target.resTag.toLowerCase()}` : "";
      const baseName = baseTitle.toLowerCase().endsWith(ext)
        ? baseTitle.substring(0, baseTitle.length - ext.length)
        : baseTitle;
      const filename = targets.length > 1
        ? `${baseName}${label}${ext}`
        : (baseTitle.toLowerCase().endsWith(ext) ? baseTitle : `${baseTitle}${ext}`);

      return {
        url: target.url,
        filename: filename,
        label: `${baseName} (${target.resTag || target.resolution || "HD"})`,
        auto_start: autoStart,
        referer: target.referer || window.location.href,
        origin: target.origin || window.location.origin,
        user_agent: target.userAgent || navigator.userAgent,
        cookies: target.cookies || ""
      };
    });

    const menu = globalOverlay ? globalOverlay.querySelector(".pdm-stream-menu") : null;
    if (menu) menu.classList.remove("pdm-show");
    openBatchModal(false, items);
  }

    function sendBatchToPDM(items, autoStart) {
    chrome.runtime.sendMessage({
      action: "batch_download_native",
      items: items
    }, (resp) => {
      if (resp && resp.status === "ok") {
        if (globalOverlay) {
          const pill = globalOverlay.querySelector(".pdm-grab-button");
          if (pill) {
            pill.classList.add("pdm-btn-success");
            setTimeout(() => {
              pill.classList.remove("pdm-btn-success");
            }, 3000);
          }
        }
        if (resp.data && resp.data.task_ids && resp.data.task_ids.length > 0) {
          if (autoStart) {
            startActiveDownloadHUD(resp.data.task_ids[0], items[0].filename, 0);
          } else {
            renderQueuedNotice(items[0].filename);
          }
        } else {
          showToast("⚡ Sent download to Personal Download Manager!");
        }
      } else {
        const err = (resp && resp.error) || "Host connection failed. Ensure PDM is running.";
        showToast(`Connection Error: ${err}`);
      }
    });
  }

  function showToast(message) {
    let t = document.getElementById("pdm-quick-toast");
    if (!t) {
      t = document.createElement("div");
      t.id = "pdm-quick-toast";
      t.style.cssText = "position:fixed;bottom:24px;right:24px;background:#1e293b;color:#f8fafc;padding:9px 16px;border-radius:8px;font-size:12px;z-index:2147483647;border:1px solid #334155;box-shadow:0 8px 24px rgba(0,0,0,0.5);transition:opacity 0.3s;font-family:system-ui,sans-serif;";
      document.body.appendChild(t);
    }
    t.innerText = message;
    t.style.opacity = "1";
    setTimeout(() => { if (t) t.style.opacity = "0"; }, 3500);
  }

  // ==========================================================================
  // IN-PAGE ACTIVE DOWNLOAD CARD (FLOATING HUD) CONTROLLER & TWO-WAY SYNC
  // ==========================================================================
  let activeCardEl = null;
  let activeProgressInterval = null;
  let currentActiveTaskId = null;

  function initCardDragging(card) {
    if (!card || card._dragInitialized) return;
    card._dragInitialized = true;

    let isDragging = false;
    let startX = 0, startY = 0;
    let startLeft = 0, startTop = 0;

    card.addEventListener("mousedown", (e) => {
      const header = e.target.closest && e.target.closest(".pdm-card-header");
      if (!header) return;
      if (e.target.closest("button") || e.target.closest("input") || e.target.closest(".pdm-icon-btn")) return;
      if (e.button !== 0) return;

      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;

      const rect = card.getBoundingClientRect();
      startLeft = rect.left;
      startTop = rect.top;

      // Switch from transform-center to absolute pixel coordinates
      card.style.transform = "none";
      card.style.bottom = "auto";
      card.style.right = "auto";
      card.style.left = `${startLeft}px`;
      card.style.top = `${startTop}px`;
      card.classList.add("pdm-card-dragging");

      if (document.body) document.body.style.userSelect = "none";

      function onMouseMove(ev) {
        if (!isDragging) return;
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;

        let newLeft = startLeft + dx;
        let newTop = startTop + dy;

        const pad = 8;
        const maxL = (window.innerWidth || 1920) - rect.width - pad;
        const maxT = (window.innerHeight || 1080) - rect.height - pad;
        newLeft = Math.max(pad, Math.min(newLeft, maxL));
        newTop = Math.max(pad, Math.min(newTop, maxT));

        card.style.left = `${newLeft}px`;
        card.style.top = `${newTop}px`;
      }

      function onMouseUp() {
        if (!isDragging) return;
        isDragging = false;
        if (document.body) document.body.style.userSelect = "";
        card.classList.remove("pdm-card-dragging");
        window.removeEventListener("mousemove", onMouseMove, true);
        window.removeEventListener("mouseup", onMouseUp, true);
      }

      window.addEventListener("mousemove", onMouseMove, true);
      window.addEventListener("mouseup", onMouseUp, true);
    });
  }

  function getActiveCard() {
    if (!activeCardEl || !document.body.contains(activeCardEl)) {
      activeCardEl = document.getElementById("pdm-active-card");
      if (!activeCardEl) {
        activeCardEl = document.createElement("div");
        activeCardEl.id = "pdm-active-card";
        document.body.appendChild(activeCardEl);
      }
      initCardDragging(activeCardEl);
    }
    return activeCardEl;
  }

  function getMiniBadge() {
    // Suppressed: User requested zero screen clutter when hidden
    return { style: {} };
  }

  
  // IDM-Style Duplicate Download Notice Card
  function showDuplicateNoticeCard(existing, opts) {
    const card = getActiveCard();
    card.style.display = "block";

    const filename = existing.filename || opts.filename || "file";
    const filepath = existing.filepath || "";
    const sizeStr = existing.total_bytes > 0 ? ` (${formatBytes(existing.total_bytes)})` : "";

    card.innerHTML = `
      <div class="pdm-card-header" title="Drag to move anywhere">
        <div class="pdm-card-brand">
          <div class="pdm-card-logo">P</div>
          <span class="pdm-card-title">Personal Download Manager</span>
        </div>
        <span class="pdm-card-status-pill pdm-status-paused" style="background:rgba(234,179,8,0.18);color:#fbbf24;border:1px solid rgba(234,179,8,0.35);">
          Already Downloaded ℹ️
        </span>
        <div class="pdm-card-controls">
          <button class="pdm-icon-btn" id="pdm-card-close" title="Close">✕</button>
        </div>
      </div>
      <div class="pdm-card-body">
        <div class="pdm-file-box">
          <div class="pdm-filename" title="${escapeHtml(filename)}">${escapeHtml(filename)}${escapeHtml(sizeStr)}</div>
          <div style="font-size:11.5px;color:#cbd5e1;margin-top:6px;line-height:1.45;">
            এই ফাইলটি ইতিমধ্যে ডাউনলোড করা হয়েছে। আপনি কি ফাইলটি ওপেন করবেন নাকি আবার ডাউনলোড করতে চান?
          </div>
          ${filepath ? `<div style="font-size:10.5px;color:#94a3b8;margin-top:5px;word-break:break-all;">📂 ${escapeHtml(filepath)}</div>` : ''}
        </div>
        <div class="pdm-action-row" style="flex-direction:column;gap:8px;">
          <button class="pdm-btn-primary" id="pdm-dup-open" style="width:100%;">
            <span>📂 Open Existing File</span>
          </button>
          <div style="display:flex;gap:8px;width:100%;">
            <button class="pdm-btn-secondary" id="pdm-dup-redownload" style="flex:1;">
              <span>⚡ Download Again</span>
            </button>
            <button class="pdm-btn-secondary" id="pdm-dup-cancel" style="flex:1;">
              <span>Cancel</span>
            </button>
          </div>
        </div>
      </div>
    `;

    // 1. Open Existing File
    const openBtn = card.querySelector("#pdm-dup-open");
    if (openBtn) {
      openBtn.onclick = () => {
        chrome.runtime.sendMessage({
          action: "open_file",
          task_id: existing.id || 0,
          filepath: filepath
        });
        card.style.display = "none";
      };
    }

    // 2. Download Again (Force Re-download)
    const reDlBtn = card.querySelector("#pdm-dup-redownload");
    if (reDlBtn) {
      reDlBtn.onclick = () => {
        reDlBtn.innerHTML = "<span>Connecting...</span>";
        chrome.runtime.sendMessage({
          action: "download_via_native",
          url: opts.url,
          filename: opts.filename,
          auto_start: true,
          force_redownload: true,
          referer: opts.referer || window.location.href,
          origin: opts.origin || window.location.origin,
          user_agent: opts.user_agent || navigator.userAgent,
          cookies: opts.cookies || ""
        }, (resp) => {
          if (resp && resp.status === "ok" && resp.data && resp.data.task_ids && resp.data.task_ids.length > 0) {
            startActiveDownloadHUD(resp.data.task_ids[0], opts.filename, opts.size || 0);
          } else {
            showCardError((resp && resp.error) || "Host connection failed.");
          }
        });
      };
    }

    // 3. Close & Cancel
    const closeBtn = card.querySelector("#pdm-card-close");
    if (closeBtn) closeBtn.onclick = () => { card.style.display = "none"; };

    const cancelBtn = card.querySelector("#pdm-dup-cancel");
    if (cancelBtn) cancelBtn.onclick = () => { card.style.display = "none"; };
  }

  function showPreDownloadCard(opts) {
    const card = getActiveCard();
    // Default initial position: Centered on screen, draggable anywhere
    card.style.left = "50%";
    card.style.top = "50%";
    card.style.transform = "translate(-50%, -50%)";
    card.style.bottom = "auto";
    card.style.right = "auto";
    card.style.display = "block";

    if (activeProgressInterval) {
      clearInterval(activeProgressInterval);
      activeProgressInterval = null;
    }

    const initialFilename = opts.filename || "Video_Download.mp4";
    const sizeStr = opts.size && opts.size > 0 ? formatBytes(opts.size) : "Ready";
    const resTag = opts.resolution || "HD Video";

    card.innerHTML = `
      <div class="pdm-card-header" title="Drag to move anywhere">
        <div class="pdm-card-brand">
          <div class="pdm-card-logo">P</div>
          <span class="pdm-card-title">Personal Download Manager</span>
        </div>
        <span class="pdm-card-status-pill pdm-status-confirm">Confirm</span>
        <div class="pdm-card-controls">
          <button class="pdm-icon-btn" id="pdm-card-close" title="Close">✕</button>
        </div>
      </div>
      <div class="pdm-card-body">
        <div class="pdm-file-box">
          <label style="display:block;font-size:11px;color:#94a3b8;margin-bottom:5px;font-weight:500;">File Name:</label>
          <input type="text" id="pdm-confirm-filename" class="pdm-filename-input" value="${escapeHtml(initialFilename)}" spellcheck="false" />
          <div class="pdm-file-meta" style="margin-top:8px;">
            <span class="pdm-meta-tag pdm-meta-res">${escapeHtml(resTag)}</span>
            <span class="pdm-meta-tag">${escapeHtml(sizeStr)}</span>
          </div>
        </div>
        <div class="pdm-action-row">
          <button class="pdm-btn-primary" id="pdm-action-download-now">
            <span>⚡ Download Now</span>
          </button>
          <button class="pdm-btn-secondary" id="pdm-action-download-later">
            <span>🕒 Download Later (Queue)</span>
          </button>
        </div>
      </div>
    `;

    card.querySelector("#pdm-card-close").onclick = () => {
      card.style.display = "none";
    };

    // Download Now Handler with IDM-style Duplicate Protection
    function initiateDownload(forceRedownload = false) {
      const inputEl = card.querySelector("#pdm-confirm-filename");
      const chosenFilename = (inputEl ? inputEl.value.trim() : "") || initialFilename;
      const nowBtn = card.querySelector("#pdm-action-download-now");
      if (nowBtn) nowBtn.innerHTML = "<span>Connecting...</span>";
      chrome.runtime.sendMessage({
        action: "download_via_native",
        url: opts.url,
        filename: chosenFilename,
        auto_start: true,
        force_redownload: forceRedownload,
        referer: opts.referer || window.location.href,
        origin: opts.origin || window.location.origin,
        user_agent: opts.user_agent || navigator.userAgent,
        cookies: opts.cookies || ""
      }, (resp) => {
        if (resp && resp.status === "duplicate" && resp.existing_task) {
          showDuplicateNoticeCard(resp.existing_task, Object.assign({}, opts, { filename: chosenFilename }));
        } else if (resp && resp.status === "ok" && resp.data && resp.data.task_ids && resp.data.task_ids.length > 0) {
          startActiveDownloadHUD(resp.data.task_ids[0], chosenFilename, opts.size || 0);
        } else {
          showCardError((resp && resp.error) || "Host connection failed. Check if PDM is running.");
        }
      });
    }

    const nowBtn = card.querySelector("#pdm-action-download-now");
    if (nowBtn) nowBtn.onclick = () => initiateDownload(false);

    // Download Later / Queue Handler
    card.querySelector("#pdm-action-download-later").onclick = () => {
      const inputEl = card.querySelector("#pdm-confirm-filename");
      const chosenFilename = (inputEl ? inputEl.value.trim() : "") || initialFilename;
      chrome.runtime.sendMessage({
        action: "download_via_native",
        url: opts.url,
        filename: chosenFilename,
        auto_start: false,
        referer: opts.referer || window.location.href,
        origin: opts.origin || window.location.origin,
        user_agent: opts.user_agent || navigator.userAgent,
        cookies: opts.cookies || ""
      }, (resp) => {
        if (resp && resp.status === "ok") {
          renderQueuedNotice(chosenFilename);
        } else {
          showCardError((resp && resp.error) || "Failed to add to queue.");
        }
      });
    };
  }

  function renderQueuedNotice(filename) {
    const card = getActiveCard();
    card.innerHTML = `
      <div class="pdm-card-header" title="Drag to move anywhere">
        <div class="pdm-card-brand">
          <div class="pdm-card-logo">P</div>
          <span class="pdm-card-title">Personal Download Manager</span>
        </div>
        <span class="pdm-card-status-pill pdm-status-paused">Queued 🕒</span>
        <div class="pdm-card-controls">
          <button class="pdm-icon-btn" id="pdm-card-close" title="Close">✕</button>
        </div>
      </div>
      <div class="pdm-card-body">
        <div class="pdm-file-box">
          <div class="pdm-filename" title="${escapeHtml(filename)}">${escapeHtml(filename)}</div>
          <div style="font-size:11.5px;color:#94a3b8;margin-top:6px;">
            ✓ Saved to PDM Download Queue in Paused state. You can resume or schedule this download anytime from the desktop app.
          </div>
        </div>
        <div class="pdm-action-row">
          <button class="pdm-btn-secondary" id="pdm-action-done" style="width:100%;">
            <span>Done</span>
          </button>
        </div>
      </div>
    `;
    card.querySelector("#pdm-card-close").onclick = () => { card.style.display = "none"; };
    card.querySelector("#pdm-action-done").onclick = () => { card.style.display = "none"; };
    setTimeout(() => {
      if (card && card.style.display !== "none") card.style.display = "none";
    }, 4500);
  }

  function startActiveDownloadHUD(taskId, filename, size) {
    const card = getActiveCard();
    const badge = getMiniBadge();
    badge.style.display = "none";
    card.style.display = "block";

    // If HUD is already active for this exact task, update filename without tearing down DOM
    if (currentActiveTaskId === taskId && document.getElementById("pdm-hud-bar")) {
      const fnEl = document.getElementById("pdm-hud-filename");
      if (fnEl && filename && filename !== "File Download" && !filename.startsWith("http")) {
        fnEl.textContent = filename;
        fnEl.title = filename;
      }
      return;
    }
    currentActiveTaskId = taskId;

    card.innerHTML = `
      <div class="pdm-card-header" title="Drag to move anywhere">
        <div class="pdm-card-brand">
          <div class="pdm-card-logo">P</div>
          <span class="pdm-card-title">Personal Download Manager</span>
        </div>
        <span class="pdm-card-status-pill pdm-status-downloading" id="pdm-hud-status">Downloading ⚡</span>
        <div class="pdm-card-controls">
          <button class="pdm-icon-btn" id="pdm-hud-mini" title="Hide to PDM Desktop App (Runs in Background)">🗕</button>
          <button class="pdm-icon-btn" id="pdm-card-close" title="Close">✕</button>
        </div>
      </div>
      <div class="pdm-card-body">
        <div class="pdm-file-box">
          <div class="pdm-filename" id="pdm-hud-filename" title="${escapeHtml(filename)}">${escapeHtml(filename)}</div>
        </div>
        <div class="pdm-progress-track">
          <div class="pdm-progress-fill" id="pdm-hud-bar" style="width: 0%;"></div>
        </div>
        <div class="pdm-stats-row">
          <div class="pdm-stat-left">
            <span class="pdm-stat-percent" id="pdm-hud-pct">0%</span>
            <span class="pdm-stat-speed" id="pdm-hud-spd">⚡ 0 KB/s</span>
          </div>
          <div class="pdm-stat-right">
            <span id="pdm-hud-bytes">0 MB / ...</span>
            <span id="pdm-hud-eta">⏱️ ...</span>
          </div>
        </div>
        <div class="pdm-action-row" id="pdm-hud-actions">
          <button class="pdm-btn-secondary" id="pdm-btn-pause-resume">
            <span id="pdm-lbl-pause">⏸️ Pause</span>
          </button>
          <button class="pdm-btn-danger" id="pdm-btn-cancel">
            <span>✕ Cancel</span>
          </button>
        </div>
      </div>
    `;

    // Clean Hide to Main Desktop App: Removes from browser screen without leaving any sticky bar
    function hideToDesktopApp() {
      card.style.display = "none";
      if (activeProgressInterval) {
        clearInterval(activeProgressInterval);
        activeProgressInterval = null;
      }
    }

    const closeBtn = card.querySelector("#pdm-card-close");
    if (closeBtn) closeBtn.onclick = hideToDesktopApp;

    const miniBtn = card.querySelector("#pdm-hud-mini");
    if (miniBtn) miniBtn.onclick = hideToDesktopApp;

    // Pause / Resume Toggle
    let isPaused = false;
    const pauseBtn = card.querySelector("#pdm-btn-pause-resume");
    const pauseLbl = card.querySelector("#pdm-lbl-pause");
    pauseBtn.onclick = () => {
      if (!isPaused) {
        chrome.runtime.sendMessage({ action: "pause_task", task_id: taskId });
        isPaused = true;
        pauseLbl.innerText = "▶️ Resume";
        const st = card.querySelector("#pdm-hud-status");
        if (st) {
          st.className = "pdm-card-status-pill pdm-status-paused";
          st.innerText = "Paused";
        }
      } else {
        chrome.runtime.sendMessage({ action: "resume_task", task_id: taskId });
        isPaused = false;
        pauseLbl.innerText = "⏸️ Pause";
        const st = card.querySelector("#pdm-hud-status");
        if (st) {
          st.className = "pdm-card-status-pill pdm-status-downloading";
          st.innerText = "Downloading ⚡";
        }
      }
    };

    // Cancel Button
    card.querySelector("#pdm-btn-cancel").onclick = () => {
      chrome.runtime.sendMessage({ action: "cancel_task", task_id: taskId });
      if (activeProgressInterval) clearInterval(activeProgressInterval);
      activeProgressInterval = null;
      card.style.display = "none";
      badge.style.display = "none";
    };

    // Start 500ms polling loop
    if (activeProgressInterval) clearInterval(activeProgressInterval);
    activeProgressInterval = setInterval(() => {
      chrome.runtime.sendMessage({ action: "get_task_progress", task_id: taskId }, (res) => {
        if (!res || res.status !== "ok" || !res.task) return;
        const t = res.task;

        // Update Progress Bar
        const bar = document.getElementById("pdm-hud-bar");
        if (bar) bar.style.width = `${t.progress}%`;

        // Update Stats
        const pctEl = document.getElementById("pdm-hud-pct");
        if (pctEl) pctEl.innerText = `${t.progress}%`;

        const spdEl = document.getElementById("pdm-hud-spd");
        if (spdEl) spdEl.innerText = `⚡ ${t.speed_formatted}`;

        const bytesEl = document.getElementById("pdm-hud-bytes");
        if (bytesEl) {
          const dlStr = formatBytes(t.downloaded);
          const totStr = t.total > 0 ? formatBytes(t.total) : "...";
          bytesEl.innerText = `${dlStr} / ${totStr}`;
        }

        const etaEl = document.getElementById("pdm-hud-eta");
        if (etaEl) etaEl.innerText = t.eta_formatted ? `⏱️ ${t.eta_formatted}` : "";

        // Update Mini Badge
        const miniPct = document.getElementById("pdm-mini-pct");
        if (miniPct) miniPct.innerText = `${t.progress}%`;

        const miniSpd = document.getElementById("pdm-mini-spd");
        if (miniSpd) miniSpd.innerText = t.speed_formatted;

        // Check if finished
        if (t.status === "completed" || t.progress >= 100) {
          clearInterval(activeProgressInterval);
          activeProgressInterval = null;
          renderCompletedHUD(t);
        }
      });
    }, 500);
  }

  function renderCompletedHUD(task) {
    const card = getActiveCard();
    const badge = getMiniBadge();
    badge.style.display = "none";
    card.style.display = "block";

    card.innerHTML = `
      <div class="pdm-card-header" title="Drag to move anywhere">
        <div class="pdm-card-brand">
          <div class="pdm-card-logo">P</div>
          <span class="pdm-card-title">Personal Download Manager</span>
        </div>
        <span class="pdm-card-status-pill pdm-status-completed">Completed ✓</span>
        <div class="pdm-card-controls">
          <button class="pdm-icon-btn" id="pdm-card-close" title="Close">✕</button>
        </div>
      </div>
      <div class="pdm-card-body">
        <div class="pdm-file-box">
          <div class="pdm-filename" title="${escapeHtml(task.filename)}">${escapeHtml(task.filename)}</div>
          <div style="font-size:11.5px;color:#34d399;font-weight:600;margin-top:4px;">
            ✓ Download Complete (${formatBytes(task.total || task.downloaded)})
          </div>
        </div>
        <div class="pdm-action-row">
          <button class="pdm-btn-primary" id="pdm-btn-open-file">
            <span>📂 Open File</span>
          </button>
          <button class="pdm-btn-secondary" id="pdm-btn-open-folder">
            <span>📁 Open Folder</span>
          </button>
        </div>
      </div>
    `;

    card.querySelector("#pdm-card-close").onclick = () => { card.style.display = "none"; };

    card.querySelector("#pdm-btn-open-file").onclick = () => {
      chrome.runtime.sendMessage({ action: "open_file", task_id: task.id });
    };

    card.querySelector("#pdm-btn-open-folder").onclick = () => {
      chrome.runtime.sendMessage({ action: "open_folder", task_id: task.id });
    };
  }

  function showCardError(errMsg) {
    const card = getActiveCard();
    card.innerHTML = `
      <div class="pdm-card-header" title="Drag to move anywhere">
        <div class="pdm-card-brand">
          <div class="pdm-card-logo">P</div>
          <span class="pdm-card-title">Personal Download Manager</span>
        </div>
        <span class="pdm-card-status-pill pdm-btn-danger">Error</span>
        <div class="pdm-card-controls">
          <button class="pdm-icon-btn" id="pdm-card-close" title="Close">✕</button>
        </div>
      </div>
      <div class="pdm-card-body">
        <div style="color:#f87171;font-size:12.5px;margin-bottom:12px;">${escapeHtml(errMsg)}</div>
        <button class="pdm-btn-secondary" id="pdm-card-err-close" style="width:100%;">Close</button>
      </div>
    `;
    card.querySelector("#pdm-card-close").onclick = () => { card.style.display = "none"; };
    card.querySelector("#pdm-card-err-close").onclick = () => { card.style.display = "none"; };
  }

  // Listen to background messages for active downloads triggered outside content script
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "PDM_ACTIVE_DOWNLOAD_STARTED" && msg.taskId) {
      startActiveDownloadHUD(msg.taskId, msg.title || "File Download", 0);
    }
  });


  const KNOWN_DOWNLOAD_EXTENSIONS = new Set([
    "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso", "img", "bin",
    "exe", "msi", "apk", "dmg", "pkg", "deb", "rpm",
    "mp4", "mkv", "avi", "webm", "mov", "flv", "wmv", "m4v", "ts", "3gp",
    "mp3", "flac", "wav", "aac", "ogg", "m4a", "opus", "wma",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "epub", "csv", "srt", "vtt", "torrent"
  ]);

  function getUrlExtension(str) {
    if (!str) return null;
    try {
      const clean = str.split("?")[0].split("#")[0].trim();
      const dot = clean.lastIndexOf(".");
      if (dot === -1) return null;
      const ext = clean.substring(dot + 1).toLowerCase();
      if (ext.length >= 1 && ext.length <= 10 && !ext.includes("/")) {
        return ext;
      }
    } catch (e) {}
    return null;
  }

  // 8. Batch Link Scanner & Grabber Dialog (IDM "Download all with IDM" feature)
  function scanPageDownloadLinks(onlySelection = false) {
    const links = [];
    const seenUrls = new Set();

    let anchorList = [];
    if (onlySelection) {
      const selection = window.getSelection();
      if (selection && selection.rangeCount > 0) {
        const selectedText = selection.toString();
        const urlMatches = selectedText.match(/https?:\/\/[^\s'"<>)]+/g) || [];
        for (const u of urlMatches) {
          if (!seenUrls.has(u)) {
            const ext = getUrlExtension(u);
            const rawName = u.split("/").pop().split("?")[0].split("#")[0] || "File";
            const fn = ext && !rawName.toLowerCase().endsWith(`.${ext}`) ? `${rawName}.${ext}` : rawName;
            links.push({
              url: u,
              filename: fn,
              label: rawName
            });
            seenUrls.add(u);
          }
        }

        const range = selection.getRangeAt(0);
        const container = range.commonAncestorContainer;
        const parent = container.nodeType === 1 ? container : container.parentElement;
        if (parent) {
          parent.querySelectorAll("a, button, [role='button']").forEach((a) => {
            if (selection.containsNode(a, true)) {
              anchorList.push(a);
            }
          });
        }
      }
    } else {
      anchorList = Array.from(document.querySelectorAll("a, button, [role='button']"));
    }

    const anchors = anchorList.slice(0, 200);

    for (const a of anchors) {
      let href = a.href || a.getAttribute("data-url") || a.getAttribute("data-href") || a.getAttribute("data-link");
      if (!href && a.tagName === "BUTTON") {
        const onclickAttr = a.getAttribute("onclick") || "";
        const m = onclickAttr.match(/https?:\/\/[^\s'"\)]+/);
        if (m) href = m[0];
      }
      if (!href || (!href.startsWith("http://") && !href.startsWith("https://"))) continue;
      if (seenUrls.has(href)) continue;

      const ext = getUrlExtension(href);
      const isKnownExt = ext ? KNOWN_DOWNLOAD_EXTENSIONS.has(ext) : false;
      const hasDownloadAttr = a.hasAttribute && a.hasAttribute("download");
      const text = (a.innerText || "").trim().toLowerCase();
      const isDownloadText = text === "download" || text.includes("download") || (a.title && a.title.toLowerCase().includes("download"));
      const classText = (a.className && typeof a.className === "string") ? a.className.toLowerCase() : "";
      const isDownloadClass = classText.includes("download") || classText.includes("btn-download");

      if (onlySelection || isKnownExt || hasDownloadAttr || isDownloadText || isDownloadClass) {
        seenUrls.add(href);

        let title = "";
        const row = a.closest("tr, li, [class*='row'], [class*='item'], [class*='episode'], [class*='card']");
        if (row) {
          const candidateEls = row.querySelectorAll("td, th, span, div, strong, b, h1, h2, h3, h4, h5, h6, p");
          for (const cel of candidateEls) {
            if (cel !== a && !cel.contains(a) && !a.contains(cel)) {
              const txt = cel.innerText.trim();
              if (txt && !txt.toLowerCase().includes("download") && txt.length > 2) {
                title = txt;
                break;
              }
            }
          }
          if (!title) {
            title = row.innerText.replace(/download/gi, "").trim();
          }
        }

        if (!title || title.toLowerCase() === "download") {
          title = (a.getAttribute && a.getAttribute("download")) || a.title || a.innerText.trim() || href.split("/").pop() || "File";
        }

        title = title.split("\n")[0].trim().replace(/[<>:"/\\|?*]/g, "_").substring(0, 100);

        let filename = title;
        if (ext) {
          if (!filename.toLowerCase().endsWith(`.${ext}`)) {
            filename = `${filename}.${ext}`;
          }
        } else if (!filename.match(/\.[a-zA-Z0-9]{2,5}$/)) {
          if (/(s\d+|e\d+|episode|season|king|movie|video|1080p|720p|480p)/i.test(filename)) {
            filename = `${filename}.mp4`;
          }
        }

        links.push({
          url: href,
          filename: filename,
          label: title
        });
      }
    }

    return links;
  }

  let batchPillElement = null;

  function updateBatchPill() {
    if (!document.body) return;

    const links = scanPageDownloadLinks(false);
    if (links.length >= 2) {
      if (!batchPillElement) {
        batchPillElement = document.createElement("div");
        batchPillElement.className = "pdm-batch-floating-btn";
        batchPillElement.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="#3b82f6">
            <path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"/>
          </svg>
          <span>Grab All Links (<span class="pdm-batch-count">${links.length}</span>)</span>
        `;
        batchPillElement.addEventListener("click", () => openBatchModal(false));
        document.body.appendChild(batchPillElement);
      } else {
        const countSpan = batchPillElement.querySelector(".pdm-batch-count");
        if (countSpan) countSpan.textContent = links.length;
      }
    } else if (batchPillElement) {
      batchPillElement.remove();
      batchPillElement = null;
    }
  }

  function openBatchModal(onlySelection = false, customItems = null) {
    const existing = document.querySelector(".pdm-modal-backdrop");
    if (existing) existing.remove();

    const links = (customItems && customItems.length > 0) ? customItems : scanPageDownloadLinks(onlySelection);
    if (!links || links.length === 0) {
      showToast("No downloadable links found.");
      return;
    }

    const backdrop = document.createElement("div");
    backdrop.className = "pdm-modal-backdrop";
    backdrop.innerHTML = `
      <div class="pdm-modal-card">
        <div class="pdm-modal-header">
          <div class="pdm-modal-title">📥 Personal Download Manager — Batch Grabber</div>
          <button class="pdm-modal-close" title="Close">✕</button>
        </div>
        <div class="pdm-modal-body">
          <div class="pdm-modal-toolbar">
            <span>Detected <b>${links.length}</b> downloadable item(s)</span>
            <div style="display:flex; gap:12px;">
              <button class="pdm-link-btn pdm-modal-select-all">Select All</button>
              <button class="pdm-link-btn pdm-modal-deselect-all">Deselect All</button>
            </div>
          </div>
          <div class="pdm-modal-item-list"></div>
        </div>
        <div class="pdm-modal-footer">
          <button class="pdm-action-btn pdm-action-download pdm-batch-dl-btn">
            ▶ Download Selected (${links.length})
          </button>
          <button class="pdm-action-btn pdm-action-queue pdm-batch-queue-btn">
            ⏳ Add to Queue
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(backdrop);

    const listContainer = backdrop.querySelector(".pdm-modal-item-list");
    const selectAllBtn = backdrop.querySelector(".pdm-modal-select-all");
    const deselectAllBtn = backdrop.querySelector(".pdm-modal-deselect-all");
    const dlBtn = backdrop.querySelector(".pdm-batch-dl-btn");
    const queueBtn = backdrop.querySelector(".pdm-batch-queue-btn");
    const closeBtn = backdrop.querySelector(".pdm-modal-close");

    const selectedSet = new Set(links.map((_, i) => i));

    function renderItems() {
      listContainer.innerHTML = "";
      links.forEach((item, idx) => {
        const row = document.createElement("div");
        row.className = "pdm-modal-item";
        row.innerHTML = `
          <input type="checkbox" class="pdm-stream-checkbox" ${selectedSet.has(idx) ? "checked" : ""}>
          <div class="pdm-item-info">
            <div class="pdm-item-title">${escapeHtml(item.label)}</div>
            <div class="pdm-item-url">${escapeHtml(item.url)}</div>
          </div>
        `;

        const cb = row.querySelector("input");
        cb.addEventListener("change", () => {
          if (cb.checked) selectedSet.add(idx);
          else selectedSet.delete(idx);
          updateButtons();
        });

        row.addEventListener("click", (e) => {
          if (e.target !== cb) {
            cb.checked = !cb.checked;
            cb.dispatchEvent(new Event("change"));
          }
        });

        listContainer.appendChild(row);
      });
      updateButtons();
    }

    function updateButtons() {
      const count = selectedSet.size;
      dlBtn.textContent = `▶ Download Selected (${count})`;
      dlBtn.disabled = count === 0;
      queueBtn.disabled = count === 0;
    }

    selectAllBtn.addEventListener("click", () => {
      links.forEach((_, i) => selectedSet.add(i));
      renderItems();
    });

    deselectAllBtn.addEventListener("click", () => {
      selectedSet.clear();
      renderItems();
    });

    closeBtn.addEventListener("click", () => backdrop.remove());
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.remove();
    });

    function dispatchBatch(autoStart) {
      const chosen = links.filter((_, i) => selectedSet.has(i));
      if (chosen.length === 0) return;

      const items = chosen.map((c) => ({
        url: c.url,
        filename: c.filename,
        auto_start: autoStart,
        referer: c.referer || window.location.href,
        origin: c.origin || window.location.origin,
        user_agent: c.user_agent || navigator.userAgent,
        cookies: c.cookies || ""
      }));

      backdrop.remove();
      sendBatchToPDM(items, autoStart);
    }

    dlBtn.addEventListener("click", () => dispatchBatch(true));
    queueBtn.addEventListener("click", () => dispatchBatch(false));

    renderItems();
  }

  // 9. Lightweight MutationObserver for dynamically injected player DOMs
  let scanDebounceTimer = null;
  function debounceScan() {
    if (scanDebounceTimer) clearTimeout(scanDebounceTimer);
    scanDebounceTimer = setTimeout(() => {
      scanMediaElements();
      updateBatchPill();
    }, 400);
  }

  const domObserver = new MutationObserver((mutations) => {
    let shouldScan = false;
    for (const m of mutations) {
      if (m.type === "childList") {
        for (const node of m.addedNodes) {
          if (node.nodeType === 1) {
            if (node.tagName === "VIDEO" || node.tagName === "AUDIO" || (node.querySelector && node.querySelector("video, audio"))) {
              shouldScan = true;
              break;
            }
          }
        }
      } else if (m.type === "attributes" && (m.attributeName === "src" || m.attributeName === "data-src")) {
        if (m.target.tagName === "VIDEO" || m.target.tagName === "AUDIO" || m.target.tagName === "SOURCE") {
          shouldScan = true;
          break;
        }
      }
      if (shouldScan) break;
    }
    if (shouldScan) {
      debounceScan();
    }
  });

  try {
    domObserver.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["src", "data-src"]
    });
  } catch (e) {}

  // Global event hooks to ensure floater follows video seamlessly
  function repositionAllOverlays() {
    repositionGlobalOverlay();
  }

  // Periodic ticker to detect dynamic SPA videos and keep floater aligned
  setInterval(() => {
    scanMediaElements();
    repositionAllOverlays();
  }, 600);

  // Capture all container scrolls
  document.addEventListener("scroll", repositionAllOverlays, { capture: true, passive: true });
  window.addEventListener("resize", repositionAllOverlays, { passive: true });

  // Playback & hover events
  document.addEventListener("play", (e) => {
    if (e.target && (e.target.tagName === "VIDEO" || e.target.tagName === "AUDIO")) {
      scanMediaElements();
      repositionAllOverlays();
    }
  }, true);

  document.addEventListener("playing", (e) => {
    if (e.target && (e.target.tagName === "VIDEO" || e.target.tagName === "AUDIO")) {
      scanMediaElements();
      repositionAllOverlays();
    }
  }, true);

  document.addEventListener("mousemove", (e) => {
    if (e.target && (e.target.tagName === "VIDEO" || (e.target.closest && e.target.closest("video, .pdm-video-overlay")))) {
      repositionAllOverlays();
    }
  }, { passive: true });

  // Immediate and staggered scans on script injection
  scanMediaElements();
  setTimeout(scanMediaElements, 300);
  setTimeout(scanMediaElements, 800);
  setTimeout(scanMediaElements, 2000);
})();
