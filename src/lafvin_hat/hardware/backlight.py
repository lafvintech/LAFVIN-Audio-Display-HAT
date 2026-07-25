"""Active-low PWM backlight for supported LAFVIN HAT Raspberry Pi boards."""

from __future__ import annotations

from typing import Any, Protocol

from .pwm import SoftwarePwm


class _OutputLine(Protocol):
    def set_value(self, value: int) -> None: ...


class Backlight:
    """Use the accepted 1 kHz active-low brightness behavior."""

    def __init__(self, line: _OutputLine, *, pwm_factory: Any = SoftwarePwm) -> None:
        self._pwm = pwm_factory(
            line.set_value,
            frequency_hz=1000,
            stop_value=1,
        )
        self._pwm.start(100)
        self._brightness = 0

    def set(self, value: int) -> None:
        self._brightness = max(0, min(100, int(value)))
        # Backlight output is active-low.
        self._pwm.change_duty_cycle(100 - self._brightness)

    def close(self) -> None:
        self._pwm.stop()
