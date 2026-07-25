"""240x280 ST7789-compatible RGB565 display transport.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol


class _DigitalOutput(Protocol):
    def set_value(self, value: int) -> None: ...


class _SpiWriter(Protocol):
    def command(self, value: int) -> None: ...

    def write(self, data: bytes | bytearray | memoryview) -> None: ...


class St7789Display:
    """Preserve the accepted LAFVIN HAT LCD initialization and frame layout."""

    width = 240
    height = 280
    row_offset = 20

    def __init__(
        self,
        spi: _SpiWriter,
        *,
        data_command_line: _DigitalOutput,
        reset_line: _DigitalOutput,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._spi = spi
        self._dc = data_command_line
        self._reset = reset_line
        self._sleep = sleep
        self._initialized = False

    def initialize(self) -> None:
        self._reset_lcd()
        self._command(0x11)
        self._sleep(0.12)
        self._command(0x36, 0xC0)
        self._command(0x3A, 0x05)
        self._command(0xB2, 0x0C, 0x0C, 0x00, 0x33, 0x33)
        self._command(0xB7, 0x35)
        self._command(0xBB, 0x32)
        self._command(0xC2, 0x01)
        self._command(0xC3, 0x15)
        self._command(0xC4, 0x20)
        self._command(0xC6, 0x0F)
        self._command(0xD0, 0xA4, 0xA1)
        self._command(
            0xE0,
            0xD0,
            0x08,
            0x0E,
            0x09,
            0x09,
            0x05,
            0x31,
            0x33,
            0x48,
            0x17,
            0x14,
            0x15,
            0x31,
            0x34,
        )
        self._command(
            0xE1,
            0xD0,
            0x08,
            0x0E,
            0x09,
            0x09,
            0x15,
            0x31,
            0x33,
            0x48,
            0x17,
            0x14,
            0x15,
            0x31,
            0x34,
        )
        self._command(0x21)
        self._command(0x29)
        self._initialized = True

    def present_rgb565(
        self,
        rgb565: bytes | bytearray | memoryview,
        *,
        width: int,
        height: int,
        x: int = 0,
        y: int = 0,
    ) -> None:
        self._validate_window(x=x, y=y, width=width, height=height)
        payload = memoryview(rgb565).cast("B")
        expected_length = width * height * 2
        if payload.nbytes != expected_length:
            raise ValueError(
                f"RGB565 payload size is {payload.nbytes}, expected {expected_length}"
            )
        self._set_window(x, y, x + width - 1, y + height - 1)
        self._data(payload)

    def fill_rgb565(self, color: int) -> None:
        color = max(0, min(0xFFFF, int(color)))
        pixel = bytes(((color >> 8) & 0xFF, color & 0xFF))
        self.present_rgb565(
            pixel * (self.width * self.height),
            width=self.width,
            height=self.height,
        )

    def _reset_lcd(self) -> None:
        self._reset.set_value(1)
        self._sleep(0.1)
        self._reset.set_value(0)
        self._sleep(0.1)
        self._reset.set_value(1)
        self._sleep(0.12)

    def _command(self, command: int, *data: int) -> None:
        self._dc.set_value(0)
        self._spi.command(command)
        if data:
            self._data(bytes(data))

    def _data(self, data: bytes | bytearray | memoryview) -> None:
        self._dc.set_value(1)
        self._spi.write(data)

    def _set_window(self, x0: int, y0: int, x1: int, y1: int) -> None:
        self._command(0x2A, x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)
        y0 += self.row_offset
        y1 += self.row_offset
        self._command(0x2B, y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)
        self._command(0x2C)

    def _validate_window(self, *, x: int, y: int, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Display dimensions must be positive")
        if x < 0 or y < 0 or x + width > self.width or y + height > self.height:
            raise ValueError("Image dimensions exceed LAFVIN HAT display bounds")
