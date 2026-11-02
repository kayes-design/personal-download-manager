// Personal Download Manager (PDM) Extension Background Service Worker
// High-performance media sniffer, dynamic stream interceptor & native messaging bridge

// 1. Setup Context Menu on installation
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "pdm-download-link",
    title: "Download with PDM",
    contexts: ["link", "image", "video", "audio"]
  });

  chrome.contextMenus.create({
    id: "pdm-download-all",
    title: "Download all links with PDM",
    contexts: ["page"]
  });

  chrome.contextMenus.create({
    id: "pdm-download-selection",
    title: "Download selected links with PDM",
    contexts: ["selection"]
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "pdm-download-link") {
    const targetUrl = info.linkUrl || info.srcUrl;
    if (targetUrl) {
      sendToPDM(targetUrl, "", true, tab ? tab.url : "", tab ? tab.id : null);
    }
  } else if (info.menuItemId === "pdm-download-all" || info.menuItemId === "pdm-download-selection") {
    if (tab && tab.id) {
      chrome.tabs.sendMessage(tab.id, {
        action: "OPEN_BATCH_MODAL",
        onlySelection: info.menuItemId === "pdm-download-selection"
      }).catch(() => {});
    }
  }
});

// 2. Comprehensive File Type Interception Engine (All 150+ Extensions + Binary MIME Detection)
const sessionStartTime = Date.now();
const interceptedDownloadIds = new Set();

const INTERCEPTABLE_EXTENSIONS = new Set([
  // Compressed & Archives
  "zip", "rar", "7z", "tar", "gz", "gzip", "bz2", "bzip2", "xz", "z", "7zip",
  "tgz", "tbz2", "txz", "cab", "arj", "lzh", "ace", "iso", "img", "bin", "cue",
  "nrg", "vhd", "vhdx", "vmdk", "dmg", "pkg", "wim", "part1", "r00", "z01",

  // Executables & Installers
  "exe", "msi", "msix", "bat", "cmd", "ps1", "deb", "rpm", "apk", "xapk", "aab",
  "appx", "appxbundle", "run", "appimage", "jar", "war", "crx", "xpi",

  // Video & Streams
  "mp4", "mkv", "avi", "mov", "flv", "webm", "wmv", "m4v", "ts", "mts", "m2ts",
  "3gp", "3g2", "ogv", "vob", "divx", "xvid", "rm", "rmvb", "asf", "m3u8", "mpd",

  // Audio & Music
  "mp3", "wav", "flac", "aac", "ogg", "m4a", "opus", "wma", "alac", "aiff", "aif",
  "mid", "midi", "mka", "ape", "ra",

  // Documents, Spreadsheets & eBooks
  "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv", "tsv", "txt", "rtf",
  "epub", "mobi", "azw", "azw3", "djvu", "odt", "ods", "odp", "pages", "numbers", "key",

  // High-Res Images & Creative Design
  "png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "tiff", "tif", "ico",
  "psd", "ai", "eps", "raw", "cr2", "nef", "heic", "avif",

  // Database & Developer Artifacts
  "sql", "sqlite", "sqlite3", "db", "mdb", "accdb", "json", "xml", "yaml", "yml",
  "whl", "torrent"
]);

function getUrlExt(str) {
  if (!str) return null;
  try {
    const clean = str.split("?")[0].split("#")[0].trim();
    const dot = clean.lastIndexOf(".");
    if (dot === -1) return null;
    return clean.substring(dot + 1).toLowerCase();
  } catch (e) {
    return null;
  }
}

