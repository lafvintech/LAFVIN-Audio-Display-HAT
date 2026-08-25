from __future__ import annotations

from pathlib import Path

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


def test_pi_3_model_b_plus_uses_bcm2837_gpiochip0() -> None:
    platform = RaspberryPiPlatform.from_model(
        "Raspberry Pi 3 Model B Plus Rev 1.3\x00"
    )

    assert platform.model == "Raspberry Pi 3 Model B Plus Rev 1.3"
    assert platform.gpiochip == 0
    assert platform.gpio_device() == "/dev/gpiochip0"
    assert platform.line_offset(13) == 27
    assert platform.line_offset(11) == 17
    assert platform.spi_bus == 0
    assert platform.spi_chip_select == 0
    assert platform.spi_speed_hz == 100_000_000


def test_detect_reads_pi_3_model_b_plus_device_tree_model(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model"
    model_path.write_bytes(b"Raspberry Pi 3 Model B Plus Rev 1.3\x00")

    platform = RaspberryPiPlatform.detect(model_path)

    assert platform.model == "Raspberry Pi 3 Model B Plus Rev 1.3"
    assert platform.gpio_device() == "/dev/gpiochip0"


def test_pi_4_model_b_uses_bcm2711_gpiochip0() -> None:
    platform = RaspberryPiPlatform.from_model(
        "Raspberry Pi 4 Model B Rev 1.5\x00"
    )

    assert platform.model == "Raspberry Pi 4 Model B Rev 1.5"
    assert platform.gpiochip == 0
    assert platform.gpio_device() == "/dev/gpiochip0"
    assert platform.line_offset(13) == 27
    assert platform.line_offset(11) == 17
    assert platform.spi_bus == 0
    assert platform.spi_chip_select == 0
    assert platform.spi_speed_hz == 100_000_000


def test_detect_reads_pi_4_device_tree_model(tmp_path: Path) -> None:
    model_path = tmp_path / "model"
    model_path.write_bytes(b"Raspberry Pi 4 Model B Rev 1.5\x00")

    platform = RaspberryPiPlatform.detect(model_path)

    assert platform.model == "Raspberry Pi 4 Model B Rev 1.5"
    assert platform.gpio_device() == "/dev/gpiochip0"


def test_pi_5_uses_rp1_gpiochip4() -> None:
    platform = RaspberryPiPlatform.from_model("Raspberry Pi 5 Model B Rev 1.1\x00")

    assert platform.gpiochip == 4
    assert platform.gpio_device() == "/dev/gpiochip4"
    assert platform.line_offset(22) == 25


def test_native_platform_rejects_unsupported_board() -> None:
    with pytest.raises(
        UnsupportedRaspberryPiError,
        match="Raspberry Pi 4 Model B",
    ):
        RaspberryPiPlatform.from_model("Radxa Zero 3W")

    with pytest.raises(UnsupportedRaspberryPiError):
        RaspberryPiPlatform.from_model("Raspberry Pi 400 Rev 1.0")

    with pytest.raises(UnsupportedRaspberryPiError):
        RaspberryPiPlatform.from_model("Raspberry Pi 3 Model B Rev 1.2")

    with pytest.raises(UnsupportedRaspberryPiError):
        RaspberryPiPlatform.from_model("Raspberry Pi 3 Model A Plus Rev 1.0")

    with pytest.raises(ValueError, match="BOARD pin"):
        RaspberryPiPlatform.from_model("Raspberry Pi 5").line_offset(1)
