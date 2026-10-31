# Important Engineering & Safety Rules

1. **Independent Implementation (Clean Room):**
   - Strictly no decompilation, cracking, patching, or extracting code from commercial download managers.
   - Use standard RFC-compliant network protocols (RFC 9110, RFC 7233).
   - Zero bypass of DRM, paywalls, or authentication boundaries.

2. **Personal Use Scope:**
   - No telemetry, analytics, cloud backends, subscriptions, or user account systems.
   - All state, settings, and download histories reside exclusively in a local SQLite database (`downloads.db`).
   - Minimal CPU and memory overhead; clean shutdown without lingering background daemon processes.

3. **Defensive Security & Reliability:**
   - **Strict URL Validation:** Scheme must be `http` or `https`. Reject `file://`, `javascript:`, `data:`, or shell schemes.
   - **Fail-Closed TLS:** Never disable SSL/TLS certificate validation. Use system certificate stores.
   - **Path Traversal Protection:** Sanitize all filenames, strip directory components (`../`, `..\`), strip illegal Windows characters (`<>:"/\|?*`), and reject Windows reserved device names (`CON`, `NUL`, etc.).
   - **No Auto-Execution:** Never execute or launch downloaded binaries automatically.
   - **Safe File Assembly:** Avoid partial file corruption; assemble segments safely and clean up temporary parts only after verified disk writes.

4. **Engine & GUI Decoupling:**
   - The UI thread (PySide6) must never perform blocking network I/O or heavy disk operations.
   - Cross-thread communication must strictly use Qt Signals/Slots or thread-safe queues.
   - Decoupled engine should be testable without launching the GUI.

5. **Incremental & Verified Progress:**
   - Write tests alongside each feature.
   - Never declare a feature complete without test verification.
   - Preserve working functionality across edits.
