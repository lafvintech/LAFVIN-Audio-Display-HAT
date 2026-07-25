import asyncio
from pathlib import Path
from typing import Any

from lafvin_hat.runtime.diagnostics import HardwareTestFlow, HardwareTestTimings


class BackendStub:
    name = "test"
    display_width = 8
    display_height = 8

    def __init__(self) -> None:
        self.frames: list[bytes] = []
        self.modes: list[str] = []
        self.leds: list[tuple[int, int, int]] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def set_backlight(self, value: int) -> None:
        return None

    async def set_led(self, r: int, g: int, b: int) -> None:
        self.leds.append((r, g, b))

    async def get_button_state(self) -> bool:
        return False

    async def get_battery_state(self) -> None:
        return None

    async def present_frame(
        self,
        rgb565: bytes,
        *,
        width: int,
        height: int,
    ) -> None:
        assert width == self.display_width
        assert height == self.display_height
        self.frames.append(rgb565)

    async def set_declarative_view(
        self,
        view: dict[str, Any] | None,
        *,
        revision: int,
    ) -> None:
        return None

    async def set_display_mode(self, mode: str) -> None:
        self.modes.append(mode)

    def set_event_sink(self, sink: Any) -> None:
        return None

    def state_snapshot(self) -> dict[str, Any]:
        return {}


class UIServiceStub:
    def __init__(self) -> None:
        self.views: list[dict[str, Any]] = []

    async def set_system_view(self, view: dict[str, Any]) -> None:
        self.views.append(view)


class AudioServiceStub:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.tone_count = 0
        self.played_files: list[str] = []
        self.recording_started = False

    async def play_system_tone(self) -> dict[str, Any]:
        self.tone_count += 1
        return {"completed": True}

    async def start_system_recording(
        self,
        *,
        max_duration_sec: int,
    ) -> dict[str, Any]:
        self.recording_started = True
        return {"recording_session": "recording"}

    async def stop_system_recording(
        self,
        recording_session: str,
    ) -> dict[str, Any]:
        assert recording_session == "recording"
        path = self.tmp_path / "loopback.wav"
        path.write_bytes(b"RIFF" + bytes(64))
        return {
            "path": str(path),
            "format": "wav",
            "duration_ms": 100,
            "size_bytes": path.stat().st_size,
        }

    async def play_system_file(self, value: str | Path) -> dict[str, Any]:
        self.played_files.append(str(value))
        return {"completed": True}


def test_hardware_test_flow_runs_to_summary_and_exits(tmp_path: Path) -> None:
    async def scenario() -> None:
        backend = BackendStub()
        ui = UIServiceStub()
        audio = AudioServiceStub(tmp_path)
        flow = HardwareTestFlow(
            backend,  # type: ignore[arg-type]
            ui,  # type: ignore[arg-type]
            audio,
            timings=HardwareTestTimings(
                color_sec=0,
                led_sec=0,
                gesture_timeout_sec=0.5,
                mic_wait_timeout_sec=0.5,
                mic_duration_sec=1,
                feedback_sec=0,
                summary_poll_sec=0.01,
            ),
        )

        await flow.start()

        await _wait_for_text(ui, "Press once")
        assert await flow.handle_event({
            "event": "button.single_clicked",
            "payload": {"context": "shell", "click_count": 1},
        })

        await _wait_for_text(ui, "Press twice")
        assert await flow.handle_event({
            "event": "button.double_clicked",
            "payload": {"context": "shell", "click_count": 2},
        })

        await _wait_for_text(ui, "Press three times")
        assert await flow.handle_event({
            "event": "button.triple_clicked",
            "payload": {"context": "shell", "click_count": 3},
        })

        await _wait_for_text(ui, "Hold button to record")
        assert await flow.handle_event({
            "event": "button.raw_pressed",
            "payload": {"pressed": True},
        })

        await _wait_for_text(ui, "Recording")
        assert await flow.handle_event({
            "event": "button.raw_released",
            "payload": {"pressed": False},
        })

        await _wait_for_phase(flow, "summary")

        assert [result["status"] for result in flow.snapshot()["results"]] == [
            "OK",
            "OK",
            "OK",
            "OK",
            "OK",
        ]
        assert len(backend.frames) >= 6
        assert (255, 0, 0) in backend.leds
        assert (0, 255, 0) in backend.leds
        assert (0, 0, 255) in backend.leds
        assert backend.leds[-1] == (0, 0, 0)
        assert audio.tone_count == 1
        assert audio.recording_started is True
        assert len(audio.played_files) == 1

        assert await flow.handle_event({
            "event": "button.triple_clicked",
            "payload": {"context": "shell", "click_count": 3},
        })
        await asyncio.sleep(0)
        assert flow.active is False

    asyncio.run(scenario())


async def _wait_for_text(ui: UIServiceStub, text: str) -> None:
    await _wait_until(lambda: text in _latest_text(ui))


async def _wait_for_phase(flow: HardwareTestFlow, phase: str) -> None:
    await _wait_until(lambda: flow.snapshot()["phase"] == phase)


async def _wait_until(predicate: Any) -> None:
    deadline = asyncio.get_running_loop().time() + 2.0
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out waiting for condition")


def _latest_text(ui: UIServiceStub) -> str:
    if not ui.views:
        return ""
    view = ui.views[-1]
    return "\n".join(
        component.get("text", "")
        for component in view.get("components", [])
        if isinstance(component, dict)
    )
