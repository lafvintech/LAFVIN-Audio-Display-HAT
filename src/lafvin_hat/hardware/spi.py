"""SPI transport with byte-oriented frame writes."""

from __future__ import annotations

import importlib
from typing import Any


class SpiTransport:
    """Own one spidev device and preserve RGB565 buffers on the fast path."""

    def __init__(
        self,
        *,
        bus: int,
        chip_select: int,
        speed_hz: int,
        mode: int = 0,
        spi_factory: Any | None = None,
    ) -> None:
        if spi_factory is None:
            spi_module = importlib.import_module("spidev")
            spi_factory = spi_module.SpiDev
        self._spi = spi_factory()
        self._closed = False
        try:
            self._spi.open(bus, chip_select)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"SPI device not found: /dev/spidev{bus}.{chip_select}. "
                "Enable SPI with 'sudo raspi-config nonint do_spi 0' and reboot, "
                "or run 'sudo bash install_driver.sh'."
            ) from exc
        self._spi.max_speed_hz = speed_hz
        self._spi.mode = mode

    def command(self, value: int) -> None:
        self._ensure_open()
        self._spi.xfer2([value & 0xFF])

    def write(self, data: bytes | bytearray | memoryview) -> None:
        self._ensure_open()
        # The compatibility implementation has already proven bytes and
        # bytearray with the supported spidev binding. Preserve them exactly;
        # a caller-provided memoryview remains a buffer without a full copy.
        payload = data.cast("B") if isinstance(data, memoryview) else data
        try:
            # spidev accepts a buffer object here; no full-frame list copy.
            self._spi.writebytes2(payload)
        except AttributeError:
            # Older bindings do not expose writebytes2. Keep fallback chunks
            # bounded rather than constructing one giant Python list.
            view = memoryview(payload).cast("B")
            for offset in range(0, len(view), 4096):
                self._spi.writebytes(view[offset : offset + 4096].tolist())

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._spi.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SPI transport has been closed")
