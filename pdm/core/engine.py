"""High-performance dynamic segmented download engine."""

import mimetypes
import os
import re
import shutil
import threading
import time
import urllib.parse
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional
import httpx

MIME_EXTENSION_MAP = {
    "video/mp4": ".mp4",
    "video/x-matroska": ".mkv",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/x-flv": ".flv",
    "video/mp2t": ".ts",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/x-rar-compressed": ".rar",
    "application/x-7z-compressed": ".7z",
    "application/x-tar": ".tar",
    "application/gzip": ".gz",
    "application/pdf": ".pdf",
    "application/vnd.android.package-archive": ".apk",
    "application/x-msdownload": ".exe",
}

from pdm.core.limiter import SpeedLimiter
from pdm.core.media_downloader import MediaStreamDownloader, is_media_stream_url
from pdm.core.security import (
    extract_filename_from_url,
    parse_content_disposition,
    resolve_safe_filepath,
    sanitize_filename,
    validate_url,
)
from pdm.core.staging import (
    cleanup_task_staging_dir,
    get_staging_path,
    get_task_staging_dir,
)
from pdm.storage.db import DatabaseManager

MIN_CHUNK_SIZE = 128 * 1024  # 128 KB minimum chunk size for multi-connection

DEFAULT_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}


class DownloadStatus(str, Enum):
    QUEUED = "Queued"
    DOWNLOADING = "Downloading"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    ERROR = "Error"
    CANCELED = "Canceled"


class RangeNotHonoredError(ConnectionError):
    """Raised when a server returns bytes that do not match a requested range."""


@dataclass
class SegmentInfo:
    segment_id: int
    segment_index: int
    start_byte: int
    end_byte: int
    downloaded_bytes: int = 0
    temp_filepath: str = ""
    status: str = "Pending"
    worker_id: Optional[int] = None

    @property
    def expected_bytes(self) -> int:
        return max(0, self.end_byte - self.start_byte + 1)

    @property
    def remaining_bytes(self) -> int:
        return max(0, self.expected_bytes - self.downloaded_bytes)

    @property
    def current_byte(self) -> int:
        return self.start_byte + self.downloaded_bytes


