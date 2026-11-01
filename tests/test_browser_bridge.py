"""Unit tests for browser native messaging protocol."""

import io
import json
import struct
from pdm.browser_bridge.native_host import read_message, send_message


def test_native_messaging_roundtrip():
    test_payload = {"action": "download", "url": "https://example.com/test.zip"}
    payload_bytes = json.dumps(test_payload).encode("utf-8")
    header = struct.pack("@I", len(payload_bytes))

    fake_stdin = io.BytesIO(header + payload_bytes)
    msg = read_message(stream=fake_stdin)
    assert msg == test_payload

    fake_stdout = io.BytesIO()
    response = {"status": "ok", "task_id": 42}
    send_message(response, stream=fake_stdout)

    raw_out = fake_stdout.getvalue()
    out_len = struct.unpack("@I", raw_out[:4])[0]
    out_body = json.loads(raw_out[4 : 4 + out_len].decode("utf-8"))

    assert out_body == response


def test_native_batch_handling(tmp_path):
    from pdm.browser_bridge.native_host import handle_download_item
    from pdm.storage.db import DatabaseManager

    db = DatabaseManager(str(tmp_path / "test_bridge.db"))
    db.set_setting("show_start_dlg", "0")

    # Instant start
    item1 = {"url": "https://example.com/v1.mp4", "filename": "v1.mp4", "auto_start": True}
    tid1 = handle_download_item(db, str(tmp_path), 4, item1)
    assert tid1 is not None
    assert db.get_download(tid1)["status"] == "Queued"

    # Add to queue for later (auto_start=False)
    item2 = {"url": "https://example.com/v2.mp4", "filename": "v2.mp4", "auto_start": False}
    tid2 = handle_download_item(db, str(tmp_path), 4, item2)
    assert tid2 is not None
    assert db.get_download(tid2)["status"] == "Paused"
