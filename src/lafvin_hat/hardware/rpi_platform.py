"""Supported Raspberry Pi platform facts for the LAFVIN HAT board."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEVICE_TREE_MODEL = Path("/proc/device-tree/model")

# BOARD pin numbers mapped to Raspberry Pi BCM GPIO offsets. The supported
# 40-pin Raspberry Pi targets use the same user-facing BCM offsets.
RPI_BOARD_TO_BCM = {
    3: 2,
    5: 3,
    7: 4,
    8: 14,
    10: 15,
    11: 17,
    12: 18,
    13: 27,
    15: 22,
    16: 23,
    18: 24,
    19: 10,
    21: 9,
    22: 25,
    23: 11,
    24: 8,
    26: 7,
    27: 0,
    28: 1,
    29: 5,
    31: 6,
    32: 12,
    33: 13,
    35: 19,
    36: 16,
    37: 26,
    38: 20,
    40: 21,
}


class UnsupportedRaspberryPiError(RuntimeError):
    """Raised when native LAFVIN HAT support is requested on another board."""


@dataclass(frozen=True, slots=True)
class RaspberryPiPlatform:
    """GPIO and SPI facts for one supported Raspberry Pi model family."""

    model: str
    gpiochip: int
    spi_bus: int = 0
    spi_chip_select: int = 0
    spi_speed_hz: int = 100_000_000

    @classmethod
    def detect(cls, model_path: Path = DEVICE_TREE_MODEL) -> "RaspberryPiPlatform":
        try:
            model = model_path.read_bytes().decode(
                "utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise UnsupportedRaspberryPiError(
                "Cannot read Raspberry Pi device model from "
                f"{model_path}. Native LAFVIN HAT hardware supports only "
                "Pi Zero 2 W, Pi 3 Model B+, Pi 4 Model B, and Pi 5."
            ) from exc
        return cls.from_model(model)

    @classmethod
    def from_model(cls, model: str) -> "RaspberryPiPlatform":
        normalized = model.replace("\x00", "").strip()
        if "Raspberry Pi Zero 2" in normalized:
            return cls(model=normalized, gpiochip=0)
        if "Raspberry Pi 3 Model B Plus" in normalized:
            # BCM2837 exposes the 40-pin header through gpiochip0.
            return cls(model=normalized, gpiochip=0)
        if "Raspberry Pi 4 Model B" in normalized:
            # BCM2711 exposes the 40-pin header through gpiochip0.
            return cls(model=normalized, gpiochip=0)
        if "Raspberry Pi 5" in normalized:
            # Pi 5 header GPIO is exposed by RP1 as gpiochip4.
            return cls(model=normalized, gpiochip=4)
        raise UnsupportedRaspberryPiError(
            "Unsupported native LAFVIN HAT platform: "
            f"{normalized or 'unknown'}. Supported boards are Raspberry Pi "
            "Zero 2 W, Raspberry Pi 3 Model B+, Raspberry Pi 4 Model B, and "
            "Raspberry Pi 5."
        )

    def line_offset(self, board_pin: int) -> int:
        try:
            return RPI_BOARD_TO_BCM[board_pin]
        except KeyError as exc:
            raise ValueError(f"Unsupported Raspberry Pi BOARD pin: {board_pin}") from exc

    def gpio_device(self) -> str:
        return f"/dev/gpiochip{self.gpiochip}"
