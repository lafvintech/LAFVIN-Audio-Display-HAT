import asyncio
from pathlib import Path

from lafvin_hat.ai import FakeAIProvider, Message, StreamingSpeechPipeline
from lafvin_hat.runtime.audio import AudioService, FakeAudioBackend
from lafvin_hat.runtime.events import EventBus


class VoiceAppStub:
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
        assert app_id == "dev.lafvin.voice-flow"
        assert session_token == "session"
        assert permission in {"microphone", "speaker"}
        return self.root


def test_voice_turn_flows_from_recording_through_streamed_playback(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        audio_backend = FakeAudioBackend()
        audio = AudioService(
            VoiceAppStub(tmp_path),  # type: ignore[arg-type]
            EventBus(),
            audio_backend,
            temp_root=tmp_path / "recordings",
        )
        provider = FakeAIProvider(
            transcript="What is the voice flow?",
            response="Audio works. Streaming works too.",
            chunk_size=4,
        )
        await audio.start()
        try:
            recording = await audio.start_recording(
                "dev.lafvin.voice-flow",
                "session",
                10,
            )
            recorded = await audio.stop_recording(
                "dev.lafvin.voice-flow",
                "session",
                recording["recording_session"],
            )
            transcript = await provider.transcribe(recorded["path"])
            streamed: list[str] = []

            async def on_text(text: str) -> None:
                streamed.append(text)

            async def play(path: Path) -> None:
                await audio.play_file(
                    "dev.lafvin.voice-flow",
                    "session",
                    str(path),
                )

            result = await StreamingSpeechPipeline(
                provider,
                provider,
            ).run(
                [Message("user", transcript)],
                on_text=on_text,
                play_audio=play,
                output_directory=tmp_path / "tts",
            )

            assert transcript == "What is the voice flow?"
            assert "".join(streamed) == result
            assert provider.synthesized_texts == [
                "Audio works.",
                "Streaming works too.",
            ]
            assert len(audio_backend.played_paths) == 2
        finally:
            await audio.stop()

    asyncio.run(scenario())