function shouldIntercept(item) {
  const url = item.finalUrl || item.url || "";
  if (!url.startsWith("http://") && !url.startsWith("https://")) return false;

  const lowerUrl = url.toLowerCase();
  if (
    lowerUrl.includes("/backend-api/") ||
    lowerUrl.includes("/api/") ||
    lowerUrl.includes("localhost") ||
    lowerUrl.includes("blob:") ||
    lowerUrl.includes("data:")
  ) {
    return false;
  }

  if (item.state && item.state !== "in_progress") {
    return false;
  }

  if (item.startTime) {
    const itemTime = new Date(item.startTime).getTime();
    if (itemTime < sessionStartTime - 3000) {
      return false;
    }
  }

  const mime = (item.mime || "").toLowerCase();

  // Never intercept HTML pages or web scripts
  if (
    mime === "text/html" ||
    mime === "text/css" ||
    mime === "text/javascript" ||
    mime === "application/javascript" ||
    mime === "application/x-javascript"
  ) {
    return false;
  }

  const ext = getUrlExt(item.filename) || getUrlExt(url);
  if (ext && INTERCEPTABLE_EXTENSIONS.has(ext)) {
    return true;
  }

  // Intercept any binary attachment or octet stream
  if (
    mime.startsWith("application/octet-stream") ||
    mime.startsWith("application/x-zip") ||
    mime.startsWith("application/x-rar") ||
    mime.startsWith("application/x-7z") ||
    mime.startsWith("application/x-msdownload") ||
    mime.startsWith("application/pdf") ||
    mime.startsWith("application/vnd.android") ||
    mime.startsWith("application/zip")
  ) {
    return true;
  }

  // If file size is substantial (> 2MB) and Chrome decided it is a file download
  if (item.fileSize && item.fileSize > 2097152) {
    return true;
  }

  return false;
}

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  if (shouldIntercept(item)) {
    if (!interceptedDownloadIds.has(item.id)) {
      interceptedDownloadIds.add(item.id);
      const url = item.finalUrl || item.url;
      const referer = item.referrer || "";
      const filename = item.filename || "";

      // Find the active tab that initiated this download
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        const activeTabId = tabs && tabs.length > 0 ? tabs[0].id : null;
        chrome.downloads.cancel(item.id, () => {
          chrome.downloads.erase({ id: item.id });
          sendToPDM(url, filename, true, referer, activeTabId);
        });
      });
      return false;
    }
  }
  suggest();
});

// 3. Cache exact request headers (User-Agent, Referer, Origin, Cookie) per URL
const requestMetadataCache = new Map();

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    let ua = "";
    let ref = "";
    let origin = "";
    let cookie = "";

    if (details.requestHeaders) {
      for (const h of details.requestHeaders) {
        const n = h.name.toLowerCase();
        if (n === "user-agent") ua = h.value;
        else if (n === "referer") ref = h.value;
        else if (n === "origin") origin = h.value;
        else if (n === "cookie") cookie = h.value;
      }
    }

    requestMetadataCache.set(details.url, {
      userAgent: ua,
      referer: ref,
      origin: origin,
      cookie: cookie,
      time: Date.now()
    });

    if (requestMetadataCache.size > 800) {
      const now = Date.now();
      for (const [k, v] of requestMetadataCache.entries()) {
        if (now - v.time > 1800000) {
          requestMetadataCache.delete(k);
        }
      }
    }
  },
  { urls: ["http://*/*", "https://*/*"] },
  ["requestHeaders", "extraHeaders"]
);

