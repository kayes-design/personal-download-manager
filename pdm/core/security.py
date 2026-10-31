"""Security primitives and sanitization routines for Personal Download Manager."""

import os
import re
import urllib.parse
from typing import Optional, Tuple

# Windows-reserved device names (case-insensitive)
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

# Illegal characters in Windows filenames
ILLEGAL_CHARS_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def validate_url(url: str) -> Tuple[bool, str]:
    """Validate that the URL is safe, syntactically correct, and uses http/https.
    
    Returns:
        (is_valid, error_or_normalized_url)
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty."

    url = url.strip()
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception as e:
        return False, f"Malformed URL: {e}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Unsupported scheme '{parsed.scheme}'. Only HTTP and HTTPS are allowed."

    if not parsed.netloc:
        return False, "URL missing host/network location."

    return True, url


def sanitize_filename(name: str, default_fallback: str = "download.bin") -> str:
    """Sanitize an untrusted filename received from URL or Content-Disposition.
    
    Protects against:
    - Path traversal (../, ..\\)
    - URL encoded traversal (%2e%2e%2f) and double encoding
    - Windows reserved device names (CON, NUL, COM1, etc.)
    - Windows forbidden characters (<>:"/\\|?*) and control chars
    - Trailing spaces and periods
    """
    if not name or not isinstance(name, str):
        return default_fallback

    # 1. Canonicalize / decode percent-encoding first to prevent double-encoding bypasses
    decoded = name
    for _ in range(2):
        try:
            unquoted = urllib.parse.unquote(decoded)
            if unquoted == decoded:
                break
            decoded = unquoted
        except Exception:
            break

    # 2. Extract only the base name (strip any directory paths)
    base = os.path.basename(decoded.replace("\\", "/"))

    # 3. Strip illegal characters and control codes
    cleaned = ILLEGAL_CHARS_PATTERN.sub("_", base)

    # 4. Strip trailing periods and spaces (Windows disallows these)
    cleaned = cleaned.strip(". ")

    # 5. Check Windows reserved base names
    stem, ext = os.path.splitext(cleaned)
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"

    # If completely empty or consists only of underscores/dots, use fallback
    if not cleaned or cleaned.replace("_", "") == "":
        return default_fallback

    # Limit filename length to 240 chars to leave room for Windows MAX_PATH
    if len(cleaned) > 240:
        stem = stem[:230]
        cleaned = f"{stem}{ext}"

    return cleaned


def extract_filename_from_url(url: str, default_fallback: str = "download.bin") -> str:
    """Extract and sanitize filename from the URL path, adding .mp4 for video stream URLs."""
    try:
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path
        raw_name = path.rstrip("/").split("/")[-1] if path else ""
        if raw_name:
            if "." not in raw_name and any(v in url.lower() for v in ("reddit", "v.redd.it", "youtu", "tiktok", "twitter", "x.com")):
                return sanitize_filename(f"{raw_name}.mp4", default_fallback)
            return sanitize_filename(raw_name, default_fallback)
    except Exception:
        pass
    return default_fallback


def parse_content_disposition(header_val: Optional[str]) -> Optional[str]:
    """Parse Content-Disposition header supporting RFC 6266 and RFC 5987 UTF-8 filenames."""
    if not header_val:
        return None

    # Check for RFC 5987 filename*=UTF-8''encoded_name
    utf8_match = re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", header_val)
    if utf8_match:
        try:
            return urllib.parse.unquote(utf8_match.group(1).strip('"\''))
        except Exception:
            pass

    # Standard filename="name" or filename=name
    fn_match = re.search(r'filename\s*=\s*(?:"([^"]+)"|([^;\s]+))', header_val)
    if fn_match:
        return (fn_match.group(1) or fn_match.group(2)).strip()

    return None


def resolve_safe_filepath(directory: str, filename: str) -> str:
    """Ensure destination path stays strictly inside directory and handles name collisions.
    
    Generates non-colliding names: 'file (1).ext', 'file (2).ext', etc.
    """
    safe_name = sanitize_filename(filename)
    target_dir = os.path.abspath(directory)
    os.makedirs(target_dir, exist_ok=True)

    candidate_path = os.path.abspath(os.path.join(target_dir, safe_name))

    # Path traversal check: candidate must be strictly within target_dir
    common = os.path.commonpath([target_dir, candidate_path])
    if common != target_dir:
        raise ValueError(f"Path traversal detected! Path {candidate_path} leaves {target_dir}")

    # Anti-collision numbering
    if not os.path.exists(candidate_path):
        return candidate_path

    stem, ext = os.path.splitext(safe_name)
    counter = 1
    while True:
        collision_name = f"{stem} ({counter}){ext}"
        candidate_path = os.path.abspath(os.path.join(target_dir, collision_name))
        if not os.path.exists(candidate_path):
            return candidate_path
        counter += 1
