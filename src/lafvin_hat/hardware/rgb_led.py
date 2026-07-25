"""Active-low RGB LED control for the LAFVIN HAT."""

from __future__ import annotations

from typing import Any, Protocol

from .pwm import SoftwarePwm


class _OutputLine(Protocol):
    def set_value(self, value: int) -> None: ...


class RgbLed:
    """Three active-low 100 Hz software PWM channels."""

    def __init__(
        self,
        red: _OutputLine,
        green: _OutputLine,
        blue: _OutputLine,
        *,
        pwm_factory: Any = SoftwarePwm,
    ) -> None:
        self._red = pwm_factory(
            red.set_value,
            frequency_hz=100,
            stop_value=1,
        )
        self._green = pwm_factory(
            green.set_value,
            frequency_hz=100,
            stop_value=1,
        )
        self._blue = pwm_factory(
            blue.set_value,
            frequency_hz=100,
            stop_value=1,
        )
        self._channels = (self._red, self._green, self._blue)
        for channel in self._channels:
            channel.start(100)
        self._rgb = (0, 0, 0)

    def set(self, r: int, g: int, b: int) -> None:
        self._rgb = tuple(max(0, min(255, int(value))) for value in (r, g, b))
        for channel, value in zip(self._channels, self._rgb, strict=True):
            # Low output is lit, so brightness is inverse physical duty cycle.
            channel.change_duty_cycle(100 - value / 255 * 100)

    def close(self) -> None:
        for channel in self._channels:
            channel.stop()
