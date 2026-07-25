from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

from lafvin_hat.runtime.backends import LafvinHatBackend


def _write_external_driver(tmp_path: Path, *, delay_seconds: float = 0) -> Path:
    driver_path = tmp_path / "lafvin_hat_driver.py"
    driver_path.write_text(
        f'''\
import time

DELAY_SECONDS = {delay_seconds!r}


class _Display:
    def __init__(self):
        self.frames = []
        self.active = 0
        self.overlapped = False

    def present_rgb565(self, data, *, width, height):
        self.active += 1
        if self.active > 1:
            self.overlapped = True
        time.sleep(DELAY_SECONDS)
        self.frames.append((data, width, height))
        self.active -= 1


class _Button:
    def bind(self, on_press, on_release):
        self.on_press = on_press
        self.on_release = on_release


class _Led:
    def set(self, red, green, blue):
        self.value = (red, green, blue)


class _Backlight:
    def set(self, value):
        self.value = value


class LafvinHatBoard:
    profile_name = "external-test-board"
    implementation = "external-test"

    def __init__(self):
        self.display = _Display()
        self.button = _Button()
        self.led = _Led()
        self.backlight = _Backlight()
        self.cleaned = False

    def cleanup(self):
        self.cleaned = True
''',
        encoding="utf-8",
    )
    return driver_path


def test_lafvin_hat_backend_uses_lafvin_driver_contract(tmp_path: Path) -> None:
    async def scenario() -> None:
        backend = LafvinHatBackend(_write_external_driver(tmp_path))
        events: list[tuple[str, dict]] = []

        async def sink(name: str, payload: dict) -> None:
            events.append((name, payload))

        backend.set_event_sink(sink)
        await backend.start()
        board = backend._board
        await backend.set_led(300, -1, 20)
        await backend.present_frame(
            bytes(240 * 280 * 2),
            width=240,
            height=280,
        )
        board.button.on_press()
        board.button.on_release()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        snapshot = backend.state_snapshot()
        await backend.stop()

        assert board.backlight.value == 100
        assert board.led.value == (255, 0, 20)
        assert len(board.display.frames) == 1
        assert snapshot["ui"]["frame_sequence"] == 1
        assert snapshot["display_metrics"]["present_count"] == 1
        assert snapshot["display_metrics"]["fps"] == 1
        assert snapshot["display_metrics"]["last_present_ms"] is not None
        assert snapshot["backend"] == "lafvin-hat"
        assert snapshot["device_backend"] == "lafvin-hat"
        assert snapshot["hardware_profile"] == {
            "name": "external-test-board",
            "implementation": "external-test",
        }
        assert backend.requires_linux_audio is True
        assert [name for name, _ in events] == [
            "button.raw_pressed",
            "button.raw_released",
        ]
        assert board.cleaned is True

    asyncio.run(scenario())


def test_lafvin_hat_backend_loads_bundled_board_by_default(monkeypatch) -> None:
    fake_module = ModuleType("lafvin_hat.hardware.lafvin_hat")
    fake_module.LafvinHatBoard = object
    monkeypatch.setitem(
        sys.modules,
        "lafvin_hat.hardware.lafvin_hat",
        fake_module,
    )

    backend = LafvinHatBackend()

    assert backend._load_driver() is fake_module
    assert backend.state_snapshot()["driver_source"] == "bundled"


def test_lafvin_hat_backend_serializes_frame_writes(tmp_path: Path) -> None:
    async def scenario() -> None:
        backend = LafvinHatBackend(
            _write_external_driver(tmp_path, delay_seconds=0.03)
        )
        await backend.start()
        board = backend._board
        started = time.perf_counter()
        try:
            await asyncio.gather(
                backend.present_frame(
                    bytes(240 * 280 * 2),
                    width=240,
                    height=280,
                ),
                backend.present_frame(
                    bytes([0xFF]) * (240 * 280 * 2),
                    width=240,
                    height=280,
                ),
            )
        finally:
            await backend.stop()

        assert board.display.overlapped is False
        assert time.perf_counter() - started >= 0.055

    asyncio.run(scenario())


def test_external_driver_must_export_lafvin_board_contract() -> None:
    legacy_module = ModuleType("legacy_driver")
    legacy_module.OldBoard = object

    with pytest.raises(RuntimeError, match="LafvinHatBoard"):
        LafvinHatBackend._create_board(legacy_module)


def test_unstarted_backend_advertises_native_profile() -> None:
    snapshot = LafvinHatBackend().state_snapshot()

    assert snapshot["hardware_profile"] == {
        "name": "lafvin-hat-rpi",
        "implementation": "lafvin-native-rpi",
    }
