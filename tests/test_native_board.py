from __future__ import annotations

from lafvin_hat.hardware.native import NativeLafvinHatBoard
from lafvin_hat.hardware.rpi_platform import RaspberryPiPlatform


class _Line:
    def __init__(self, value: int = 0) -> None:
        self.value = value
        self.values: list[int] = []

    def set_value(self, value: int) -> None:
        self.value = value
        self.values.append(value)

    def get_value(self) -> int:
        return self.value


class _Gpio:
    def __init__(self) -> None:
        self.outputs: dict[int, _Line] = {}
        self.inputs: dict[int, _Line] = {}
        self.closed = False

    def request_output(self, pin: int, **_kwargs) -> _Line:
        line = _Line()
        self.outputs[pin] = line
        return line

    def request_input(self, pin: int, **_kwargs) -> _Line:
        line = _Line()
        self.inputs[pin] = line
        return line

    def close(self) -> None:
        self.closed = True


class _Spi:
    def __init__(self) -> None:
        self.commands: list[int] = []
        self.writes: list[bytes] = []
        self.closed = False

    def command(self, value: int) -> None:
        self.commands.append(value)

    def write(self, data) -> None:
        self.writes.append(bytes(data))

    def close(self) -> None:
        self.closed = True


def test_native_board_composes_expected_components_and_cleans_up() -> None:
    gpio = _Gpio()
    spi = _Spi()
    board = NativeLafvinHatBoard(
        platform=RaspberryPiPlatform.from_model("Raspberry Pi 5 Model B Rev 1.1"),
        gpio=gpio,
        spi=spi,
        sleep=lambda _seconds: None,
    )
    try:
        assert set(gpio.outputs) == {7, 13, 15, 16, 18, 22}
        assert set(gpio.inputs) == {11}
        assert board.profile_name == "lafvin-hat-rpi"
        assert board.implementation == "lafvin-native-rpi"
        assert board.display is not None
        assert board.button is not None
        assert board.led is not None
        assert board.backlight is not None
        assert spi.commands[0] == 0x11
        board.display.present_rgb565(b"\x00\x00", width=1, height=1)
    finally:
        board.cleanup()

    assert gpio.closed is True
    assert spi.closed is True
