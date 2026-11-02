"""SQLite persistence manager for Personal Download Manager."""

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional


class DatabaseManager:
    """Thread-safe SQLite database manager operating in WAL mode."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            with conn:
                yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _init_db(self):
        with self._lock, self._get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                destination_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                total_bytes INTEGER DEFAULT -1,
                downloaded_bytes INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Queued',
                etag TEXT,
                last_modified TEXT,
                supports_range INTEGER DEFAULT 0,
                connections_count INTEGER DEFAULT 4,
                category TEXT DEFAULT 'Other',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                download_id INTEGER NOT NULL,
                segment_index INTEGER NOT NULL,
                start_byte INTEGER NOT NULL,
                end_byte INTEGER NOT NULL,
                downloaded_bytes INTEGER DEFAULT 0,
                status TEXT DEFAULT 'Pending',
                temp_filepath TEXT NOT NULL,
                FOREIGN KEY (download_id) REFERENCES downloads(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS incoming_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                download_id INTEGER DEFAULT 0,
                url TEXT NOT NULL,
                filename TEXT DEFAULT '',
                category TEXT DEFAULT 'Other',
                cookies TEXT DEFAULT '',
                referer TEXT DEFAULT '',
                user_agent TEXT DEFAULT '',
                origin TEXT DEFAULT '',
                proxy TEXT DEFAULT '',
                auto_start INTEGER DEFAULT 1,
                processed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
            CREATE INDEX IF NOT EXISTS idx_downloads_category ON downloads(category);
            CREATE INDEX IF NOT EXISTS idx_segments_download ON segments(download_id);
            """)

            # Ensure optional IDM columns exist in schema
            for col_name, col_type in [
                ("description", "TEXT DEFAULT ''"),
                ("queue_name", "TEXT DEFAULT ''"),
                ("cookies", "TEXT DEFAULT ''"),
                ("referer", "TEXT DEFAULT ''"),
                ("user_agent", "TEXT DEFAULT ''"),
                ("origin", "TEXT DEFAULT ''"),
                ("proxy", "TEXT DEFAULT ''")
            ]:
                try:
                    conn.execute(f"ALTER TABLE downloads ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass

            try:
                conn.execute("ALTER TABLE incoming_requests ADD COLUMN download_id INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

    # ------------------- Download Task CRUD -------------------

    def create_download(
        self,
        url: str,
        destination_path: str,
        filename: str,
        category: str = "Other",
        connections_count: int = 4,
        description: str = "",
        queue_name: str = "",
        cookies: str = "",
        referer: str = "",
        user_agent: str = "",
        origin: str = "",
        proxy: str = ""
    ) -> int:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO downloads (url, destination_path, filename, category, connections_count, status, description, queue_name, cookies, referer, user_agent, origin, proxy)
                VALUES (?, ?, ?, ?, ?, 'Queued', ?, ?, ?, ?, ?, ?, ?)
                """,
                (url, destination_path, filename, category, connections_count, description, queue_name, cookies, referer, user_agent, origin, proxy)
            )
            return cur.lastrowid

    def get_download(self, download_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM downloads WHERE id = ?", (download_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_downloads(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM downloads WHERE 1=1"
        params: List[Any] = []

        if category and category != "All":
            query += " AND category = ?"
            params.append(category)

        if status and status != "All":
            if status == "Unfinished":
                query += " AND status != 'Completed'"
            elif status == "Finished":
                query += " AND status = 'Completed'"
            else:
                query += " AND status = ?"
                params.append(status)

        if search:
            query += " AND (filename LIKE ? OR url LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term])

        query += " ORDER BY id DESC"

        with self._lock, self._get_connection() as conn:
            cur = conn.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def update_download_metadata(
        self,
        download_id: int,
        total_bytes: int,
        etag: Optional[str],
        last_modified: Optional[str],
        supports_range: bool
    ):
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                UPDATE downloads
                SET total_bytes = ?, etag = ?, last_modified = ?, supports_range = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (total_bytes, etag, last_modified, 1 if supports_range else 0, download_id)
            )

    def update_download_progress(
        self,
        download_id: int,
        downloaded_bytes: int,
        status: Optional[str] = None
    ):
        with self._lock, self._get_connection() as conn:
            if status:
                completed_clause = ", completed_at = CURRENT_TIMESTAMP" if status == "Completed" else ""
                conn.execute(
                    f"""
                    UPDATE downloads
                    SET downloaded_bytes = ?, status = ?, updated_at = CURRENT_TIMESTAMP {completed_clause}
                    WHERE id = ?
                    """,
                    (downloaded_bytes, status, download_id)
                )
            else:
                conn.execute(
                    """
                    UPDATE downloads
                    SET downloaded_bytes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (downloaded_bytes, download_id)
                )

    def set_download_status(self, download_id: int, status: str, error_message: Optional[str] = None):
        with self._lock, self._get_connection() as conn:
            completed_clause = ", completed_at = CURRENT_TIMESTAMP" if status == "Completed" else ""
            conn.execute(
                f"""
                UPDATE downloads
                SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP {completed_clause}
                WHERE id = ?
                """,
                (status, error_message, download_id)
            )

    def update_download_file_info(self, download_id: int, filename: str, destination_path: str, category: Optional[str] = None):
        """Update filename, destination path, and optionally category (e.g. after server probe or media downloader resolves title)."""
        with self._lock, self._get_connection() as conn:
            if category:
                conn.execute(
                    """
                    UPDATE downloads
                    SET filename = ?, destination_path = ?, category = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (filename, destination_path, category, download_id)
                )
            else:
                conn.execute(
                    """
                    UPDATE downloads
                    SET filename = ?, destination_path = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (filename, destination_path, download_id)
                )

    def update_download_address(self, download_id: int, new_url: str, cookies: str = "", referer: str = ""):
        """Update download URL and session cookies for an expired or renewed download link."""
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                UPDATE downloads
                SET url = ?,
                    cookies = CASE WHEN ? != '' THEN ? ELSE cookies END,
                    referer = CASE WHEN ? != '' THEN ? ELSE referer END,
                    error_message = NULL,
                    status = 'Queued',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_url, cookies, cookies, referer, referer, download_id)
            )

    def delete_download(self, download_id: int):
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM downloads WHERE id = ?", (download_id,))

    def delete_completed(self) -> List[Dict[str, Any]]:
        """Delete all completed downloads from DB and return the deleted records."""
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM downloads WHERE status = 'Completed'")
            completed = [dict(r) for r in cur.fetchall()]
            conn.execute("DELETE FROM downloads WHERE status = 'Completed'")
            return completed

    # ------------------- Segment Tracking -------------------

    def create_segment(
        self,
        download_id: int,
        segment_index: int,
        start_byte: int,
        end_byte: int,
        temp_filepath: str
    ) -> int:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO segments (download_id, segment_index, start_byte, end_byte, downloaded_bytes, temp_filepath)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (download_id, segment_index, start_byte, end_byte, temp_filepath)
            )
            return cur.lastrowid

    def get_segments(self, download_id: int) -> List[Dict[str, Any]]:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM segments WHERE download_id = ? ORDER BY segment_index ASC",
                (download_id,)
            )
            return [dict(row) for row in cur.fetchall()]

    def update_segment_progress(
        self,
        segment_id: int,
        downloaded_bytes: int,
        status: Optional[str] = None
    ):
        with self._lock, self._get_connection() as conn:
            if status:
                conn.execute(
                    "UPDATE segments SET downloaded_bytes = ?, status = ? WHERE id = ?",
                    (downloaded_bytes, status, segment_id)
                )
            else:
                conn.execute(
                    "UPDATE segments SET downloaded_bytes = ? WHERE id = ?",
                    (downloaded_bytes, segment_id)
                )

    def update_segment_range(self, segment_id: int, start_byte: int, end_byte: int):
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "UPDATE segments SET start_byte = ?, end_byte = ? WHERE id = ?",
                (start_byte, end_byte, segment_id)
            )

    def clear_segments(self, download_id: int):
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM segments WHERE download_id = ?", (download_id,))

    # ------------------- Settings Key-Value -------------------

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value)
            )

    # ------------------- Incoming Browser Requests -------------------

    def add_incoming_request(
        self,
        url: str,
        filename: str = "",
        category: str = "Other",
        cookies: str = "",
        referer: str = "",
        user_agent: str = "",
        origin: str = "",
        proxy: str = "",
        auto_start: bool = True,
        download_id: int = 0
    ) -> int:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO incoming_requests (url, filename, category, cookies, referer, user_agent, origin, proxy, auto_start, download_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (url, filename, category, cookies, referer, user_agent, origin, proxy, 1 if auto_start else 0, download_id)
            )
            return cur.lastrowid

    def fetch_unprocessed_incoming_requests(self) -> List[Dict[str, Any]]:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM incoming_requests WHERE processed = 0 ORDER BY id ASC"
            )
            return [dict(r) for r in cur.fetchall()]

    def mark_incoming_request_processed(self, request_id: int):
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "UPDATE incoming_requests SET processed = 1 WHERE id = ?",
                (request_id,)
            )