// 4. Enhanced Media & Stream Sniffer (HLS, DASH, Direct Video/Audio)
chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    if (!details.tabId || details.tabId < 0) return;

    const lowerUrl = details.url.toLowerCase();

    const isManifest = lowerUrl.includes(".m3u8") ||
                       lowerUrl.includes(".mpd") ||
                       lowerUrl.includes("dashplaylist") ||
                       lowerUrl.includes("hlsplaylist") ||
                       lowerUrl.includes("/manifest");

    // Filter out tiny transport segments unless manifest
    const isNumberedSegment = /\.m4s(\?|$)/i.test(lowerUrl) ||
                              /\b(seg|segment|chunk|frag|piece)[-_]?\d+\.ts(\?|$)/i.test(lowerUrl) ||
                              /\/\d+\.ts(\?|$)/i.test(lowerUrl) ||
                              lowerUrl.includes("/segment/") ||
                              lowerUrl.includes("/chunk/") ||
                              lowerUrl.includes("bytestart=") ||
                              lowerUrl.includes("byteend=") ||
                              lowerUrl.includes("&range=") ||
                              lowerUrl.includes("?range=") ||
                              lowerUrl.includes("&sq=") ||
                              lowerUrl.includes("?sq=") ||
                              lowerUrl.includes("initsegment") ||
                              lowerUrl.includes("initialization") ||
                              lowerUrl.includes("storyboard") ||
                              lowerUrl.includes("live-preview");

    if (isNumberedSegment && !isManifest) {
      return;
    }

    const headers = details.responseHeaders || [];
    let contentType = "";
    let contentLength = 0;
    let totalRangeLength = 0;

    for (const h of headers) {
      const name = h.name.toLowerCase();
      if (name === "content-type") {
        contentType = (h.value || "").toLowerCase();
      } else if (name === "content-length") {
        contentLength = parseInt(h.value || "0", 10);
      } else if (name === "content-range") {
        const match = (h.value || "").match(/\/(\d+)/);
        if (match) {
          totalRangeLength = parseInt(match[1], 10);
        }
      }
    }

    const exactOrChunkSize = totalRangeLength > 0 ? totalRangeLength : contentLength;
    if (!isManifest && exactOrChunkSize > 0 && exactOrChunkSize < 250000) {
      return;
    }

    const isVideoType = contentType.startsWith("video/") ||
                        contentType.startsWith("audio/") ||
                        contentType.includes("vnd.apple.mpegurl") ||
                        contentType.includes("x-mpegurl") ||
                        contentType.includes("dash+xml");

    const hasVideoExt = lowerUrl.includes(".mp4") ||
                        lowerUrl.includes(".mkv") ||
                        lowerUrl.includes(".webm") ||
                        lowerUrl.includes(".mov") ||
                        lowerUrl.includes(".flv") ||
                        lowerUrl.includes(".avi") ||
                        lowerUrl.includes(".m4v") ||
                        lowerUrl.includes("videoplayback") ||
                        lowerUrl.includes("fbcdn.net") ||
                        lowerUrl.includes("googlevideo.com") ||
                        lowerUrl.includes("cdninstagram.com");

    const isMedia = isManifest || isVideoType || hasVideoExt;

    if (isMedia && (isManifest || exactOrChunkSize > 50000 || !exactOrChunkSize)) {
      const resInfo = getStreamResolution(details.url, contentType);
      const reqMeta = requestMetadataCache.get(details.url) || {};

      const referer = reqMeta.referer || details.initiator || details.documentUrl || "";
      const origin = reqMeta.origin || "";
      const userAgent = reqMeta.userAgent || navigator.userAgent;
      const cookies = reqMeta.cookie || "";

      const mediaPayload = {
        type: "PDM_MEDIA_DETECTED",
        data: {
          url: details.url,
          type: contentType.split(";")[0] || "video/mp4",
          size: exactOrChunkSize,
          label: resInfo ? resInfo.full : getStreamLabel(details.url, contentType),
          resolution: resInfo ? resInfo.full : "",
          resTag: resInfo ? resInfo.tag : "",
          referer: referer,
          origin: origin,
          userAgent: userAgent,
          cookies: cookies
        }
      };

      if (details.frameId > 0) {
        chrome.tabs.sendMessage(details.tabId, mediaPayload, { frameId: details.frameId }).catch(() => {});
      }
      chrome.tabs.sendMessage(details.tabId, mediaPayload, { frameId: 0 }).catch(() => {});
    }
  },
  { urls: ["http://*/*", "https://*/*"], types: ["media", "xmlhttprequest", "other"] },
  ["responseHeaders"]
);

// 5. Notify tabs when user navigates
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url || (changeInfo.status === "loading" && tab.url)) {
    chrome.tabs.sendMessage(tabId, {
      type: "PDM_PAGE_NAVIGATED",
      url: changeInfo.url || tab.url
    }).catch(() => {});
  }
});

