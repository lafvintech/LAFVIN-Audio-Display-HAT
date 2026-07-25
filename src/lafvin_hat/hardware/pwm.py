"""Interruptible software PWM for active-low HAT outputs."""

from __future__ import annotations

import threading
from collections.abc import Callable


class SoftwarePwm:
    """A small PWM worker that can be stopped before GPIO release."""

    def __init__(
        self,
        write_value: Callable[[int], None],
        *,
        frequency_hz: float,
        stop_value: int,
    ) -> None:
        if frequency_hz <= 0:
            raise ValueError("PWM frequency must be positive")
        self._write_value = write_value
        self._period = 1.0 / frequency_hz
        self._stop_value = 1 if stop_value else 0
        self._duty_cycle = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, duty_cycle: float = 0.0) -> None:
        self.change_duty_cycle(duty_cycle)
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="lafvin-hat-pwm",
            daemon=True,
        )
        self._thread.start()

    def change_duty_cycle(self, duty_cycle: float) -> None:
        with self._lock:
            self._duty_cycle = max(0.0, min(100.0, float(duty_cycle)))

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)
        self._thread = None
        try:
            self._write_value(self._stop_value)
        except Exception:
            pass

    def _run(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                duty_cycle = self._duty_cycle
            if duty_cycle <= 0:
                self._write_value(0)
                self._stop_event.wait(self._period)
                continue
            if duty_cycle >= 100:
                self._write_value(1)
                self._stop_event.wait(self._period)
                continue
            on_time = self._period * duty_cycle / 100.0
            self._write_value(1)
            if self._stop_event.wait(on_time):
                break
            self._write_value(0)
            self._stop_event.wait(self._period - on_time)
