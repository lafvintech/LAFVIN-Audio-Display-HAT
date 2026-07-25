"""Polling physical button with Runtime-compatible press/release callbacks."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol


class _InputLine(Protocol):
    def get_value(self) -> int: ...


ButtonCallback = Callable[[], None]


class Button:
    """Use the accepted 5 ms high-is-pressed polling behavior."""

    def __init__(self, line: _InputLine, *, poll_interval_sec: float = 0.005) -> None:
        if poll_interval_sec <= 0:
            raise ValueError("Button poll interval must be positive")
        self._line = line
        self._poll_interval_sec = poll_interval_sec
        self._on_press: ButtonCallback | None = None
        self._on_release: ButtonCallback | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def bind(self, on_press: ButtonCallback, on_release: ButtonCallback) -> None:
        self._on_press = on_press
        self._on_release = on_release

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor,
            name="lafvin-hat-button",
            daemon=True,
        )
        self._thread.start()

    def is_pressed(self) -> bool:
        return bool(self._line.get_value())

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)
        self._thread = None

    def _monitor(self) -> None:
        try:
            previous = self._line.get_value()
        except Exception:
            previous = 0
        while not self._stop_event.wait(self._poll_interval_sec):
            try:
                current = self._line.get_value()
            except Exception:
                continue
            if current == previous:
                continue
            previous = current
            callback = self._on_press if current else self._on_release
            if callback is not None:
                try:
                    callback()
                except Exception:
                    # A Runtime callback must not terminate the hardware thread.
                    pass
