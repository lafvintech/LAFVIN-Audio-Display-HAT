from __future__ import annotations

from types import SimpleNamespace

from lafvin_hat.hardware.gpio import GpioController
from lafvin_hat.hardware.rpi_platform import RaspberryPiPlatform


class _V1Line:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.values: list[int] = []
        self.value = 0
        self.released = False

    def request(self, **kwargs) -> None:
        self.requests.append(kwargs)
        self.value = kwargs.get("default_val", 0)

    def set_value(self, value: int) -> None:
        self.value = value
        self.values.append(value)

    def get_value(self) -> int:
        return self.value

    def release(self) -> None:
        self.released = True


class _V1Chip:
    def __init__(self) -> None:
        self.lines: dict[int, _V1Line] = {}
        self.closed = False

    def get_line(self, offset: int) -> _V1Line:
        return self.lines.setdefault(offset, _V1Line())

    def close(self) -> None:
        self.closed = True


class _V1Gpiod:
    LINE_REQ_DIR_OUT = "out"
    LINE_REQ_DIR_IN = "in"
    LINE_REQ_FLAG_BIAS_DISABLE = "bias-disabled"

    def __init__(self) -> None:
        self.chips: list[tuple[str, _V1Chip]] = []

    def Chip(self, path: str) -> _V1Chip:
        chip = _V1Chip()
        self.chips.append((path, chip))
        return chip


class _V2Request:
    def __init__(self, offset: int, initial: int) -> None:
        self.offset = offset
        self.value = initial
        self.set_calls: list[tuple[int, int]] = []
        self.released = False

    def set_value(self, offset: int, value: int) -> None:
        self.value = value
        self.set_calls.append((offset, value))

    def get_value(self, _offset: int) -> int:
        return self.value

    def release(self) -> None:
        self.released = True


class _V2Chip:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict, _V2Request]] = []
        self.closed = False

    def request_lines(self, *, consumer: str, config: dict) -> _V2Request:
        offset, settings = next(iter(config.items()))
        request = _V2Request(offset, getattr(settings, "output_value", 0))
        self.requests.append((consumer, config, request))
        return request

    def close(self) -> None:
        self.closed = True


class _V2Settings:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _V2Gpiod:
    LineSettings = _V2Settings
    line = SimpleNamespace(
        Direction=SimpleNamespace(OUTPUT="out", INPUT="in"),
        Value=SimpleNamespace(ACTIVE=1, INACTIVE=0),
        Bias=SimpleNamespace(DISABLED="disabled"),
    )

    def __init__(self) -> None:
        self.chips: list[tuple[str, _V2Chip]] = []

    def Chip(self, path: str) -> _V2Chip:
        chip = _V2Chip()
        self.chips.append((path, chip))
        return chip


def test_gpio_controller_uses_v1_requests_and_releases_lines() -> None:
    gpiod = _V1Gpiod()
    controller = GpioController(
        RaspberryPiPlatform.from_model("Raspberry Pi Zero 2 W"),
        gpiod_module=gpiod,
    )

    output = controller.request_output(13, initial_value=1)
    input_line = controller.request_input(11)
    output.set_value(0)

    chip = gpiod.chips[0][1]
    assert gpiod.chips[0][0] == "/dev/gpiochip0"
    assert chip.lines[27].requests == [
        {"consumer": "lafvin-hat", "type": "out", "default_val": 1}
    ]
    assert chip.lines[17].requests == [
        {
            "consumer": "lafvin-hat",
            "type": "in",
            "flags": "bias-disabled",
        }
    ]
    assert output.get_value() == 0
    assert input_line.get_value() == 0

    controller.close()

    assert chip.lines[27].released is True
    assert chip.lines[17].released is True
    assert chip.closed is True


def test_gpio_controller_uses_v2_requests_on_pi_5() -> None:
    gpiod = _V2Gpiod()
    controller = GpioController(
        RaspberryPiPlatform.from_model("Raspberry Pi 5 Model B Rev 1.1"),
        gpiod_module=gpiod,
    )

    line = controller.request_output(15, initial_value=0, consumer="backlight")
    line.set_value(1)

    path, chip = gpiod.chips[0]
    consumer, config, request = chip.requests[0]
    offset, settings = next(iter(config.items()))
    assert path == "/dev/gpiochip4"
    assert consumer == "backlight"
    assert offset == 22
    assert settings.direction == "out"
    assert settings.output_value == 0
    assert request.set_calls == [(22, 1)]

    controller.close()
    assert request.released is True
    assert chip.closed is True


def test_gpio_controller_uses_gpiochip0_for_pi_3_model_b_plus() -> None:
    gpiod = _V2Gpiod()
    controller = GpioController(
        RaspberryPiPlatform.from_model(
            "Raspberry Pi 3 Model B Plus Rev 1.3"
        ),
        gpiod_module=gpiod,
    )

    line = controller.request_output(15, initial_value=0, consumer="backlight")
    line.set_value(1)

    path, chip = gpiod.chips[0]
    consumer, config, request = chip.requests[0]
    offset, settings = next(iter(config.items()))
    assert path == "/dev/gpiochip0"
    assert consumer == "backlight"
    assert offset == 22
    assert settings.direction == "out"
    assert settings.output_value == 0
    assert request.set_calls == [(22, 1)]

    controller.close()
    assert request.released is True
    assert chip.closed is True


def test_gpio_controller_uses_gpiochip0_for_pi_4_v2_requests() -> None:
    gpiod = _V2Gpiod()
    controller = GpioController(
        RaspberryPiPlatform.from_model("Raspberry Pi 4 Model B Rev 1.5"),
        gpiod_module=gpiod,
    )

    line = controller.request_output(15, initial_value=0, consumer="backlight")
    line.set_value(1)

    path, chip = gpiod.chips[0]
    consumer, config, request = chip.requests[0]
    offset, settings = next(iter(config.items()))
    assert path == "/dev/gpiochip0"
    assert consumer == "backlight"
    assert offset == 22
    assert settings.direction == "out"
    assert settings.output_value == 0
    assert request.set_calls == [(22, 1)]

    controller.close()
    assert request.released is True
    assert chip.closed is True


def test_gpio_v2_input_retries_when_disabled_bias_is_unsupported() -> None:
    class RejectingSettings(_V2Settings):
        def __init__(self, **kwargs) -> None:
            if "bias" in kwargs:
                raise ValueError("bias is unsupported")
            super().__init__(**kwargs)

    gpiod = _V2Gpiod()
    gpiod.LineSettings = RejectingSettings
    controller = GpioController(
        RaspberryPiPlatform.from_model("Raspberry Pi Zero 2 W"),
        gpiod_module=gpiod,
    )

    controller.request_input(11)

    _consumer, config, _request = gpiod.chips[0][1].requests[0]
    _offset, settings = next(iter(config.items()))
    assert settings.direction == "in"
    assert not hasattr(settings, "bias")
