# Test Report

## Automated Test Run Summary
- **Execution Date:** 2026-10-30
- **Runner:** `pytest 9.2.0` on Python `3.12.10` (win32)
- **Total Tests:** 23
- **Passed:** 23
- **Failed:** 0
- **Execution Duration:** 5.79s

### Test Breakdown by Module

| Module | Test Name | Purpose / Verified Invariant | Status |
|---|---|---|---|
| `test_batch.py` | `test_expand_numeric_pattern` | Numeric wildcard range expansion with zero-padding | PASS |
| `test_batch.py` | `test_expand_alpha_pattern` | Alphabetic wildcard range expansion (`[a-d]`) | PASS |
| `test_batch.py` | `test_parse_batch_input` | Multi-line text parsing, pattern expansion, URL filtering | PASS |
| `test_scheduler.py` | `test_scheduler_config` | Automated queue timer configuration and DB persistence | PASS |
| `test_security.py` | `test_validate_url` | Accepts http/https, rejects file://, javascript:, malformed URLs | PASS |
| `test_security.py` | `test_sanitize_filename` | Path traversal protection, Windows reserved names (`CON`, `NUL`), illegal chars | PASS |
| `test_security.py` | `test_extract_filename_from_url` | Strips query tokens and extracts clean resource names | PASS |
| `test_security.py` | `test_parse_content_disposition` | Parses quoted, unquoted, and RFC 5987 UTF-8 encoded names | PASS |
| `test_security.py` | `test_resolve_safe_filepath` | Anti-collision naming (`file (1).ext`) and directory containment | PASS |
| `test_storage.py` | `test_download_crud` | Task creation, status updates, metadata, query filters, and search | PASS |
| `test_storage.py` | `test_segment_management` | Segment range insertion, progress checkpoints, and cascade deletion | PASS |
| `test_storage.py` | `test_settings_storage` | Key-value settings upsert and default fallbacks in WAL mode | PASS |
| `test_engine.py` | `test_multi_connection_download` | Multi-connection Range 206 download and byte-for-byte SHA-256 integrity match | PASS |
| `test_engine.py` | `test_single_connection_fallback`| Graceful fallback to single linear stream when server denies Range | PASS |
| `test_engine.py` | `test_redirect_download` | Follows HTTP 302 redirect and downloads final resource cleanly | PASS |
| `test_engine.py` | `test_coordinator_queue_management` | Enforces max concurrent downloads, queues surplus tasks, and drains queue | PASS |
| `test_engine.py` | `test_pause_and_resume` | Mid-stream pause, server validator check, and resumed completion matching hash | PASS |
| `test_gui.py` | `test_format_helpers` | Formats bytes (KB/MB/GB), transfer rates, and ETA strings | PASS |
| `test_gui.py` | `test_detect_category` | Extension-to-category mapping (Compressed, Video, Music, etc.) | PASS |
| `test_gui.py` | `test_table_model` | AbstractTableModel row/column count, cell values, and status colors | PASS |
| `test_gui.py` | `test_segment_widget` | Custom segment visualization widget offscreen painting | PASS |
| `test_gui.py` | `test_main_window_and_filtering`| Window creation, category sidebar filtering, and search bar filtering | PASS |
| `test_browser_bridge.py`| `test_native_messaging_roundtrip` | 32-bit length-prefixed JSON stdin/stdout protocol serialization | PASS |
