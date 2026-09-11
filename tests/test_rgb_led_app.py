from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "rgb_led" / "main.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "lafvin_rgb_led_app",
        MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ClientStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def request(
        self,
        method: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.calls.append((method, dict(params or {})))
        return {}


class AppStub:
    def __init__(self) -> None:
        self.app_id = "dev.lafvin.rgb-led"
        self.session_token = "session-token"
        self.client = ClientStub()


def test_gradient_rgb_walks_a_full_hue_cycle() -> None:
    app = _load_module()

    start = app.gradient_rgb(0.0, period_sec=8.0)
    quarter = app.gradient_rgb(2.0, period_sec=8.0)
    half = app.gradient_rgb(4.0, period_sec=8.0)
    wrapped = app.gradient_rgb(8.0, period_sec=8.0)

    assert start == app.rgb_from_hue(0.0)
    assert quarter == app.rgb_from_hue(0.25)
    assert half == app.rgb_from_hue(0.5)
    assert wrapped == start
    assert len({start, quarter, half}) == 3
    assert all(0 <= channel <= 255 for channel in start + quarter + half)


def test_single_click_enters_palette_and_cycles_colors() -> None:
    app = _load_module()
    lamp = app.RgbLamp(started_at=10.0)

    first = lamp.on_single_click(11.0)
    second = lamp.on_single_click(12.0)
    third = lamp.on_single_click(13.0)

    assert lamp.mode == app.MODE_PALETTE
    assert first == app.PALETTE[0]
    assert second == app.PALETTE[1]
    assert third == app.PALETTE[2]
    assert lamp.color_at(20.0) == app.PALETTE[2]


def test_palette_wraps_and_double_click_restarts_gradient() -> None:
    app = _load_module()
    lamp = app.RgbLamp(started_at=0.0)
    lamp.mode = app.MODE_PALETTE
    lamp.palette_index = len(app.PALETTE) - 1

    wrapped = lamp.on_single_click(1.0)
    restarted = lamp.on_double_click(5.0)

    assert wrapped == app.PALETTE[0]
    assert lamp.mode == app.MODE_GRADIENT
    assert lamp.gradient_started_at == 5.0
    assert restarted == app.gradient_rgb(0.0)
    assert lamp.color_at(5.0) == app.gradient_rgb(0.0)
    assert lamp.color_at(7.0) == app.gradient_rgb(2.0)


def test_set_led_sends_integer_rgb_ipc() -> None:
    async def scenario() -> None:
        app_module = _load_module()
        fake_app = AppStub()

        await app_module.set_led(fake_app, (12, 34, 56))
        await app_module.set_led(fake_app, app_module.LED_OFF)

        assert fake_app.client.calls == [
            (
                "device.set_led",
                {
                    "app_id": "dev.lafvin.rgb-led",
                    "session_token": "session-token",
                    "r": 12,
                    "g": 34,
                    "b": 56,
                },
            ),
            (
                "device.set_led",
                {
                    "app_id": "dev.lafvin.rgb-led",
                    "session_token": "session-token",
                    "r": 0,
                    "g": 0,
                    "b": 0,
                },
            ),
        ]

    asyncio.run(scenario())