function getStreamResolution(url, contentType) {
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
  if (contentType.startsWith("audio/") || lower.includes("audio") || lower.includes("dash_audio") || lower.includes("itag=140") || lower.includes("itag=251")) {
    return { tag: "AUDIO", full: "Audio Track" };
  }
  return null;
}

function getStreamLabel(url, contentType) {
  const res = getStreamResolution(url, contentType);
  if (res) return res.full;
  if (contentType.includes("mp4") || url.includes(".mp4")) return "MP4 Video";
  if (contentType.includes("webm") || url.includes(".webm")) return "WebM Video";
  if (contentType.includes("mpegurl") || url.includes(".m3u8")) return "HLS Stream (m3u8)";
  if (contentType.includes("dash+xml") || url.includes(".mpd")) return "DASH Stream (mpd)";
  if (contentType.startsWith("audio/")) return "Audio Stream";
  return "Video Stream";
}

// Helper to extract session cookies for URL
async function getCookiesForUrl(targetUrl) {
  try {
    if (!chrome.cookies || !targetUrl || !targetUrl.startsWith("http")) return "";
    const cookies = await chrome.cookies.getAll({ url: targetUrl });
    if (!cookies || cookies.length === 0) return "";
    return cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch (e) {
    return "";
  }
}

// 6. Native Messaging Communication & Card Hub Dispatcher
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "download_via_native") {
    (async () => {
      const cookies = message.cookies || (await getCookiesForUrl(message.url));
      const referer = message.referer || (sender.tab && sender.tab.url) || "";
      const origin = message.origin || "";
      const userAgent = message.user_agent || navigator.userAgent;
      const proxy = message.proxy || (await getActiveBrowserProxy());

      chrome.runtime.sendNativeMessage(
        "com.pdm.native_host",
        {
          action: "download",
          url: message.url,
          filename: message.filename || "",
          auto_start: message.auto_start !== false,
          cookies: cookies,
          referer: referer,
          user_agent: userAgent,
          origin: origin,
          proxy: proxy
        },
        (response) => {
          if (chrome.runtime.lastError) {
            console.warn("PDM Host Communication Error:", chrome.runtime.lastError.message);
            // VnA-style clipboard fallback if native messaging fails
            try {
              if (sender.tab && sender.tab.id) {
                chrome.scripting.executeScript({
                  target: { tabId: sender.tab.id },
                  func: (u) => { navigator.clipboard.writeText(u); },
                  args: [message.url]
                }).catch(() => {});
              }
            } catch (err) {}
            sendResponse({ status: "error", error: chrome.runtime.lastError.message, copiedToClipboard: true });
          } else {
            sendResponse({ status: "ok", data: response });
          }
        }
      );
    })();
    return true; // Keep channel open for async response
  } else if (message.action === "get_task_progress") {
    chrome.runtime.sendNativeMessage(
      "com.pdm.native_host",
      {
        action: "get_progress",
        task_id: message.task_id
      },
      (response) => {
        if (chrome.runtime.lastError) {
          sendResponse({ status: "error", error: chrome.runtime.lastError.message });
        } else {
          sendResponse({ status: "ok", data: response });
        }
      }
    );
    return true;
  } else if (message.action === "pause_task") {
    chrome.runtime.sendNativeMessage(
      "com.pdm.native_host",
      {
        action: "pause_task",
        task_id: message.task_id
      },
      (response) => {
        sendResponse(response || { status: "ok" });
      }
    );
    return true;
  } else if (message.action === "resume_task") {
    chrome.runtime.sendNativeMessage(
      "com.pdm.native_host",
      {
        action: "resume_task",
        task_id: message.task_id
      },
      (response) => {
        sendResponse(response || { status: "ok" });
      }
    );
    return true;
  } else if (message.action === "cancel_task") {
    chrome.runtime.sendNativeMessage(
      "com.pdm.native_host",
      {
        action: "cancel_task",
        task_id: message.task_id
      },
      (response) => {
        sendResponse(response || { status: "ok" });
      }
    );
    return true;
  } else if (message.action === "open_file") {
    chrome.runtime.sendNativeMessage(
      "com.pdm.native_host",
      {
        action: "open_file",
        task_id: message.task_id
      },
      (response) => {
        sendResponse(response || { status: "ok" });
      }
    );
    return true;
  } else if (message.action === "open_folder") {
    chrome.runtime.sendNativeMessage(
      "com.pdm.native_host",
      {
        action: "open_folder",
        task_id: message.task_id
      },
      (response) => {
        sendResponse(response || { status: "ok" });
      }
    );
    return true;
  } else if (message.action === "batch_download_native") {
    (async () => {
      const items = message.items || [];
      const defaultReferer = (sender.tab && sender.tab.url) || "";
      const defaultOrigin = sender.tab && sender.tab.url ? new URL(sender.tab.url).origin : "";
      const activeProxy = await getActiveBrowserProxy();

      for (const it of items) {
        if (!it.cookies && it.url) {
          it.cookies = await getCookiesForUrl(it.url);
        }
        if (!it.referer) {
          it.referer = defaultReferer;
        }
        if (!it.origin) {
          it.origin = defaultOrigin;
        }
        if (!it.user_agent) {
          it.user_agent = navigator.userAgent;
        }
        if (!it.proxy && activeProxy) {
          it.proxy = activeProxy;
        }
      }

      chrome.runtime.sendNativeMessage(
        "com.pdm.native_host",
        {
          action: "batch_download",
          items: items
        },
        (response) => {
          if (chrome.runtime.lastError) {
            console.warn("PDM Host Communication Error:", chrome.runtime.lastError.message);
            sendResponse({ status: "error", error: chrome.runtime.lastError.message });
          } else {
            sendResponse({ status: "ok", data: response });
          }
        }
      );
    })();
    return true;
  }
});

