// Personal Download Manager (PDM) Extension Content Script
// Dynamic Video Player Grabber, Multi-Stream Sniffer & Universal Link Interceptor

(function () {
  if (window.__pdm_grabber_initialized) return;
  window.__pdm_grabber_initialized = true;

  const capturedStreams = [];
  const selectedStreamUrls = new Set();
  const overlays = new Map();

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

    if (lower.includes("facebook.com") || lower.includes("fb.watch")) {
      if (videoEl) {
        const article = videoEl.closest('[role="article"], [data-pagelet], [data-virtualized="false"], div[id^="mount_"]');
        if (article) {
          const links = article.querySelectorAll('a[href*="/videos/"], a[href*="/reel/"], a[href*="/watch/"], a[href*="story.php"], a[href*="permalink.php"], a[href*="/posts/"]');
          for (const a of links) {
            if (a.href && !a.href.includes("comment") && !a.href.includes("reaction")) {
              return a.href;
            }
          }
        }
      }
      return currentUrl;
    }

    if (lower.includes("instagram.com")) {
      if (videoEl) {
        const article = videoEl.closest("article, main");
        if (article) {
          const link = article.querySelector('a[href*="/p/"], a[href*="/reel/"]');
          if (link && link.href) return link.href;
        }
      }
      return currentUrl;
    }

    return currentUrl;
  }

  // 2. SPA Navigation Reset (YouTube, Facebook, Twitter, Reddit, etc.)
  function handleNavigation() {
    capturedStreams.length = 0;
    selectedStreamUrls.clear();
    overlays.forEach((overlay) => overlay.remove());
    overlays.clear();
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

  // 5. Scan for HTML5 video/audio elements on page (including Reddit & Shadow DOM)
  function scanMediaElements() {
    const candidates = [];

    // Standard video and audio tags
    document.querySelectorAll("video, audio").forEach((el) => candidates.push(el));

    // Reddit custom player components
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
        attachOverlay(el, vel);
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

      attachOverlay(el, el);
    });

    // Only offer clean merged video URL on known platforms where media stream downloader handles audio+video muxing
    if (candidates.length > 0 && isPopularMediaPortal(window.location.href)) {
      const primaryVideo = candidates.find((c) => c.tagName && c.tagName.toLowerCase() === "video");
      const portalMediaUrl = getPortalVideoUrl(primaryVideo);
      const pRes = detectResolution(primaryVideo, portalMediaUrl);
      if (!capturedStreams.some((s) => s.isMasterStream)) {
        addStream({
          url: portalMediaUrl,
          type: "video/mp4",
          label: "🎬 Download Complete Video (Full HD + Audio)",
          resTag: (pRes && pRes.tag) ? pRes.tag : "1080p",
          resolution: (pRes && pRes.full) ? pRes.full : "Full HD with Audio",
          referer: window.location.href,
          isMasterStream: true
        }, primaryVideo, true);
      }
    }
  }

  // 6. Attach Floating Download Overlay onto Video Element
  function attachOverlay(videoEl, actualVideoEl = null) {
    if (overlays.has(videoEl)) return;

    const activeVideo = actualVideoEl || (videoEl.tagName && videoEl.tagName.toLowerCase() === "video" ? videoEl : (videoEl.querySelector ? videoEl.querySelector("video") : null));

    const overlay = document.createElement("div");
    overlay.className = "pdm-video-overlay";
    overlay.innerHTML = `
      <div class="pdm-grab-button" title="Download with Personal Download Manager">
        <svg class="pdm-grab-icon" viewBox="0 0 24 24">
          <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
        </svg>
        <span class="pdm-btn-text" style="display:none;"></span>
        <span class="pdm-stream-badge" style="display:none;">0</span>
      </div>
      <div class="pdm-stream-menu">
        <div class="pdm-menu-header">
          <span class="pdm-header-title">Detected Streams</span>
          <span class="pdm-select-all">Select All</span>
        </div>
        <div class="pdm-stream-list"></div>
        <div class="pdm-action-row">
          <button class="pdm-action-btn pdm-action-download" title="Download selected immediately">
            ▶ Download Now
          </button>
          <button class="pdm-action-btn pdm-action-queue" title="Add to queue for later">
            ⏳ Add to Queue
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);
    overlays.set(videoEl, overlay);

    const btn = overlay.querySelector(".pdm-grab-button");
    const menu = overlay.querySelector(".pdm-stream-menu");
    const selectAllBtn = overlay.querySelector(".pdm-select-all");
    const dlNowBtn = overlay.querySelector(".pdm-action-download");
    const queueBtn = overlay.querySelector(".pdm-action-queue");

    function updateLabelAndResolution() {
      if (activeVideo) {
        const res = detectResolution(activeVideo, activeVideo.currentSrc || activeVideo.src);
        if (btn) {
          if (res && res.tag && res.tag !== "AUDIO") {
            btn.title = `Download Video (${res.tag}) with PDM`;
          } else {
            btn.title = "Download Video with PDM";
          }
        }

        const pageUrl = window.location.href;
        const pageStream = capturedStreams.find((s) => s.url === pageUrl);
        if (pageStream && res) {
          pageStream.resTag = res.tag;
          pageStream.resolution = res.full;
        }

        const directSrc = activeVideo.currentSrc || activeVideo.src;
        if (directSrc) {
          const directStream = capturedStreams.find((s) => s.url === directSrc);
          if (directStream && res) {
            directStream.resTag = res.tag;
            directStream.resolution = res.full;
          }
        }
      }
      reposition();
    }

    if (activeVideo) {
      activeVideo.addEventListener("loadedmetadata", updateLabelAndResolution);
      activeVideo.addEventListener("durationchange", updateLabelAndResolution);
      activeVideo.addEventListener("play", updateLabelAndResolution);
      activeVideo.addEventListener("playing", updateLabelAndResolution);
      activeVideo.addEventListener("canplay", updateLabelAndResolution);
      updateLabelAndResolution();
    }

    // Toggle menu
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();

      updateLabelAndResolution();

      if (capturedStreams.length === 0) {
        let direct = (activeVideo && (activeVideo.currentSrc || activeVideo.src)) || videoEl.currentSrc || videoEl.src;
        if (!direct || direct.startsWith("blob:")) {
          if (isPopularMediaPortal(window.location.href)) {
            direct = window.location.href;
          } else {
            direct = null;
          }
        }
        if (direct && direct.startsWith("http")) {
          sendBatchToPDM([{
            url: direct,
            filename: `${getCleanTitle()}.mp4`,
            auto_start: true,
            referer: window.location.href,
            origin: window.location.origin,
            user_agent: navigator.userAgent
          }], true);
        } else {
          showToast("Stream loading... Click play on the video player.");
        }
        return;
      }

      menu.classList.toggle("pdm-show");
      renderStreamList(overlay);
    });

    // Close menu when clicking outside
    document.addEventListener("click", () => {
      menu.classList.remove("pdm-show");
    });

    menu.addEventListener("click", (e) => {
      e.stopPropagation();
    });

    // Select All toggle
    selectAllBtn.addEventListener("click", () => {
      const allSelected = capturedStreams.every((s) => selectedStreamUrls.has(s.url));
      if (allSelected) {
        selectedStreamUrls.clear();
      } else {
        capturedStreams.forEach((s) => selectedStreamUrls.add(s.url));
      }
      renderStreamList(overlay);
    });

    // Download Now Action
    dlNowBtn.addEventListener("click", () => {
      menu.classList.remove("pdm-show");
      executeSelectedDownloads(true);
    });

    // Add to Queue Action
    queueBtn.addEventListener("click", () => {
      menu.classList.remove("pdm-show");
      executeSelectedDownloads(false);
    });

    // Position tracking
    function reposition() {
      if (!document.body.contains(videoEl)) {
        overlay.remove();
        overlays.delete(videoEl);
        return;
      }
      const rect = videoEl.getBoundingClientRect();
      if (rect.width < 100 || rect.height < 80 || rect.bottom < 0 || rect.top > window.innerHeight) {
        overlay.style.display = "none";
        return;
      }

      overlay.style.display = "block";
      overlay.style.top = `${Math.max(4, window.scrollY + rect.top + 10)}px`;
      overlay.style.left = `${Math.max(4, window.scrollX + rect.right - 44)}px`;
    }

    window.addEventListener("scroll", reposition, { passive: true });
    window.addEventListener("resize", reposition, { passive: true });

    reposition();
  }

  function updateAllOverlays() {
    overlays.forEach((overlay) => {
      const badge = overlay.querySelector(".pdm-stream-badge");
      if (badge) {
        badge.textContent = capturedStreams.length;
        badge.style.display = capturedStreams.length > 0 ? "inline-block" : "none";
      }
      renderStreamList(overlay);
    });
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

      quickDlBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const baseTitle = getCleanTitle(document.querySelector("video"));
        const ext = stream.type && stream.type.includes("audio") ? ".mp3" : ".mp4";
        const filename = baseTitle.toLowerCase().endsWith(ext) ? baseTitle : `${baseTitle}${ext}`;
        sendBatchToPDM([{
          url: stream.url,
          filename: filename,
          auto_start: true,
          referer: stream.referer || window.location.href,
          origin: stream.origin || window.location.origin,
          user_agent: stream.userAgent || navigator.userAgent,
          cookies: stream.cookies || ""
        }], true);
        const menu = overlay.querySelector(".pdm-stream-menu");
        if (menu) menu.classList.remove("pdm-show");
      });

      item.addEventListener("click", () => {
        cb.checked = !cb.checked;
        if (cb.checked) {
          selectedStreamUrls.add(stream.url);
        } else {
          selectedStreamUrls.delete(stream.url);
        }
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

    // Default to the single best selected stream to prevent downloading fragmented split pieces of the same video
    const target = targets[0];
    const baseTitle = getCleanTitle(document.querySelector("video"));
    const ext = target.type && target.type.includes("audio") ? ".mp3" : ".mp4";
    const filename = baseTitle.toLowerCase().endsWith(ext) ? baseTitle : `${baseTitle}${ext}`;

    const items = [{
      url: target.url,
      filename: filename,
      auto_start: autoStart,
      referer: target.referer || window.location.href,
      origin: target.origin || window.location.origin,
      user_agent: target.userAgent || navigator.userAgent,
      cookies: target.cookies || ""
    }];

    sendBatchToPDM(items, autoStart);
  }

  function sendBatchToPDM(items, autoStart) {
    chrome.runtime.sendMessage({
      action: "batch_download_native",
      items: items
    }, (resp) => {
      if (resp && resp.status === "ok") {
        const count = items.length;
        if (autoStart) {
          showToast(`✓ Started downloading ${count} video(s) in PDM at maximum speed!`);
        } else {
          showToast(`⏳ Successfully added ${count} video(s) to PDM Queue!`);
        }

        overlays.forEach((overlay) => {
          const b = overlay.querySelector(".pdm-grab-button");
          if (b) {
            b.classList.add("pdm-btn-success");
            setTimeout(() => {
              b.classList.remove("pdm-btn-success");
            }, 3000);
          }
        });
      } else {
        const err = (resp && resp.error) || "Host connection failed. Reload extension & ensure PDM is running.";
        showToast(`❌ Connection Error: ${err}`);
      }
    });
  }

  function showToast(message) {
    const existing = document.getElementById("pdm-toast-banner");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.id = "pdm-toast-banner";
    toast.className = "pdm-toast-banner";
    toast.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="#22c55e">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
      </svg>
      <span>${escapeHtml(message)}</span>
    `;

    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.4s ease";
      setTimeout(() => toast.remove(), 400);
    }, 4000);
  }

  function getCleanTitle(videoEl = null) {
    let title = "";
    if (videoEl) {
      const container = videoEl.closest('[role="article"], [data-pagelet], article, .post');
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

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return "";
    const units = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) {
      bytes /= 1024;
      i++;
    }
    return `${bytes.toFixed(1)} ${units[i]}`;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // 7. Intercept clicks on download links & buttons (IDM-style link interception)
  const DOWNLOAD_EXTENSIONS = new Set([
    "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso", "img", "bin",
    "exe", "msi", "dmg", "pkg", "deb", "rpm", "apk",
    "mp4", "mkv", "avi", "mov", "flv", "webm", "wmv", "m4v",
    "mp3", "wav", "flac", "aac", "ogg", "m4a", "wma",
    "pdf", "epub", "mobi", "docx", "xlsx", "pptx"
  ]);

  function getUrlExtension(urlString) {
    try {
      const url = new URL(urlString, window.location.href);
      if (!["http:", "https:"].includes(url.protocol)) return null;
      const pathname = url.pathname.split("/").pop() || "";
      const dotIndex = pathname.lastIndexOf(".");
      if (dotIndex === -1) return null;
      return pathname.substring(dotIndex + 1).toLowerCase();
    } catch (e) {
      return null;
    }
  }

  document.addEventListener(
    "click",
    (e) => {
      // Hold Alt or Ctrl to bypass PDM interception (standard IDM bypass shortcut)
      if (e.altKey || e.ctrlKey || e.button !== 0) return;

      const link = e.target.closest("a, button, [role='button']");
      if (!link) return;

      let url = link.href || link.getAttribute("data-url") || link.getAttribute("data-href");
      if (!url && link.tagName === "BUTTON") {
        const onclickAttr = link.getAttribute("onclick") || "";
        const m = onclickAttr.match(/https?:\/\/[^\s'"\)]+/);
        if (m) url = m[0];
      }
      if (!url || (!url.startsWith("http://") && !url.startsWith("https://"))) return;

      const ext = getUrlExtension(url);
      const hasDownloadAttr = link.hasAttribute && link.hasAttribute("download");
      const isKnownExt = ext && DOWNLOAD_EXTENSIONS.has(ext);
      const text = (link.innerText || "").trim().toLowerCase();
      const isDownloadText = text === "download" || text.includes("download") || (link.title && link.title.toLowerCase().includes("download"));
      const classText = (link.className && typeof link.className === "string") ? link.className.toLowerCase() : "";
      const isDownloadClass = classText.includes("download") || classText.includes("btn-download");

      if (isKnownExt || hasDownloadAttr || isDownloadText || isDownloadClass) {
        e.preventDefault();
        e.stopPropagation();

        let title = "";
        const row = link.closest("tr, li, [class*='row'], [class*='item'], [class*='episode'], [class*='card']");
        if (row) {
          const candidateEls = row.querySelectorAll("td, th, span, div, strong, b, h1, h2, h3, h4, h5, h6, p");
          for (const cel of candidateEls) {
            if (cel !== link && !cel.contains(link) && !link.contains(cel)) {
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
          title = (link.getAttribute && link.getAttribute("download")) || link.title || link.innerText.trim() || url.split("/").pop() || "download";
        }
        title = title.split("\n")[0].trim().replace(/[<>:"/\\|?*]/g, "_").substring(0, 100);
        if (title && !title.match(/\.[a-zA-Z0-9]{2,5}$/)) {
          if (ext) {
            title = `${title}.${ext}`;
          } else if (/(s\d+|e\d+|episode|season|king|movie|video|1080p|720p|480p)/i.test(title)) {
            title = `${title}.mp4`;
          }
        }

        chrome.runtime.sendMessage(
          {
            action: "download_via_native",
            url: url,
            filename: title,
            auto_start: true,
            referer: window.location.href,
            origin: window.location.origin,
            user_agent: navigator.userAgent
          },
          () => {
            showToast("⚡ Sent download to Personal Download Manager!");
          }
        );
      }
    },
    true
  );

  // 8. Batch Link Scanner & Grabber Dialog (IDM "Download all with IDM" feature)
  function scanPageDownloadLinks(onlySelection = false) {
    const links = [];
    const seenUrls = new Set();

    let anchorList = [];
    if (onlySelection) {
      const selection = window.getSelection();
      if (selection && selection.rangeCount > 0) {
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
      const hasDownloadAttr = a.hasAttribute && a.hasAttribute("download");
      const text = (a.innerText || "").trim().toLowerCase();
      const isDownloadText = text === "download" || text.includes("download") || (a.title && a.title.toLowerCase().includes("download"));
      const classText = (a.className && typeof a.className === "string") ? a.className.toLowerCase() : "";
      const isDownloadClass = classText.includes("download") || classText.includes("btn-download");

      if (isKnownExt || hasDownloadAttr || isDownloadText || isDownloadClass) {
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
          } else {
            filename = `${filename}.bin`;
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

  function openBatchModal(onlySelection = false) {
    const existing = document.querySelector(".pdm-modal-backdrop");
    if (existing) existing.remove();

    const links = scanPageDownloadLinks(onlySelection);
    if (links.length === 0) {
      showToast("No downloadable links found on this page.");
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
        referer: window.location.href,
        origin: window.location.origin,
        user_agent: navigator.userAgent
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

  document.addEventListener("play", (e) => {
    if (e.target && (e.target.tagName === "VIDEO" || e.target.tagName === "AUDIO")) {
      attachOverlay(e.target);
    }
  }, true);

  if (document.readyState === "complete") {
    setTimeout(() => {
      scanMediaElements();
      updateBatchPill();
    }, 800);
  } else {
    window.addEventListener("load", () => {
      setTimeout(() => {
        scanMediaElements();
        updateBatchPill();
      }, 800);
    });
  }
})();
