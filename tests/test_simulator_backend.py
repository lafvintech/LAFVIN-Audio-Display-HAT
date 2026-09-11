import asyncio
import json
from pathlib import Path

import pytest

from lafvin_hat.runtime.backends import simulator as simulator_module
from lafvin_hat.runtime.backends import SimulatorBackend


def _frontend_html() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "lafvin_hat"
        / "runtime"
        / "backends"
        / "simulator_index.html"
    ).read_text(encoding="utf-8")


def test_simulator_state_and_events() -> None:
    async def scenario() -> None:
        backend = SimulatorBackend(web_enabled=False)
        events: list[tuple[str, dict]] = []

        async def sink(name: str, payload: dict) -> None:
            events.append((name, payload))

        backend.set_event_sink(sink)
        await backend.start()
        await backend.inject_button(True)
        await backend.inject_button(False)
        await backend.set_led(300, -10, 20)
        await backend.set_backlight(150)
        await backend.present_frame(
            bytes(240 * 280 * 2),
            width=240,
            height=280,
        )
        await backend.set_declarative_view(
            {"kind": "text", "text": "Hello"},
            revision=1,
        )
        await backend.set_simulated_state(
            battery_level=42,
            charging=True,
            network_online=False,
        )
        snapshot = backend.state_snapshot()
        await backend.stop()

        assert snapshot["button_pressed"] is False
        assert snapshot["led"] == {"r": 255, "g": 0, "b": 20}
        assert snapshot["backlight"] == 100
        assert snapshot["battery"] == {"level": 42, "charging": True}
        assert snapshot["network"] == {"online": False}
        assert snapshot["display_metrics"]["present_count"] == 1
        assert snapshot["display_metrics"]["fps"] == 1
        assert snapshot["display_metrics"]["last_present_ms"] is not None
        assert snapshot["ui"] == {
            "mode": "declarative",
            "revision": 1,
            "view": {"kind": "text", "text": "Hello"},
            "frame_sequence": 1,
        }
        assert [name for name, _ in events] == [
            "button.raw_pressed",
            "button.raw_released",
            "battery.changed",
            "network.changed",
        ]

    asyncio.run(scenario())


def test_simulator_injects_shortcuts_through_raw_button_events(monkeypatch) -> None:
    async def scenario() -> None:
        backend = SimulatorBackend(web_enabled=False)
        events: list[tuple[str, dict]] = []

        async def sink(name: str, payload: dict) -> None:
            events.append((name, payload))

        backend.set_event_sink(sink)
        monkeypatch.setattr(simulator_module, "_SIMULATED_CLICK_PRESS_SEC", 0)
        monkeypatch.setattr(simulator_module, "_SIMULATED_CLICK_GAP_SEC", 0)
        monkeypatch.setattr(simulator_module, "_SIMULATED_GESTURE_SETTLE_SEC", 0)

        await backend.inject_clicks(3)

        assert backend.state_snapshot()["button_pressed"] is False
        assert [name for name, _payload in events] == [
            "button.raw_pressed",
            "button.raw_released",
            "button.raw_pressed",
            "button.raw_released",
            "button.raw_pressed",
            "button.raw_released",
        ]

        with pytest.raises(ValueError, match="1, 2, or 3"):
            await backend.inject_clicks(4)

    asyncio.run(scenario())


def test_simulator_http_gesture_shortcut_uses_click_injection(monkeypatch) -> None:
    async def scenario() -> None:
        backend = SimulatorBackend(port=0)
        events: list[str] = []

        async def sink(name: str, _payload: dict) -> None:
            events.append(name)

        backend.set_event_sink(sink)
        monkeypatch.setattr(simulator_module, "_SIMULATED_CLICK_PRESS_SEC", 0)
        monkeypatch.setattr(simulator_module, "_SIMULATED_CLICK_GAP_SEC", 0)
        monkeypatch.setattr(simulator_module, "_SIMULATED_GESTURE_SETTLE_SEC", 0)
        await backend.start()
        try:
            body = json.dumps({"clicks": 2}).encode("utf-8")
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                backend.bound_port,
            )
            writer.write(
                b"POST /api/gesture HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                + body
            )
            await writer.drain()
            response = await reader.read()

            assert response.startswith(b"HTTP/1.1 200 OK\r\n")
            assert events == [
                "button.raw_pressed",
                "button.raw_released",
                "button.raw_pressed",
                "button.raw_released",
            ]
        finally:
            await backend.stop()

    asyncio.run(scenario())


def test_simulator_frontend_uses_one_canvas_for_every_ui_mode() -> None:
    html = _frontend_html()

    assert '<canvas id="display"' in html
    assert 'fetch("/api/frame"' in html
    assert 'if (uiMode === "raw_frame")' in html
    assert "function renderView(" not in html
    assert 'view.kind === "system_page"' not in html


def test_simulator_frontend_preserves_native_display_dimensions() -> None:
    html = _frontend_html()

    assert 'width="240" height="280"' in html
    assert "width: 240px;" in html
    assert "height: 280px;" in html
    assert "width: 232px;" not in html
    assert "height: 272px;" not in html


def test_simulator_frontend_uses_smooth_hidpi_canvas_rendering() -> None:
    html = _frontend_html()

    assert "image-rendering: auto;" in html
    assert "window.devicePixelRatio" in html
    assert 'document.createElement("canvas")' in html
    assert "nativeFrameContext.putImageData(image, 0, 0);" in html
    assert "displayContext.imageSmoothingEnabled = true;" in html
    assert 'displayContext.imageSmoothingQuality = "high";' in html
    assert "displayContext.drawImage(nativeFrameCanvas" in html
    assert "image-rendering: pixelated;" not in html


def test_simulator_frontend_exposes_gesture_shortcuts_and_raw_button() -> None:
    html = _frontend_html()

    assert 'data-clicks="1"' in html
    assert 'data-clicks="2"' in html
    assert 'data-clicks="3"' in html
    assert 'api("/api/gesture"' in html
    assert "tripleShortcutAvailable" in html
    assert 'id="physical-button"' in html
    assert 'api("/api/button"' in html
