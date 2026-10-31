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
        if self._rate <= 0:
            return  # Unlimited

        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_time
                self._last_time = now

                # Replenish tokens
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)

                if self._tokens >= num_bytes:
                    self._tokens -= num_bytes
                    return

                # Calculate sleep duration needed for remaining tokens
                needed = num_bytes - self._tokens
                sleep_time = needed / self._rate

            time.sleep(min(sleep_time, 0.1))
