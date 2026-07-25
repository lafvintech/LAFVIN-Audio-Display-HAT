from __future__ import annotations

import time
from collections import deque
from typing import Any


class DisplayMetrics:
    def __init__(self) -> None:
        self._present_count = 0
        self._present_times: deque[float] = deque()
        self._last_present_ms: float | None = None

    def record_present(self, duration_ms: float) -> None:
        now = time.monotonic()
        self._present_count += 1
        self._last_present_ms = duration_ms
        self._present_times.append(now)
        while self._present_times and now - self._present_times[0] > 1.0:
            self._present_times.popleft()

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        while self._present_times and now - self._present_times[0] > 1.0:
            self._present_times.popleft()
        return {
            "present_count": self._present_count,
            "fps": len(self._present_times),
            "last_present_ms": self._last_present_ms,
        }
