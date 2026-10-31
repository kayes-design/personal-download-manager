"""Local HTTP test server simulating real-world download scenarios."""

import http.server
import socketserver
import threading
import time
from typing import Dict, Optional, Tuple


class DownloadTestHandler(http.server.BaseHTTPRequestHandler):
    """Custom request handler supporting Range requests, redirects, and edge cases."""

    # Pre-configured resources: path -> (bytes_content, supports_range, etag, last_modified)
    resources: Dict[str, Tuple[bytes, bool, str, str]] = {}

    def log_message(self, format, *args):
        # Silence default request logging in tests
        pass

    def do_HEAD(self):
        self._handle_request(send_body=False)

    def do_GET(self):
        self._handle_request(send_body=True)

    def _handle_request(self, send_body: bool = True):
        # Handle redirect test
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/range-supported.bin")
            self.end_headers()
            return

        # Check resource
        path = self.path.split("?")[0]
        if path not in self.resources:
            self.send_response(404)
            self.end_headers()
            return

        res = self.resources[path]
        content = res[0]
        supports_range = res[1]
        etag = res[2]
        last_mod = res[3]
        content_type = res[4] if len(res) > 4 else "application/octet-stream"
        total_len = len(content)

        range_header = self.headers.get("Range") if supports_range else None

        if range_header and range_header.startswith("bytes="):
            # Parse Range: bytes=start-end
            try:
                range_spec = range_header.replace("bytes=", "").strip()
                parts = range_spec.split("-")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if parts[1] else total_len - 1

                if start >= total_len or end >= total_len or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{total_len}")
                    self.end_headers()
                    return

                chunk = content[start : end + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{total_len}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("ETag", etag)
                self.send_header("Last-Modified", last_mod)
                self.send_header("Content-Type", content_type)
                self.end_headers()

                if send_body:
                    self.wfile.write(chunk)
                return
            except Exception:
                self.send_response(400)
                self.end_headers()
                return

        # Non-range request or server ignoring range
        self.send_response(200)
        self.send_header("Content-Length", str(total_len))
        if supports_range:
            self.send_header("Accept-Ranges", "bytes")
        else:
            self.send_header("Accept-Ranges", "none")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", last_mod)
        self.send_header("Content-Type", content_type)
        self.end_headers()

        if send_body:
            self.wfile.write(content)


class LocalTestServer:
    """Threaded local test HTTP server."""

    def __init__(self, port: int = 0):
        # Port 0 binds to any available ephemeral port
        self.server = socketserver.TCPServer(("127.0.0.1", port), DownloadTestHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def add_resource(
        self,
        path: str,
        content: bytes,
        supports_range: bool = True,
        etag: str = '"default-etag-1"',
        last_modified: str = "Wed, 21 Oct 2026 07:28:00 GMT",
        content_type: str = "application/octet-stream"
    ):
        DownloadTestHandler.resources[path] = (content, supports_range, etag, last_modified, content_type)

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def get_url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"
