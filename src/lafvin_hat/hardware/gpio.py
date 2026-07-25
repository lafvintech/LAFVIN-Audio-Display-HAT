"""Small gpiod v1/v2 adapter used by the native Raspberry Pi board."""

from __future__ import annotations

import importlib
from typing import Any

from .rpi_platform import RaspberryPiPlatform


class GpioLine:
    """One requested GPIO line with integer value semantics."""

    def __init__(
        self,
        *,
        v2_request: Any | None = None,
        v2_offset: int | None = None,
        v2_active_value: Any | None = None,
        v2_inactive_value: Any | None = None,
        v1_line: Any | None = None,
    ) -> None:
        self._v2_request = v2_request
        self._v2_offset = v2_offset
        self._v2_active_value = v2_active_value
        self._v2_inactive_value = v2_inactive_value
        self._v1_line = v1_line
        self._released = False

    def set_value(self, value: int) -> None:
        if self._released:
            return
        if self._v2_request is not None:
            self._v2_request.set_value(
                self._v2_offset,
                self._v2_active_value if value else self._v2_inactive_value,
            )
            return
        if self._v1_line is None:
            raise RuntimeError("GPIO line was not initialized")
        self._v1_line.set_value(1 if value else 0)

    def get_value(self) -> int:
        if self._released:
            raise RuntimeError("GPIO line has been released")
        if self._v2_request is not None:
            value = self._v2_request.get_value(self._v2_offset)
            return 1 if value == self._v2_active_value else 0
        if self._v1_line is None:
            raise RuntimeError("GPIO line was not initialized")
        return 1 if self._v1_line.get_value() else 0

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            if self._v2_request is not None:
                self._v2_request.release()
            elif self._v1_line is not None:
                self._v1_line.release()
        except Exception:
            # Cleanup must continue so other board resources can be released.
            pass


class GpioController:
    """Own GPIO chips and requested lines for one native board instance."""

    def __init__(
        self,
        platform: RaspberryPiPlatform,
        *,
        consumer: str = "lafvin-hat",
        gpiod_module: Any | None = None,
    ) -> None:
        self._platform = platform
        self._consumer = consumer
        self._gpiod = gpiod_module or importlib.import_module("gpiod")
        self._is_v2 = hasattr(self._gpiod, "LineSettings")
        self._chips: dict[int, Any] = {}
        self._lines: list[GpioLine] = []
        self._closed = False

    def request_output(
        self,
        board_pin: int,
        *,
        initial_value: int = 0,
        consumer: str | None = None,
    ) -> GpioLine:
        return self._request(
            board_pin,
            direction="output",
            initial_value=initial_value,
            consumer=consumer,
        )

    def request_input(
        self,
        board_pin: int,
        *,
        consumer: str | None = None,
    ) -> GpioLine:
        return self._request(
            board_pin,
            direction="input",
            initial_value=0,
            consumer=consumer,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for line in reversed(self._lines):
            line.release()
        self._lines.clear()
        for chip in self._chips.values():
            try:
                chip.close()
            except Exception:
                pass
        self._chips.clear()

    def _request(
        self,
        board_pin: int,
        *,
        direction: str,
        initial_value: int,
        consumer: str | None,
    ) -> GpioLine:
        if self._closed:
            raise RuntimeError("GPIO controller has been closed")
        offset = self._platform.line_offset(board_pin)
        chip = self._chip_for_platform()
        name = consumer or self._consumer
        if self._is_v2:
            line = self._request_v2(
                chip,
                offset,
                direction=direction,
                initial_value=initial_value,
                consumer=name,
            )
        else:
            line = self._request_v1(
                chip,
                offset,
                direction=direction,
                initial_value=initial_value,
                consumer=name,
            )
        self._lines.append(line)
        return line

    def _chip_for_platform(self) -> Any:
        chip_number = self._platform.gpiochip
        chip = self._chips.get(chip_number)
        if chip is None:
            chip = self._gpiod.Chip(self._platform.gpio_device())
            self._chips[chip_number] = chip
        return chip

    def _request_v2(
        self,
        chip: Any,
        offset: int,
        *,
        direction: str,
        initial_value: int,
        consumer: str,
    ) -> GpioLine:
        line_api = getattr(self._gpiod, "line", None)
        if line_api is None:
            line_api = importlib.import_module("gpiod.line")
        direction_value = (
            line_api.Direction.OUTPUT
            if direction == "output"
            else line_api.Direction.INPUT
        )
        kwargs: dict[str, Any] = {"direction": direction_value}
        if direction == "output":
            kwargs["output_value"] = (
                line_api.Value.ACTIVE
                if initial_value
                else line_api.Value.INACTIVE
            )
            settings = self._gpiod.LineSettings(**kwargs)
        else:
            try:
                kwargs["bias"] = line_api.Bias.DISABLED
                settings = self._gpiod.LineSettings(**kwargs)
            except Exception:
                # Some gpiod/kernel combinations do not support a disabled
                # bias setting. The accepted legacy path retried without it.
                settings = self._gpiod.LineSettings(direction=direction_value)
        request = chip.request_lines(
            consumer=consumer,
            config={offset: settings},
        )
        return GpioLine(
            v2_request=request,
            v2_offset=offset,
            v2_active_value=line_api.Value.ACTIVE,
            v2_inactive_value=line_api.Value.INACTIVE,
        )

    def _request_v1(
        self,
        chip: Any,
        offset: int,
        *,
        direction: str,
        initial_value: int,
        consumer: str,
    ) -> GpioLine:
        line = chip.get_line(offset)
        if direction == "output":
            line.request(
                consumer=consumer,
                type=self._gpiod.LINE_REQ_DIR_OUT,
                default_val=1 if initial_value else 0,
            )
        else:
            try:
                line.request(
                    consumer=consumer,
                    type=self._gpiod.LINE_REQ_DIR_IN,
                    flags=self._gpiod.LINE_REQ_FLAG_BIAS_DISABLE,
                )
            except Exception:
                line.request(
                    consumer=consumer,
                    type=self._gpiod.LINE_REQ_DIR_IN,
                )
        return GpioLine(v1_line=line)
