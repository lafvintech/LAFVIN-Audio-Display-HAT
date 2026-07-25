from __future__ import annotations

import pytest

from lafvin_hat.hardware.rpi_platform import (
    RaspberryPiPlatform,
    UnsupportedRaspberryPiError,
)


def test_zero_2_w_uses_gpiochip0_and_supported_board_pin_map() -> None:
    platform = RaspberryPiPlatform.from_model("Raspberry Pi Zero 2 W Rev 1.0")

    assert platform.gpiochip == 0
    assert platform.gpio_device() == "/dev/gpiochip0"
    assert platform.line_offset(13) == 27
    assert platform.line_offset(11) == 17
    assert platform.spi_bus == 0
    assert platform.spi_chip_select == 0
    assert platform.spi_speed_hz == 100_000_000


def test_pi_5_uses_rp1_gpiochip4() -> None:
    platform = RaspberryPiPlatform.from_model("Raspberry Pi 5 Model B Rev 1.1\x00")

    assert platform.gpiochip == 4
    assert platform.gpio_device() == "/dev/gpiochip4"
    assert platform.line_offset(22) == 25


def test_native_platform_rejects_unsupported_board() -> None:
    with pytest.raises(UnsupportedRaspberryPiError, match="Pi Zero 2 W and Raspberry Pi 5"):
        RaspberryPiPlatform.from_model("Radxa Zero 3W")

    with pytest.raises(ValueError, match="BOARD pin"):
        RaspberryPiPlatform.from_model("Raspberry Pi 5").line_offset(1)
