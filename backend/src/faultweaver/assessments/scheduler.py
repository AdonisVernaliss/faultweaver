from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from time import monotonic, sleep


class RateLimiter:
    """Thread-safe request-start limiter with an injectable clock for deterministic tests."""

    def __init__(
        self,
        requests_per_second: float,
        *,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], None] = sleep,
    ) -> None:
        self._interval = 1.0 / requests_per_second
        self._clock = clock
        self._sleep = sleep
        self._next_start: float | None = None
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if self._next_start is None:
                self._next_start = now + self._interval
                return
            delay = max(0.0, self._next_start - now)
            if delay:
                self._sleep(delay)
                now = self._clock()
            self._next_start = max(self._next_start, now) + self._interval
