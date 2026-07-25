from __future__ import annotations

from lafvin_hat.hardware.display import St7789Display
from lafvin_hat.hardware.spi import SpiTransport


class _Line:
    def __init__(self) -> None:
        self.values: list[int] = []

    def set_value(self, value: int) -> None:
        self.values.append(value)


class _Spi:
    def __init__(self) -> None:
        self.commands: list[int] = []
        self.writes: list[bytes] = []

    def command(self, value: int) -> None:
        self.commands.append(value)

    def write(self, data) -> None:
        self.writes.append(bytes(data))


def test_display_preserves_initialization_sequence_and_window_offset() -> None:
    spi = _Spi()
    dc = _Line()
    reset = _Line()
    sleeps: list[float] = []
    display = St7789Display(
        spi,
        data_command_line=dc,
        reset_line=reset,
        sleep=sleeps.append,
    )

    display.initialize()
    assert reset.values == [1, 0, 1]
    assert sleeps[:4] == [0.1, 0.1, 0.12, 0.12]
    assert spi.commands[:3] == [0x11, 0x36, 0x3A]
    assert spi.commands[-2:] == [0x21, 0x29]

    spi.commands.clear()
    spi.writes.clear()
    display.present_rgb565(b"\xf8\x00\x07\xe0", width=2, height=1)

    assert spi.commands == [0x2A, 0x2B, 0x2C]
    assert spi.writes == [
        b"\x00\x00\x00\x01",
        b"\x00\x14\x00\x14",
        b"\xf8\x00\x07\xe0",
    ]


def test_spi_transport_uses_buffer_fast_path_without_list_copy() -> None:
    class FakeSpiDevice:
        def __init__(self) -> None:
            self.opened: tuple[int, int] | None = None
            self.payload = None
            self.max_speed_hz = None
            self.mode = None
            self.closed = False

        def open(self, bus: int, chip_select: int) -> None:
            self.opened = (bus, chip_select)

        def xfer2(self, _data) -> None:
            pass

        def writebytes2(self, data) -> None:
            self.payload = data

        def close(self) -> None:
            self.closed = True

    device = FakeSpiDevice()
    transport = SpiTransport(
        bus=0,
        chip_select=0,
        speed_hz=100_000_000,
        spi_factory=lambda: device,
    )
    payload = bytes(32)
    transport.write(payload)
    transport.close()

    assert device.opened == (0, 0)
    assert device.payload is payload
    assert device.max_speed_hz == 100_000_000
    assert device.mode == 0
    assert device.closed is True
