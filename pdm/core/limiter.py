"""Token bucket rate limiter for controlling download speeds."""

import threading
import time
from typing import Optional


class SpeedLimiter:
    """Thread-safe token bucket rate limiter."""

    def __init__(self, bytes_per_second: int = 0):
        """
        Args:
            bytes_per_second: Max speed in bytes/sec. 0 means unlimited.
        """
        self._rate = bytes_per_second
        self._tokens = float(bytes_per_second)
        self._capacity = float(max(bytes_per_second, 65536))
        self._last_time = time.monotonic()
        self._lock = threading.Lock()

    def set_rate(self, bytes_per_second: int):
        with self._lock:
            self._rate = bytes_per_second
            self._capacity = float(max(bytes_per_second, 65536))
            self._tokens = min(self._tokens, self._capacity)
            self._last_time = time.monotonic()

    def get_rate(self) -> int:
        with self._lock:
            return self._rate

    def acquire(self, num_bytes: int):
        """Acquire permission to transfer num_bytes.
        
        Blocks if rate limit would be exceeded.
        """
        remaining = max(0, num_bytes)

        while remaining:
            with self._lock:
                if self._rate <= 0:
                    return

                now = time.monotonic()
                elapsed = now - self._last_time
                self._last_time = now

                # Replenish tokens
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                request_bytes = min(remaining, self._capacity)

                if self._tokens >= request_bytes:
                    self._tokens -= request_bytes
                    remaining -= request_bytes
                    continue

                # Calculate sleep duration needed for remaining tokens
                needed = request_bytes - self._tokens
                sleep_time = needed / self._rate

            time.sleep(min(sleep_time, 0.1))
