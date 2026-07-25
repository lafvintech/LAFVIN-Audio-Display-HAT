import asyncio
from pathlib import Path

import pytest

from lafvin_hat.runtime.audio import AudioService, FakeAudioBackend
from lafvin_hat.runtime.events import EventBus
from lafvin_hat.runtime.ipc.protocol import ProtocolError


class AuthorizedAudioApp:
    def __init__(self, root: Path) -> None:
        self.root = root

    async def authorize(
        self,
        app_id: str,
        session_token: str,
        *,
        permission: str,
        require_foreground: bool = False,
        ui_mode: str | None = None,
    ) -> Path:
        assert app_id == "dev.lafvin.audio"
        assert session_token == "session"
        assert permission in {"microphone", "speaker"}
        return self.root


def test_audio_record_play_volume_and_lifecycle(tmp_path: Path) -> None:
    async def scenario() -> None:
        backend = FakeAudioBackend()
        events = EventBus()
        service = AudioService(
            AuthorizedAudioApp(tmp_path),  # type: ignore[arg-type]
            events,
            backend,
            temp_root=tmp_path / "runtime-audio",
        )
        await service.start()
        try:
            recording = await service.start_recording(
                "dev.lafvin.audio",
                "session",
                10,
            )
            result = await service.stop_recording(
                "dev.lafvin.audio",
                "session",
                recording["recording_session"],
            )
            path = Path(result["path"])
            assert path.is_file()
            assert result["format"] == "wav"
            assert result["size_bytes"] > 44
            assert (
                service.snapshot()["metrics"]["last_recording_duration_ms"]
                is not None
            )

            played = await service.play_file(
                "dev.lafvin.audio",
                "session",
                str(path),
            )
            assert played["completed"] is True
            assert backend.played_paths == [path]
            metrics = service.snapshot()["metrics"]
            assert metrics["recording_count"] == 1
            assert metrics["playback_count"] == 1
            assert metrics["last_playback_duration_ms"] is not None

            assert (
                await service.set_volume(
                    "dev.lafvin.audio",
                    "session",
                    120,
                )
            ) == {"value": 100}
            assert await service.get_system_volume() == 100
            assert await service.set_system_volume(-20) == 0
            assert service.snapshot()["volume"] == 0
            await events.emit(
                "app.foreground_revoked",
                {"app_id": "dev.lafvin.audio"},
                app_id="dev.lafvin.audio",
            )
            await asyncio.sleep(0)
            assert service.snapshot()["recording_app_id"] is None
            assert service.snapshot()["playing_app_id"] is None
            assert service.snapshot()["recording_format"] == "fake-wav"
            metrics = service.snapshot()["metrics"]
            assert metrics["interrupted_recording_count"] == 0
            assert metrics["interrupted_playback_count"] == 0
        finally:
            await service.stop()

    asyncio.run(scenario())


def test_audio_system_record_play_and_tone(tmp_path: Path) -> None:
    async def scenario() -> None:
        backend = FakeAudioBackend()
        service = AudioService(
            AuthorizedAudioApp(tmp_path),  # type: ignore[arg-type]
            EventBus(),
            backend,
            temp_root=tmp_path / "runtime-audio",
        )
        await service.start()
        try:
            recording = await service.start_system_recording(
                max_duration_sec=1,
            )
            assert service.snapshot()["recording_app_id"] == "system.diagnostics"
            result = await service.stop_system_recording(
                recording["recording_session"],
            )
            assert Path(result["path"]).is_file()
            assert service.snapshot()["recording_app_id"] is None

            played = await service.play_system_file(result["path"])
            assert played["completed"] is True
            await service.play_system_tone(duration_ms=20)

            assert len(backend.played_paths) == 2
            assert backend.played_paths[-1].name == "speaker-test.wav"
            metrics = service.snapshot()["metrics"]
            assert metrics["recording_count"] == 1
            assert metrics["playback_count"] == 2
        finally:
            await service.stop()

    asyncio.run(scenario())


def test_audio_volume_feedback_tone_is_runtime_owned(tmp_path: Path) -> None:
    async def scenario() -> None:
        backend = FakeAudioBackend()
        service = AudioService(
            AuthorizedAudioApp(tmp_path),  # type: ignore[arg-type]
            EventBus(),
            backend,
            temp_root=tmp_path / "runtime-audio",
        )
        await service.start()
        try:
            result = await service.play_feedback_tone(
                "dev.lafvin.audio",
                "session",
                kind="volume",
            )

            assert result["completed"] is True
            assert result["kind"] == "volume"
            assert len(backend.played_paths) == 1
            assert backend.played_paths[0].name.startswith("feedback-volume-")
            assert not backend.played_paths[0].exists()

            with pytest.raises(ProtocolError) as exc_info:
                await service.play_feedback_tone(
                    "dev.lafvin.audio",
                    "session",
                    kind="unsupported",
                )
            assert exc_info.value.code == "INVALID_REQUEST"
        finally:
            await service.stop()

    asyncio.run(scenario())
