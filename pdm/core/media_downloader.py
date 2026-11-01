"""Universal media stream downloader for all websites (YouTube, Reddit, Facebook, Instagram,
TikTok, Twitter/X, Twitch, Vimeo, Bilibili, Dailymotion, Rumble, Kick, SoundCloud, HLS, DASH, and 1,700+ platforms).
Automatically downloads separate video and audio tracks and merges them via FFmpeg.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse
import imageio_ffmpeg
import yt_dlp
import yt_dlp.extractor

# Comprehensive registry of popular video, audio, and streaming domains
POPULAR_MEDIA_DOMAINS: Set[str] = {
    # Video & Social
    "youtube.com", "youtu.be",
    "reddit.com", "redd.it", "v.redd.it", "packaged-media.redd.it",
    "facebook.com", "fb.watch", "fb.com", "m.facebook.com", "fbcdn.net",
    "instagram.com", "instagr.am", "cdninstagram.com",
    "tiktok.com", "tiktokcdn.com", "byteoversea.com",
    "twitter.com", "x.com", "t.co", "twimg.com",
    "twitch.tv", "kick.com",
    "vimeo.com", "vimeocdn.com",
    "dailymotion.com", "dai.ly",
    "bilibili.com", "b23.tv",
    "rumble.com",
    "threads.net",
    "pinterest.com", "pin.it",
    "linkedin.com",
    "streamable.com",
    "imgur.com",
    "vk.com",
    "ok.ru",
    "archive.org",
    "odysee.com",
    "bitchute.com",
    "9gag.com",
    "weibo.com",
    # Audio & Podcasts
    "soundcloud.com",
    "bandcamp.com",
    "mixcloud.com",
    "anchor.fm",
    "podcasts.apple.com",
}

# Manifest & Streaming stream indicators
STREAM_INDICATORS = (
    ".m3u8", ".mpd", "dashplaylist", "hlsplaylist",
    "videoplayback", "/manifest", "/playlist", ".ism/manifest",
    "googlevideo.com", "fbcdn.net", "tiktokcdn.com", "byteoversea.com",
    "cdninstagram.com", "twimg.com", "vimeocdn.com"
)

# Cache yt-dlp extractors for fast offline URL matching (excluding generic)
_CACHED_EXTRACTORS = None
_EXTRACTORS_LOCK = threading.Lock()


def _get_extractors():
    global _CACHED_EXTRACTORS
    if _CACHED_EXTRACTORS is None:
        with _EXTRACTORS_LOCK:
            if _CACHED_EXTRACTORS is None:
                try:
                    _CACHED_EXTRACTORS = [
                        e for e in yt_dlp.extractor.gen_extractors()
                        if getattr(e, "IE_NAME", "") != "generic"
                    ]
                except Exception:
                    _CACHED_EXTRACTORS = []
    return _CACHED_EXTRACTORS


def is_media_stream_url(url: str) -> bool:
    """Return True if URL is from any known video streaming platform, DASH/HLS manifest, or supported extractor."""
    if not url:
        return False
    lower = url.lower()

    # 1. Direct stream manifests
    if any(ind in lower for ind in STREAM_INDICATORS):
        return True

    # 2. Fast check against common popular media domains
    if any(domain in lower for domain in POPULAR_MEDIA_DOMAINS):
        return True

    # 3. Match against yt-dlp's 1,750+ offline site extractors
    extractors = _get_extractors()
    for ie in extractors:
        try:
            if ie.suitable(url):
                return True
        except Exception:
            pass

    return False


def normalize_media_url(url: str) -> str:
    """Normalize stream-specific URLs (e.g. v.redd.it DASH fragments) to master resource URLs."""
    if not url:
        return ""
    if "v.redd.it" in url:
        clean = url.split("?")[0]
        parts = clean.split("/")
        if parts[-1].startswith("DASH_") or parts[-1].startswith("HLS") or parts[-1] in ("audio", "DASHPlaylist.mpd"):
            return "/".join(parts[:-1])
    return url


def get_ffmpeg_path() -> Optional[str]:
    """Return path to bundled imageio-ffmpeg or system ffmpeg executable."""
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    return shutil.which("ffmpeg")


def ensure_h264_compatibility(file_path: str) -> str:
    """Ensure downloaded MP4 uses standard H.264 video codec so standard Windows Media Player can play it without codec errors."""
    if not file_path or not os.path.exists(file_path):
        return file_path
    if not file_path.lower().endswith((".mp4", ".mkv", ".webm")):
        return file_path

    ffmpeg_exe = get_ffmpeg_path()
    if not ffmpeg_exe or not os.path.exists(ffmpeg_exe):
        return file_path

    try:
        # Check header: if it has AV1 ('av01') or VP9 ('vp09'/'vp9'), transcode to standard H.264
        with open(file_path, "rb") as f:
            header_sample = f.read(8192)
        needs_transcode = b"av01" in header_sample or b"vp09" in header_sample or b"vp9" in header_sample
        if not needs_transcode:
            return file_path

        dest_mp4 = os.path.splitext(file_path)[0] + ".mp4"
        temp_out = file_path + ".h264_temp.mp4"
        cmd = [
            ffmpeg_exe, "-y", "-i", file_path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "copy",
            temp_out
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        if res.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
            if file_path != dest_mp4 and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            os.replace(temp_out, dest_mp4)
            return dest_mp4
    except Exception:
        pass
    return file_path


def create_temp_netscape_cookiefile(cookies_str: str, url: str) -> Optional[str]:
    """Format raw cookie string into temporary Netscape cookiefile for yt-dlp authenticated sessions."""
    if not cookies_str:
        return None
    try:
        host = urlparse(url).hostname or "youtube.com"
        domains = set()
        parts = host.split(".")
        if len(parts) >= 2:
            domains.add(f".{parts[-2]}.{parts[-1]}")
        if not host.startswith("."):
            domains.add(f".{host}")
        domains.add(host)

        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", prefix="pdm_cookies_", delete=False)
        tf.write("# Netscape HTTP Cookie File\n")
        pairs = cookies_str.split(";")
        for p in pairs:
            p = p.strip()
            if "=" in p:
                k, v = p.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k and v:
                    for d in domains:
                        subdomains = "TRUE" if d.startswith(".") else "FALSE"
                        tf.write(f"{d}\t{subdomains}\t/\tTRUE\t2147483647\t{k}\t{v}\n")
        tf.close()
        return tf.name
    except Exception:
        return None


class MediaStreamDownloader:
    """Universal media downloader for all video/audio websites with automatic stream muxing."""

    def __init__(self):
        self.ffmpeg_path = get_ffmpeg_path()

    def download(
        self,
        url: str,
        destination_path: str,
        cookies: str = "",
        referer: str = "",
        user_agent: str = "",
        origin: str = "",
        progress_callback: Optional[Callable[[int, int, float, Optional[int]], None]] = None,
        is_stopped_callback: Optional[Callable[[], bool]] = None,
        resolution_callback: Optional[Callable[[str], None]] = None,
        proxy: Optional[str] = None,
    ) -> str:
        """Download video + audio from any site and merge into a single playable MP4 file.

        Args:
            url: The media URL (YouTube, Reddit, Facebook, TikTok, Instagram, Twitter, HLS, DASH, etc.)
            destination_path: Target filepath (e.g. C:/Users/.../video.mp4)
            cookies: Browser session cookies
            referer: HTTP referer header
            user_agent: Browser User-Agent header
            origin: HTTP origin header
            progress_callback: (downloaded_bytes, total_bytes, speed_bps, eta_seconds)
            is_stopped_callback: Function returning True if task was paused/canceled
            resolution_callback: Callback when resolution is detected

        Returns:
            Absolute path to final completed file.
        """
        target_url = normalize_media_url(url)
        dest_dir = os.path.dirname(os.path.abspath(destination_path))
        os.makedirs(dest_dir, exist_ok=True)

        # Check if resolution/format was requested via URL fragment e.g. #res=720p or #res=audio or #res=sub
        res_tag = None
        if "#res=" in target_url:
            parts = target_url.split("#res=")
            target_url = parts[0]
            res_tag = parts[1].split("&")[0].lower()

        is_sub_only = res_tag in ("sub", "subs", "subtitle", "subtitles")

        dest_name, dest_ext = os.path.splitext(os.path.basename(destination_path))
        if not dest_ext:
            if is_sub_only:
                dest_ext = ".srt"
            elif res_tag == "audio":
                dest_ext = ".m4a"
            else:
                dest_ext = ".mp4"

        # If dest_name is generic or placeholder, let yt-dlp name it with the video's real title
        generic_names = {"download", "watch", "video", "index", "media", "bin", "stream", "playlist"}
        use_real_title = dest_name.lower() in generic_names or not dest_name

        if use_real_title:
            out_template = os.path.join(dest_dir, "%(title).200B.%(ext)s")
        else:
            out_template = os.path.join(dest_dir, f"{dest_name}.%(ext)s")

        def hook(d):
            if is_stopped_callback and is_stopped_callback():
                raise InterruptedError("Download paused or canceled by user")

            status = d.get("status")
            if status == "downloading":
                downloaded = d.get("downloaded_bytes") or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                speed = d.get("speed") or 0.0
                eta = d.get("eta")
                if progress_callback:
                    progress_callback(int(downloaded), int(total), float(speed), int(eta) if eta else None)
            elif status == "finished":
                total = d.get("total_bytes") or d.get("downloaded_bytes") or 0
                if progress_callback:
                    progress_callback(int(total), int(total), 0.0, 0)

        ua = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

        is_fb = "facebook.com" in target_url.lower() or "fb.watch" in target_url.lower()

        format_selector = "bestvideo[vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc]+bestaudio/bestvideo+bestaudio/best"
        merge_fmt = "mp4"

        if is_sub_only:
            format_selector = "bestaudio/best"
            merge_fmt = None
        elif res_tag == "audio":
            format_selector = "bestaudio[ext=m4a]/bestaudio/best"
            merge_fmt = "m4a"
        elif res_tag == "360p":
            format_selector = "bestvideo[height<=360][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]"
        elif res_tag == "480p":
            format_selector = "bestvideo[height<=480][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]"
        elif res_tag == "720p":
            format_selector = "bestvideo[height<=720][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]"
        elif res_tag in ("1080p", "1080"):
            format_selector = "bestvideo[height<=1080][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]"

        ydl_opts = {
            "format": format_selector,
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "noplaylist": True,
            "extractor_args": {
                "youtubetab": ["skip=authcheck"],
                "youtube": ["skip=authcheck"],
            },
            "progress_hooks": [hook],
        }

        if merge_fmt:
            ydl_opts["merge_output_format"] = merge_fmt

        if is_sub_only:
            ydl_opts["writesubtitles"] = True
            ydl_opts["writeautomaticsub"] = True
            ydl_opts["subtitlesformat"] = "srt/vtt/best"
            ydl_opts["skip_download"] = True
        else:
            ydl_opts["writesubtitles"] = True
            ydl_opts["writeautomaticsub"] = True
            ydl_opts["subtitleslangs"] = ["en", "bn", "all"]
            ydl_opts["embedsubtitles"] = True

        if not is_fb:
            ydl_opts["http_headers"] = {
                "User-Agent": ua,
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
            }

        cookie_file = create_temp_netscape_cookiefile(cookies, target_url) if cookies else None
        if cookie_file and os.path.exists(cookie_file):
            ydl_opts["cookiefile"] = cookie_file

        if referer:
            ydl_opts["http_headers"] = ydl_opts.get("http_headers", {})
            ydl_opts["http_headers"]["Referer"] = referer
        if origin:
            ydl_opts["http_headers"] = ydl_opts.get("http_headers", {})
            ydl_opts["http_headers"]["Origin"] = origin
        if proxy:
            ydl_opts["proxy"] = proxy

        if self.ffmpeg_path:
            ydl_opts["ffmpeg_location"] = self.ffmpeg_path

        yt_error = None
        info = None
        ydl_final = None

        def _run_extraction(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(target_url, download=True), ydl

        try:
            info, ydl_final = _run_extraction(ydl_opts)
        except InterruptedError:
            raise
        except Exception as primary_err:
            yt_error = primary_err
            # Automatic fallback: If cookies/headers triggered error, retry completely clean anonymous
            try:
                fallback_opts = dict(ydl_opts)
                fallback_opts.pop("cookiefile", None)
                if "http_headers" in fallback_opts:
                    fallback_opts["http_headers"] = dict(fallback_opts["http_headers"])
                    fallback_opts["http_headers"].pop("Cookie", None)
                    fallback_opts["http_headers"].pop("User-Agent", None)
                info, ydl_final = _run_extraction(fallback_opts)
                yt_error = None
            except InterruptedError:
                raise
            except Exception as fb_err:
                yt_error = fb_err

        if info:
            width = info.get("width")
            height = info.get("height")
            format_note = info.get("format_note")
            res_str = ""
            if height:
                res_str = f"{height}p"
                if width:
                    res_str = f"{height}p ({width}x{height})"
            elif format_note:
                res_str = str(format_note)
            elif info.get("resolution"):
                res_str = str(info.get("resolution"))

            if res_str and resolution_callback:
                try:
                    resolution_callback(res_str)
                except Exception:
                    pass

            if ydl_final:
                try:
                    prepared = ydl_final.prepare_filename(info)
                    stem, _ = os.path.splitext(prepared)
                    mp4_candidate = f"{stem}.mp4"
                    if os.path.exists(mp4_candidate):
                        return ensure_h264_compatibility(mp4_candidate)
                    if os.path.exists(prepared):
                        return ensure_h264_compatibility(prepared)
                except Exception:
                    pass

        if cookie_file and os.path.exists(cookie_file):
            try:
                os.remove(cookie_file)
            except Exception:
                pass

        # If yt-dlp succeeded and output file exists
        expected_file = os.path.join(dest_dir, f"{dest_name}.mp4")
        if os.path.exists(expected_file):
            return ensure_h264_compatibility(expected_file)

        if os.path.exists(destination_path):
            return ensure_h264_compatibility(destination_path)

        for f in os.listdir(dest_dir):
            if (f.startswith(dest_name) or use_real_title) and not f.endswith((".part", ".ytdl")) and f.endswith((".mp4", ".mkv", ".webm")):
                return ensure_h264_compatibility(os.path.join(dest_dir, f))

        # Fallback to direct FFmpeg stream capture if yt-dlp failed or produced no file
        lower_url = target_url.lower()
        is_stream = any(ind in lower_url for ind in STREAM_INDICATORS) or lower_url.endswith((".mp4", ".mkv", ".webm", ".ts"))
        if is_stream:
            try:
                return self._download_via_ffmpeg(
                    url=target_url,
                    destination_path=destination_path,
                    user_agent=ua,
                    referer=referer,
                    origin=origin,
                    cookies=cookies,
                    progress_callback=progress_callback,
                    is_stopped_callback=is_stopped_callback,
                    resolution_callback=resolution_callback,
                    proxy=proxy,
                )
            except InterruptedError:
                raise
            except Exception as ffmpeg_err:
                raise RuntimeError(
                    f"Media stream download failed. yt-dlp error: {yt_error or 'No output file'}; "
                    f"FFmpeg error: {ffmpeg_err}"
                )

        if yt_error:
            raise yt_error
        raise FileNotFoundError(f"Media download finished but output file not found at {destination_path}")

    def _download_via_ffmpeg(
        self,
        url: str,
        destination_path: str,
        user_agent: str = "",
        referer: str = "",
        origin: str = "",
        cookies: str = "",
        progress_callback: Optional[Callable[[int, int, float, Optional[int]], None]] = None,
        is_stopped_callback: Optional[Callable[[], bool]] = None,
        resolution_callback: Optional[Callable[[str], None]] = None,
        proxy: Optional[str] = None,
    ) -> str:
        """Direct stream capture via bundled FFmpeg for HLS (.m3u8), DASH (.mpd), and resilient direct streams."""
        ffmpeg_exe = self.ffmpeg_path or get_ffmpeg_path()
        if not ffmpeg_exe or not os.path.exists(ffmpeg_exe):
            raise RuntimeError("FFmpeg executable not found for direct media stream capture.")

        dest_dir = os.path.dirname(os.path.abspath(destination_path))
        os.makedirs(dest_dir, exist_ok=True)
        dest_name, dest_ext = os.path.splitext(destination_path)
        if not dest_ext:
            destination_path = f"{destination_path}.mp4"

        headers_list = []
        ua = (user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36").replace("\r", "").replace("\n", "")
        headers_list.append(f"User-Agent: {ua}")
        if referer:
            headers_list.append(f"Referer: {referer.replace('\r', '').replace('\n', '')}")
        if origin:
            headers_list.append(f"Origin: {origin.replace('\r', '').replace('\n', '')}")
        if cookies:
            headers_list.append(f"Cookie: {cookies.replace('\r', '').replace('\n', '')}")
            headers_list.append(f"Cookie: {cookies}")

        headers_arg = "\r\n".join(headers_list) + "\r\n"

        cmd = [
            ffmpeg_exe,
            "-y",
        ]
        if proxy and proxy.startswith("http"):
            cmd.extend(["-http_proxy", proxy])
        cmd.extend([
            "-headers", headers_arg,
            "-i", url,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-movflags", "+faststart",
            destination_path,
        ])

        creation_flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
        )

        last_size = 0
        last_time = time.time()

        try:
            while proc.poll() is None:
                if is_stopped_callback and is_stopped_callback():
                    proc.terminate()
                    try:
                        proc.wait(timeout=2.0)
                    except Exception:
                        proc.kill()
                    raise InterruptedError("Download paused or canceled by user")

                time.sleep(0.5)
                if os.path.exists(destination_path):
                    current_size = os.path.getsize(destination_path)
                    now = time.time()
                    elapsed = max(0.1, now - last_time)
                    speed = (current_size - last_size) / elapsed
                    last_size = current_size
                    last_time = now
                    if progress_callback:
                        progress_callback(current_size, 0, speed, None)

            stdout, stderr = proc.communicate()
            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="ignore")
                raise RuntimeError(f"FFmpeg exit code {proc.returncode}: {err_text[-300:]}")

            if not os.path.exists(destination_path) or os.path.getsize(destination_path) < 1000:
                raise RuntimeError("FFmpeg stream capture completed but resulting output file is empty.")

            if resolution_callback:
                resolution_callback("Stream (HLS/Direct)")

            return destination_path
        finally:
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass


def is_playlist_url(url: str) -> bool:
    """Check if the provided URL is a playlist or album."""
    if not url:
        return False
    lower = url.lower()
    return (
        "list=" in lower
        or "/playlist" in lower
        or "/sets/" in lower
        or "/album" in lower
    )


def extract_playlist_entries(url: str, cookies: str = "", referer: str = "", max_items: int = 100) -> List[Dict[str, Any]]:
    """Extract list of media items from a playlist URL without downloading."""
    ydl_opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "playlist_items": f"1-{max_items}",
        "extractor_args": {
            "youtubetab": ["skip=authcheck"],
            "youtube": ["skip=authcheck"],
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    if cookies:
        ydl_opts["http_headers"]["Cookie"] = cookies
    if referer:
        ydl_opts["http_headers"]["Referer"] = referer

    entries: List[Dict[str, Any]] = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return entries

            raw_entries = info.get("entries")
            if raw_entries is None:
                raw_entries = [info]

            for idx, entry in enumerate(raw_entries):
                if not entry:
                    continue
                title = entry.get("title") or f"Item {idx + 1}"
                entry_url = entry.get("url") or entry.get("webpage_url") or url
                if not entry_url.startswith("http"):
                    # Relative YouTube ID
                    entry_id = entry.get("id") or entry.get("url")
                    if entry_id:
                        entry_url = f"https://www.youtube.com/watch?v={entry_id}"
                duration = entry.get("duration") or 0
                entries.append({
                    "index": idx + 1,
                    "title": title,
                    "url": entry_url,
                    "duration": duration,
                    "id": entry.get("id", ""),
                })
    except Exception:
        pass

    return entries
