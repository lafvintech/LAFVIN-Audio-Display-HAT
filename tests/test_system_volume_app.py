from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "system_volume" / "main.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "lafvin_system_volume_app",
        MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AudioStub:
    def __init__(self, volume: int) -> None:
        self.volume = volume
        self.feedback_tones: list[str] = []
        self.stop_count = 0

    async def get_volume(self) -> int:
        return self.volume

    async def set_volume(self, value: int) -> int:
        self.volume = max(0, min(100, int(value)))
        return self.volume

    async def play_feedback_tone(self, kind: str) -> dict[str, object]:
        self.feedback_tones.append(kind)
        return {"kind": kind, "completed": True}

    async def stop(self) -> dict[str, object]:
        self.stop_count += 1
        return {}


class AppStub:
    def __init__(self, volume: int) -> None:
        self.audio = AudioStub(volume)


def test_system_volume_app_builds_volume_page() -> None:
    app = _load_module()

    canvas = app.build_volume_canvas(70)
    frame = canvas.render()

    assert len(frame) == 240 * 280 * 2
    assert canvas.image.getpixel((45, 189)) == canvas.theme.button
    assert canvas.image.getpixel((141, 189)) == canvas.theme.button_selected


def test_system_volume_app_applies_selected_adjustment() -> None:
    async def scenario() -> None:
        app_module = _load_module()
        fake_app = AppStub(70)

        assert (
            await app_module.apply_selected(fake_app, app_module.ACTION_UP)
            == 80
        )
        assert (
            await app_module.apply_selected(fake_app, app_module.ACTION_DOWN)
            == 70
        )

    asyncio.run(scenario())


def test_system_volume_app_clamps_volume() -> None:
    async def scenario() -> None:
        app_module = _load_module()

        high = AppStub(100)
        low = AppStub(0)

        assert (
            await app_module.apply_selected(high, app_module.ACTION_UP)
            == 100
        )
        assert (
            await app_module.apply_selected(low, app_module.ACTION_DOWN)
            == 0
        )

    asyncio.run(scenario())


def test_system_volume_app_debounces_feedback_preview() -> None:
    async def scenario() -> None:
        app_module = _load_module()
        fake_app = AppStub(70)

        preview = await app_module.schedule_volume_preview(
            fake_app,
            None,
            delay_sec=0.05,
        )
        await asyncio.sleep(0.02)
        preview = await app_module.schedule_volume_preview(
            fake_app,
            preview,
            delay_sec=0.01,
        )
        await asyncio.sleep(0.03)

        assert fake_app.audio.feedback_tones == ["volume"]
        assert fake_app.audio.stop_count == 1

        await app_module.cancel_volume_preview(fake_app, preview)

    asyncio.run(scenario())


def test_system_volume_app_cancels_active_feedback_before_stopping_audio(
) -> None:
    class BlockingAudio(AudioStub):
        def __init__(self) -> None:
            super().__init__(70)
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()
            self.events: list[str] = []

        async def play_feedback_tone(self, kind: str) -> dict[str, object]:
            self.feedback_tones.append(kind)
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.events.append("preview_cancelled")
                self.cancelled.set()
                raise

        async def stop(self) -> dict[str, object]:
            self.events.append("audio_stopped")
            return await super().stop()

    async def scenario() -> None:
        app_module = _load_module()
        fake_app = AppStub(70)
        audio = BlockingAudio()
        fake_app.audio = audio

        preview = await app_module.schedule_volume_preview(
            fake_app,
            None,
            delay_sec=0,
        )
        await asyncio.wait_for(audio.started.wait(), timeout=1)
        await app_module.cancel_volume_preview(fake_app, preview)

        assert preview.cancelled()
        assert audio.cancelled.is_set()
        assert audio.stop_count == 1
        assert audio.events == ["preview_cancelled", "audio_stopped"]

    asyncio.run(scenario())
