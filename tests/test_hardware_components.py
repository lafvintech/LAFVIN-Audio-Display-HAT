from __future__ import annotations

import threading

from lafvin_hat.hardware.backlight import Backlight
from lafvin_hat.hardware.button import Button
from lafvin_hat.hardware.rgb_led import RgbLed


class _Pwm:
    def __init__(self, _write, *, frequency_hz: int, stop_value: int) -> None:
        self.frequency_hz = frequency_hz
        self.stop_value = stop_value
        self.started: list[float] = []
        self.duties: list[float] = []
        self.stopped = False

    def start(self, duty_cycle: float) -> None:
        self.started.append(duty_cycle)

    def change_duty_cycle(self, duty_cycle: float) -> None:
        self.duties.append(duty_cycle)

    def stop(self) -> None:
        self.stopped = True


class _Line:
    def __init__(self, value: int = 0) -> None:
        self.value = value
        self.values: list[int] = []

    def set_value(self, value: int) -> None:
        self.value = value
        self.values.append(value)

    def get_value(self) -> int:
        return self.value


def test_rgb_led_and_backlight_preserve_active_low_pwm_mapping() -> None:
    created: list[_Pwm] = []

    def pwm_factory(*args, **kwargs):
        pwm = _Pwm(*args, **kwargs)
        created.append(pwm)
        return pwm

    led = RgbLed(_Line(), _Line(), _Line(), pwm_factory=pwm_factory)
    backlight = Backlight(_Line(), pwm_factory=pwm_factory)
    led.set(255, 128, 0)
    backlight.set(60)

    assert [pwm.frequency_hz for pwm in created] == [100, 100, 100, 1000]
    assert [pwm.started for pwm in created] == [[100], [100], [100], [100]]
    assert created[0].duties == [0]
    assert created[1].duties == [100 - 128 / 255 * 100]
    assert created[2].duties == [100]
    assert created[3].duties == [40]

    led.close()
    backlight.close()
    assert all(pwm.stopped for pwm in created)


def test_button_emits_transition_callbacks_and_stops() -> None:
    line = _Line()
    pressed = threading.Event()
    released = threading.Event()
    button = Button(line, poll_interval_sec=0.001)
    button.bind(pressed.set, released.set)
    button.start()
    try:
        line.value = 1
        assert pressed.wait(0.2)
        line.value = 0
        assert released.wait(0.2)
    finally:
        button.stop()