class DownloadTask:
    """Manages downloading a single file, orchestrating workers and segmented ranges."""

    def __init__(
        self,
        task_id: int,
        url: str,
        destination_path: str,
        filename: str,
        db: DatabaseManager,
        connections_count: int = 4,
        speed_limiter: Optional[SpeedLimiter] = None,
        progress_callback: Optional[Callable[["DownloadTask"], None]] = None,
        status_callback: Optional[Callable[["DownloadTask", DownloadStatus], None]] = None,
        cookies: str = "",
        referer: str = "",
        user_agent: str = "",
        origin: str = "",
        proxy: Optional[str] = None,
        category: str = "Other",
        cookie_jar: str = ""
    ):
        self.task_id = task_id
        self.url = url
        self.destination_path = destination_path
        self.filename = filename
        self.db = db
        self.connections_count = max(1, min(connections_count, 32))
        self.speed_limiter = speed_limiter or SpeedLimiter(0)
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        self.cookies = cookies
        self.referer = referer
        self.user_agent = user_agent
        self.origin = origin
        self.proxy = proxy or None
        self.category = category
        self.cookie_jar = cookie_jar

        self.status = DownloadStatus.QUEUED
        self.total_bytes: int = -1
        self.downloaded_bytes: int = 0
        self.etag: Optional[str] = None
        self.last_modified: Optional[str] = None
        self.supports_range: bool = False
        self.error_message: Optional[str] = None

        # Speed and ETA metrics
        self.current_speed: float = 0.0  # bytes/sec
        self.eta_seconds: Optional[int] = None
        self._speed_window_bytes = 0
        self._speed_window_time = time.monotonic()

        # Threading & Control
        self._stop_event = threading.Event()
        self._segments_lock = threading.Lock()
        self.segments: List[SegmentInfo] = []
        self._workers: List[threading.Thread] = []
        self._worker_errors: List[Exception] = []
        self._last_db_checkpoint = time.monotonic()

    def stop(self):
        """Signal all workers to pause/stop."""
        self._stop_event.set()

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def run_sync(self):
        """Run the download synchronously (invoked inside worker thread)."""
        self._stop_event.clear()
        self._set_status(DownloadStatus.DOWNLOADING)

        # Guard against accidental homepage root downloads
        parsed = urllib.parse.urlparse(self.url)
        if parsed.netloc and (not parsed.path or parsed.path == "/") and not parsed.query:
            if any(dom in parsed.netloc.lower() for dom in ("facebook.com", "fb.watch", "youtube.com", "instagram.com", "tiktok.com", "twitter.com", "x.com")):
                err_msg = (
                    f"The link '{self.url}' is a website homepage, not a video stream. "
                    "Please navigate to the specific video/reel page, or click Download on the video player."
                )
                self.error_message = err_msg
                self._set_status(DownloadStatus.ERROR)
                raise ValueError(err_msg)

        # 0. Check if URL is a media stream (Reddit, YouTube, M3U8, DASH, etc.)
        if is_media_stream_url(self.url):
            try:
                self._download_stream()
                return
            except Exception as stream_err:
                if self.is_stopped():
                    self._set_status(DownloadStatus.PAUSED)
                    return
                # If stream is an M3U8/MPD or explicit video manifest, DO NOT fallback to raw HTTP
                # because downloading a 2KB text playlist into a fake .mp4 file creates broken files
                if is_media_stream_url(self.url):
                    self.error_message = f"Failed to capture media stream: {stream_err}"
                    self._set_status(DownloadStatus.ERROR)
                    raise

                # Otherwise, reset error state and proceed to standard segmented download as fallback
                self.error_message = None
                self._set_status(DownloadStatus.DOWNLOADING)

        try:
            # 1. Probe server for Range capabilities and file size
            self._probe_server()

            if self.is_stopped():
                self._set_status(DownloadStatus.PAUSED)
                return

            # If probed response is HTML or redirected to a media site, attempt stream extraction
            if getattr(self, "content_type", "").startswith("text/html") or is_media_stream_url(getattr(self, "final_url", "")):
                try:
                    self._download_stream()
                    return
                except Exception as stream_err:
                    if self.is_stopped():
                        self._set_status(DownloadStatus.PAUSED)
                        return

                    if is_media_stream_url(self.url):
                        self.error_message = f"Failed to capture media stream: {stream_err}"
                        self._set_status(DownloadStatus.ERROR)
                        raise

                    # Guard against saving an HTML error/login page as a media file ("download hoy but kisu nai")
                    ext = os.path.splitext(self.filename)[1].lower()
                    if getattr(self, "content_type", "").startswith("text/html") and ext in (
                        ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts", ".m4v",
                        ".zip", ".rar", ".7z", ".exe", ".iso", ".tar", ".gz"
                    ):
                        raise ValueError(
                            f"Server returned an HTML web page instead of a {ext} file. "
                            "The link may have expired, requires website authentication/cookies, or is protected by anti-bot checks."
                        )

            # 2. Setup or recover segments
            self._setup_segments()

            if self.is_stopped():
                self._set_status(DownloadStatus.PAUSED)
                return

            # 3. Launch download workers
            try:
                self._execute_workers()
            except RangeNotHonoredError:
                self._reset_segments()
                self.supports_range = False
                self.db.update_download_metadata(
                    self.task_id,
                    self.total_bytes,
                    self.etag,
                    self.last_modified,
                    False,
                )
                self._setup_segments()
                self._execute_workers()

            if self.is_stopped():
                self._set_status(DownloadStatus.PAUSED)
                return

            # 4. Check if all segments are 100% complete
            with self._segments_lock:
                all_done = all(s.remaining_bytes == 0 for s in self.segments)

            if all_done:
                # 5. Assemble segments into final destination file
                self._assemble_file()
                self._set_status(DownloadStatus.COMPLETED)
            else:
                if not self.is_stopped():
                    raise RuntimeError("Download stopped before all segments completed.")

        except Exception as e:
            self.error_message = str(e)
            self._set_status(DownloadStatus.ERROR)
            raise

    # ------------------- Private Implementation -------------------

    def _set_status(self, new_status: DownloadStatus):
        self.status = new_status
        self.db.set_download_status(self.task_id, new_status.value, self.error_message)
        if self.status_callback:
            try:
                self.status_callback(self, new_status)
            except Exception:
                pass

    def _download_stream(self):
        """Download streaming media (Reddit, YouTube, HLS, DASH) with automatic audio+video muxing."""
        downloader = MediaStreamDownloader()
        destination_path = self.destination_path
        staging_dir = get_task_staging_dir(destination_path, self.task_id)
        staged_destination = os.path.join(staging_dir, os.path.basename(destination_path))

        def on_progress(downloaded: int, total: int, speed: float, eta: Optional[int]):
            self.downloaded_bytes = downloaded
            if total > 0:
                self.total_bytes = total
            self.current_speed = speed
            self.eta_seconds = eta
            self.db.update_download_progress(self.task_id, self.downloaded_bytes)
            if self.progress_callback:
                try:
                    self.progress_callback(self)
                except Exception:
                    pass

        try:
            final_file = downloader.download(
                url=self.url,
                destination_path=staged_destination,
                cookies=self.cookies,
                cookie_jar=self.cookie_jar,
                referer=self.referer,
                user_agent=self.user_agent,
                origin=self.origin,
                progress_callback=on_progress,
                is_stopped_callback=self.is_stopped,
                resolution_callback=lambda res: setattr(self, "resolution", res),
                proxy=self.proxy,
            )
            if os.path.exists(final_file) and os.path.getsize(final_file) > 0:
                final_file = os.path.abspath(final_file)
                if os.path.commonpath((staging_dir, final_file)) != os.path.abspath(staging_dir):
                    raise RuntimeError("Media downloader returned a file outside its staging directory.")

                published_path = os.path.join(
                    os.path.dirname(destination_path),
                    os.path.basename(final_file),
                )
                os.replace(final_file, published_path)
                cleanup_task_staging_dir(destination_path, self.task_id)

                self.downloaded_bytes = os.path.getsize(published_path)
                self.total_bytes = self.downloaded_bytes
                self.destination_path = published_path
                self.filename = os.path.basename(published_path)
                self.db.update_download_file_info(self.task_id, self.filename, self.destination_path)
                self.db.update_download_progress(self.task_id, self.downloaded_bytes)
                self._set_status(DownloadStatus.COMPLETED)
            else:
                raise RuntimeError("Media stream extraction produced an empty or inaccessible file.")
        except InterruptedError:
            self._set_status(DownloadStatus.PAUSED)
            raise
        except Exception as e:
            if not self.is_stopped():
                self.error_message = str(e)
            raise

    def _probe_server(self):
        """Perform HEAD or Range GET probe to check content length and byte-range support."""
        base_headers = dict(DEFAULT_BROWSER_HEADERS)
        if self.user_agent:
            base_headers["User-Agent"] = self.user_agent
        if self.origin:
            base_headers["Origin"] = self.origin
        if self.cookies:
            base_headers["Cookie"] = self.cookies
        if self.referer:
            base_headers["Referer"] = self.referer

        previous_record = self.db.get_download(self.task_id)
        with httpx.Client(follow_redirects=True, timeout=15.0, proxy=self.proxy) as client:
            resp = None
            try:
                # First try HEAD with standard browser headers
                resp = client.head(self.url, headers=base_headers)
            except Exception:
                pass

            if resp is None or resp.status_code >= 400:
                # Fallback to GET with Range: bytes=0-0 and browser headers
                try:
                    probe_headers = dict(base_headers)
                    probe_headers["Range"] = "bytes=0-0"
                    request = client.build_request("GET", self.url, headers=probe_headers)
                    resp = client.send(request, stream=True)
                except Exception as ex:
                    raise ConnectionError(f"Failed to connect to server: {ex}")

            try:
                self._record_probe_response(resp, previous_record)
            finally:
                resp.close()

    def _record_probe_response(self, resp: httpx.Response, previous_record: Optional[Dict]):
        if resp.status_code not in (200, 206):
            if resp.status_code in (401, 403, 410):
                raise ConnectionError(
                    f"Download link expired or access forbidden (HTTP {resp.status_code}). "
                    "Click 'Refresh Address' to update URL and resume."
                )
            raise ConnectionError(f"Server returned HTTP status {resp.status_code}")

        # Inspect headers
        cl_header = resp.headers.get("Content-Length")
        cr_header = resp.headers.get("Content-Range")
        ar_header = resp.headers.get("Accept-Ranges", "").lower()
        self.content_type = resp.headers.get("Content-Type", "").lower()
        self.final_url = str(resp.url) if resp.url else self.url

        self.etag = resp.headers.get("ETag")
        self.last_modified = resp.headers.get("Last-Modified")

        # Determine total file size
        if cr_header and "/" in cr_header:
            total_str = cr_header.split("/")[-1].strip()
            if total_str.isdigit():
                self.total_bytes = int(total_str)
        elif cl_header and cl_header.isdigit() and resp.status_code == 200:
            self.total_bytes = int(cl_header)

        # Determine range support
        if resp.status_code == 206 or "bytes" in ar_header or cr_header:
            self.supports_range = True
        else:
            self.supports_range = False

        # Determine true filename from Content-Disposition and Content-Type
        cd_header = resp.headers.get("Content-Disposition")
        server_filename = parse_content_disposition(cd_header) if cd_header else None

        chosen_name = sanitize_filename(server_filename) if server_filename else None
        effective_name = chosen_name or self.filename
        stem, ext = os.path.splitext(effective_name)

        # Check if extension is missing or generic server script/dummy format
        is_generic = not ext or ext.lower() in (
            ".bin", ".tmp", ".download", ".php", ".asp", ".jsp", ".aspx", ".cgi", ".htm", ".html"
        )
        clean_ct = self.content_type.split(";")[0].strip().lower()
        if is_generic and clean_ct:
            guessed_ext = MIME_EXTENSION_MAP.get(clean_ct) or mimetypes.guess_extension(clean_ct)
            if guessed_ext:
                if guessed_ext == ".jpe":
                    guessed_ext = ".jpg"
                effective_name = f"{stem}{guessed_ext}"
                chosen_name = effective_name

        # Detect matching category from final extension
        final_ext = os.path.splitext(effective_name)[1].lower()
        detected_category = None
        if final_ext in (".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".wmv", ".ts", ".m4v", ".3gp"):
            detected_category = "Video"
        elif final_ext in (".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus", ".wma"):
            detected_category = "Music"
        elif final_ext in (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".7zip", ".cab", ".tgz"):
            detected_category = "Compressed"
        elif final_ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub", ".csv", ".rtf"):
            detected_category = "Documents"
        elif final_ext in (".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".bat", ".cmd", ".appimage"):
            detected_category = "Programs"

        if chosen_name and chosen_name != self.filename:
            target_dir = os.path.dirname(self.destination_path)
            new_path = resolve_safe_filepath(target_dir, chosen_name)
            self.filename = os.path.basename(new_path)
            self.destination_path = new_path
            self.db.update_download_file_info(self.task_id, self.filename, self.destination_path, detected_category)

        existing_segments = self.db.get_segments(self.task_id)
        if existing_segments and previous_record:
            old_etag = previous_record.get("etag")
            old_last_modified = previous_record.get("last_modified")
            old_total_bytes = previous_record.get("total_bytes")
            validators_changed = (
                (old_etag or self.etag) and old_etag != self.etag
            ) or (
                (old_last_modified or self.last_modified)
                and old_last_modified != self.last_modified
            )
            size_changed = (
                old_total_bytes is not None
                and old_total_bytes > 0
                and self.total_bytes > 0
                and old_total_bytes != self.total_bytes
            )
            if validators_changed or size_changed:
                for segment in existing_segments:
                    part_path = segment["temp_filepath"]
                    if os.path.exists(part_path):
                        os.remove(part_path)
                self.db.clear_segments(self.task_id)
                self.db.update_download_progress(self.task_id, 0)
                self.downloaded_bytes = 0

        self.db.update_download_metadata(
            self.task_id,
            self.total_bytes,
            self.etag,
            self.last_modified,
            self.supports_range
        )

    def _setup_segments(self):
        """Initialize or resume non-overlapping segments."""
        with self._segments_lock:
            existing = self.db.get_segments(self.task_id)
            get_task_staging_dir(self.destination_path, self.task_id)
            if existing:
                valid = True
                loaded = []
                for s in existing:
                    part_file = s["temp_filepath"]
                    staged_part = get_staging_path(
                        self.destination_path,
                        self.task_id,
                        f"part_{s['segment_index']}.bin",
                    )
                    if os.path.abspath(part_file) != os.path.abspath(staged_part):
                        if os.path.exists(part_file):
                            os.replace(part_file, staged_part)
                        part_file = staged_part
                        self.db.update_segment_temp_filepath(s["id"], part_file)
                    if os.path.exists(part_file):
                        actual_size = os.path.getsize(part_file)
                        loaded.append(
                            SegmentInfo(
                                segment_id=s["id"],
                                segment_index=s["segment_index"],
                                start_byte=s["start_byte"],
                                end_byte=s["end_byte"],
                                downloaded_bytes=actual_size,
                                temp_filepath=part_file,
                                status=s["status"]
                            )
                        )
                    else:
                        valid = False
                        break

                if valid and loaded:
                    self.segments = loaded
                    self.downloaded_bytes = sum(s.downloaded_bytes for s in self.segments)
                    return

            # Clear any stale records
            self.db.clear_segments(self.task_id)
            self.segments.clear()
            self.downloaded_bytes = 0

            target_dir = os.path.dirname(os.path.abspath(self.destination_path))
            os.makedirs(target_dir, exist_ok=True)

            if not self.supports_range or self.total_bytes <= 0:
                # Single connection mode
                part_path = get_staging_path(
                    self.destination_path, self.task_id, "part_0.bin"
                )
                with open(part_path, "wb"):
                    pass
                seg_id = self.db.create_segment(
                    self.task_id, 0, 0, max(0, self.total_bytes - 1), part_path
                )
                self.segments.append(
                    SegmentInfo(seg_id, 0, 0, max(0, self.total_bytes - 1), 0, part_path)
                )
            else:
                # Calculate number of segments based on file size and connection count
                num_segments = self.connections_count
                if self.total_bytes < MIN_CHUNK_SIZE * 2:
                    num_segments = 1  # Don't fragment tiny files
                else:
                    max_possible = max(1, self.total_bytes // MIN_CHUNK_SIZE)
                    num_segments = min(num_segments, max_possible)

                chunk_size = self.total_bytes // num_segments

                for i in range(num_segments):
                    start = i * chunk_size
                    end = (self.total_bytes - 1) if (i == num_segments - 1) else (start + chunk_size - 1)

                    part_path = get_staging_path(
                        self.destination_path, self.task_id, f"part_{i}.bin"
                    )
                    with open(part_path, "wb"):
                        pass

                    seg_id = self.db.create_segment(
                        self.task_id, i, start, end, part_path
                    )
                    self.segments.append(
                        SegmentInfo(
                            segment_id=seg_id,
                            segment_index=i,
                            start_byte=start,
                            end_byte=end,
                            downloaded_bytes=0,
                            temp_filepath=part_path
                        )
                    )

    def _execute_workers(self):
        """Spawn workers for each segment."""
        num_workers = len(self.segments)
        self._workers.clear()
        self._worker_errors.clear()

        for worker_idx in range(num_workers):
            t = threading.Thread(
                target=self._worker_loop,
                args=(worker_idx,),
                daemon=True,
                name=f"PDM-Worker-{self.task_id}-{worker_idx}"
            )
            self._workers.append(t)
            t.start()

        # Wait for all workers to finish
        for t in self._workers:
            t.join()
        if self._worker_errors:
            raise self._worker_errors[0]

    def _reset_segments(self):
        """Discard incomplete segments before retrying with a single connection."""
        with self._segments_lock:
            for segment in self.segments:
                if os.path.exists(segment.temp_filepath):
                    os.remove(segment.temp_filepath)
            self.db.clear_segments(self.task_id)
            self.segments.clear()
            self.downloaded_bytes = 0
            self.db.update_download_progress(self.task_id, 0)

    def _worker_loop(self, worker_id: int):
        """Worker thread: claims an unfinished segment and streams its exact byte range.
        If no unassigned segment exists, dynamically steals and splits the remaining half
        of the slowest active segment (IDM-style re-balancing)."""
        while not self.is_stopped():
            segment: Optional[SegmentInfo] = None
            with self._segments_lock:
                for s in self.segments:
                    if s.worker_id is None and s.remaining_bytes > 0:
                        s.worker_id = worker_id
                        s.status = "Downloading"
                        segment = s
                        break

            # Dynamic chunk stealing if no unassigned segment is available
            if not segment and self.supports_range and not self.is_stopped():
                with self._segments_lock:
                    candidates = [
                        s for s in self.segments
                        if s.worker_id is not None
                        and s.worker_id != worker_id
                        and s.status == "Downloading"
                        and s.remaining_bytes > 262144  # > 256 KB remaining
                    ]
                    if candidates:
                        donor = max(candidates, key=lambda s: s.remaining_bytes)
                        curr = donor.current_byte
                        old_end = donor.end_byte
                        rem = old_end - curr + 1
                        if rem > 262144:
                            mid = curr + rem // 2
                            if mid > curr and old_end > mid:
                                donor.end_byte = mid
                                self.db.update_segment_range(donor.segment_id, donor.start_byte, mid)

                                new_idx = len(self.segments)
                                new_part = get_staging_path(
                                    self.destination_path,
                                    self.task_id,
                                    f"part_{new_idx}.bin",
                                )
                                with open(new_part, "wb"):
                                    pass
                                new_seg_id = self.db.create_segment(
                                    self.task_id, new_idx, mid + 1, old_end, new_part
                                )
                                new_seg = SegmentInfo(
                                    segment_id=new_seg_id,
                                    segment_index=new_idx,
                                    start_byte=mid + 1,
                                    end_byte=old_end,
                                    downloaded_bytes=0,
                                    temp_filepath=new_part,
                                    worker_id=worker_id,
                                    status="Downloading"
                                )
                                self.segments.append(new_seg)
                                segment = new_seg

            if not segment:
                break  # No more unassigned segments and nothing eligible to steal

            try:
                self._download_segment(segment)
                with self._segments_lock:
                    segment.worker_id = None
                    if segment.remaining_bytes == 0:
                        segment.status = "Completed"
                        self.db.update_segment_progress(
                            segment.segment_id, segment.downloaded_bytes, "Completed"
                        )
            except Exception as error:
                with self._segments_lock:
                    segment.worker_id = None
                    segment.status = "Error"
                    self._worker_errors.append(error)
                if not self.is_stopped():
                    break

    def _download_segment(self, segment: SegmentInfo):
        """Stream bytes for an assigned segment strictly up to segment.end_byte."""
        headers = dict(DEFAULT_BROWSER_HEADERS)
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        if self.origin:
            headers["Origin"] = self.origin
        if self.cookies:
            headers["Cookie"] = self.cookies
        if self.referer:
            headers["Referer"] = self.referer
        requested_range = None
        if self.supports_range:
            req_start = segment.current_byte
            req_end = segment.end_byte
            if req_start > req_end:
                return  # Segment already completed
            headers["Range"] = f"bytes={req_start}-{req_end}"
            requested_range = (req_start, req_end)

        with open(segment.temp_filepath, "ab", buffering=262144) as f:
            limits = httpx.Limits(max_connections=64, max_keepalive_connections=32, keepalive_expiry=60.0)
            with httpx.Client(follow_redirects=True, timeout=30.0, proxy=self.proxy, limits=limits) as client:
                with client.stream("GET", self.url, headers=headers) as resp:
                    if requested_range and resp.status_code == 200:
                        raise RangeNotHonoredError(
                            "Server ignored a byte-range request; retrying with one connection."
                        )
                    if requested_range and resp.status_code != 206:
                        if resp.status_code in (401, 403, 410):
                            raise ConnectionError(
                                f"Download link expired (HTTP {resp.status_code}). "
                                "Click 'Refresh Address' to update URL and resume."
                            )
                        raise ConnectionError(f"Unexpected status {resp.status_code} for range request")
                    if requested_range:
                        content_range = resp.headers.get("Content-Range", "")
                        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
                        if (
                            not match
                            or int(match.group(1)) != requested_range[0]
                            or int(match.group(2)) != requested_range[1]
                            or (self.total_bytes > 0 and int(match.group(3)) != self.total_bytes)
                        ):
                            raise RangeNotHonoredError(
                                "Server returned an invalid byte range; retrying with one connection."
                            )
                    elif resp.status_code < 200 or resp.status_code >= 300:
                        raise ConnectionError(f"Server returned HTTP status {resp.status_code}")

                    for chunk in resp.iter_bytes(chunk_size=131072):
                        if self.is_stopped():
                            break

                        if not chunk:
                            continue

                        # Never write past the segment's expected bytes (strict boundary guard)
                        if self.supports_range:
                            remaining = segment.end_byte - segment.current_byte + 1
                            if remaining <= 0:
                                break
                            if len(chunk) > remaining:
                                chunk = chunk[:remaining]

                        # Rate limiting
                        self.speed_limiter.acquire(len(chunk))

                        f.write(chunk)
                        chunk_len = len(chunk)

                        with self._segments_lock:
                            segment.downloaded_bytes += chunk_len
                            self.downloaded_bytes += chunk_len
                            self._speed_window_bytes += chunk_len

                        self._maybe_checkpoint()

                        if self.supports_range and segment.current_byte > segment.end_byte:
                            break

    def _maybe_checkpoint(self):
        """Periodically update speed calculation and DB state."""
        now = time.monotonic()
        if now - self._last_db_checkpoint >= 0.5:
            elapsed = now - self._speed_window_time
            if elapsed > 0:
                self.current_speed = self._speed_window_bytes / elapsed
                self._speed_window_bytes = 0
                self._speed_window_time = now

                if self.total_bytes > 0 and self.current_speed > 0:
                    remaining = max(0, self.total_bytes - self.downloaded_bytes)
                    self.eta_seconds = int(remaining / self.current_speed)
                else:
                    self.eta_seconds = None

            self.db.update_download_progress(self.task_id, self.downloaded_bytes)
            self._last_db_checkpoint = now

            if self.progress_callback:
                try:
                    self.progress_callback(self)
                except Exception:
                    pass

    def _assemble_file(self):
        """Sequentially merge all segment part files into the target destination file."""
        with self._segments_lock:
            ordered_segments = sorted(self.segments, key=lambda s: s.start_byte)

        # Fast zero-copy path for single segment: move directly without disk rewrite
        if len(ordered_segments) == 1:
            part_path = ordered_segments[0].temp_filepath
            if not os.path.exists(part_path):
                raise FileNotFoundError(f"Missing part file: {part_path}")
            os.replace(part_path, self.destination_path)
            self.db.update_download_progress(self.task_id, self.downloaded_bytes, "Completed")
            cleanup_task_staging_dir(self.destination_path, self.task_id)
            return

        temp_final_path = get_staging_path(
            self.destination_path, self.task_id, "assembled.tmp"
        )

        try:
            with open(temp_final_path, "wb", buffering=4 * 1024 * 1024) as final_f:
                for seg in ordered_segments:
                    if not os.path.exists(seg.temp_filepath):
                        raise FileNotFoundError(f"Missing part file: {seg.temp_filepath}")

                    with open(seg.temp_filepath, "rb", buffering=4 * 1024 * 1024) as part_f:
                        shutil.copyfileobj(part_f, final_f, length=4 * 1024 * 1024)

            # Atomically replace destination file
            os.replace(temp_final_path, self.destination_path)

            # Cleanup part files
            for seg in ordered_segments:
                try:
                    if os.path.exists(seg.temp_filepath):
                        os.remove(seg.temp_filepath)
                except Exception:
                    pass

            # Update DB
            self.db.update_download_progress(self.task_id, self.downloaded_bytes, "Completed")
            cleanup_task_staging_dir(self.destination_path, self.task_id)

        except Exception as e:
            if os.path.exists(temp_final_path):
                try:
                    os.remove(temp_final_path)
                except Exception:
                    pass
            raise RuntimeError(f"Failed to assemble final file: {e}")
