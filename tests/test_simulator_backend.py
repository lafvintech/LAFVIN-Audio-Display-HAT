import asyncio
from pathlib import Path

from lafvin_hat.runtime.backends import SimulatorBackend


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


def test_simulator_frontend_supports_system_page_view() -> None:
    html = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "lafvin_hat"
        / "runtime"
        / "backends"
        / "simulator_index.html"
    ).read_text(encoding="utf-8")

    assert 'view.kind === "system_page"' in html
    assert ".system-page" in html


def test_simulator_frontend_supports_light_home_list() -> None:
    html = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "lafvin_hat"
        / "runtime"
        / "backends"
        / "simulator_index.html"
    ).read_text(encoding="utf-8")

    assert 'view.kind === "list"' in html
    assert ".screen.home" in html
    assert "#5c96ff" in html


def test_simulator_frontend_supports_view_action_bar() -> None:
    html = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "lafvin_hat"
        / "runtime"
        / "backends"
        / "simulator_index.html"
    ).read_text(encoding="utf-8")

    assert "appendViewActions(view)" in html
    assert ".view-actions" in html