// 7. Inspect active browser proxy/VPN configuration
async function getActiveBrowserProxy() {
  return new Promise((resolve) => {
    if (!chrome.proxy || !chrome.proxy.settings) {
      resolve("");
      return;
    }
    try {
      chrome.proxy.settings.get({ incognito: false }, (config) => {
        try {
          if (config && config.value) {
            const rules = config.value.rules;
            if (rules) {
              const p = rules.singleProxy || rules.proxyForHttps || rules.proxyForHttp;
              if (p && p.host) {
                const scheme = p.scheme || "http";
                const port = p.port ? `:${p.port}` : "";
                resolve(`${scheme}://${p.host}${port}`);
                return;
              }
            }
          }
        } catch (e) {}
        resolve("");
      });
    } catch (err) {
      resolve("");
    }
  });
}

// 8. Send message via Native Messaging host to PDM desktop application
async function sendToPDM(url, filename, autoStart = true, referer = "", activeTabId = null) {
  const cookies = await getCookiesForUrl(url);
  const proxy = await getActiveBrowserProxy();
  let origin = "";
  try {
    if (referer && referer.startsWith("http")) {
      origin = new URL(referer).origin;
    }
  } catch (e) {}

  chrome.runtime.sendNativeMessage(
    "com.pdm.native_host",
    {
      action: "download",
      url: url,
      filename: filename,
      auto_start: autoStart,
      cookies: cookies,
      referer: referer,
      user_agent: navigator.userAgent,
      origin: origin,
      proxy: proxy
    },
    (response) => {
      if (chrome.runtime.lastError) {
        console.warn("PDM Host Communication Error:", chrome.runtime.lastError.message);
      } else {
        console.log("PDM Task Created Successfully:", response);
        // If an active tab is available, trigger the in-page active download HUD!
        if (activeTabId && response && response.task_ids && response.task_ids.length > 0) {
          chrome.tabs.sendMessage(activeTabId, {
            type: "PDM_ACTIVE_DOWNLOAD_STARTED",
            taskId: response.task_ids[0],
            title: filename || url,
            url: url
          }).catch(() => {});
        }
      }
    }
  );
}
