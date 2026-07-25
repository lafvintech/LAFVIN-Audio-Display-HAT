import asyncio
import wave
from pathlib import Path

import pytest

from lafvin_hat.ai import (
    AudioResult,
    FakeAIProvider,
    Message,
    PipelineStageError,
    SentenceSplitter,
    StreamingSpeechPipeline,
    TTSQueue,
)


def test_sentence_splitter_handles_stream_boundaries() -> None:
    splitter = SentenceSplitter()

    assert splitter.feed("Hello wor") == []
    assert splitter.feed("ld. Next") == ["Hello world."]
    assert splitter.feed(" sentence!") == ["Next sentence!"]
    assert splitter.flush() is None


def test_sentence_splitter_handles_chinese_punctuation() -> None:
    splitter = SentenceSplitter()

    assert splitter.feed("你好。下一") == ["你好。"]
    assert splitter.feed("句！还有吗？") == ["下一句！", "还有吗？"]
    assert splitter.flush() is None


def test_fake_record_llm_tts_playback_flow(tmp_path: Path) -> None:
    async def scenario() -> None:
        recording = tmp_path / "recording.wav"
        recording.write_bytes(b"RIFFfake")
        provider = FakeAIProvider(
            transcript="hello",
            response="First sentence. Second sentence!",
            chunk_size=5,
        )
        transcript = await provider.transcribe(recording)
        chunks: list[str] = []
        played: list[Path] = []

        async def on_text(value: str) -> None:
            chunks.append(value)

        async def play_audio(path: Path) -> None:
            assert path.is_file()
            played.append(path)

        pipeline = StreamingSpeechPipeline(provider, provider)
        result = await pipeline.run(
            [Message("user", transcript)],
            on_text=on_text,
            play_audio=play_audio,
            output_directory=tmp_path / "tts",
        )

        assert transcript == "hello"
        assert result == "First sentence. Second sentence!"
        assert "".join(chunks) == result
        assert provider.synthesized_texts == [
            "First sentence.",
            "Second sentence!",
        ]
        assert len(played) == 2
        with wave.open(str(played[0]), "rb") as audio:
            samples = audio.readframes(audio.getnframes())
        assert any(samples)

    asyncio.run(scenario())


def test_tts_worker_failure_is_reported_without_queue_deadlock(
    tmp_path: Path,
) -> None:
    class FailingTTS:
        async def synthesize(
            self,
            text: str,
            *,
            output_path: str | Path | None = None,
        ) -> AudioResult:
            raise TimeoutError(f"network timeout for {text}")

    async def scenario() -> None:
        provider = FakeAIProvider(
            response="One. Two. Three. Four. Five. Six.",
            chunk_size=4,
        )
        pipeline = StreamingSpeechPipeline(provider, FailingTTS())

        with pytest.raises(
            PipelineStageError,
            match="TTS synthesis failed",
        ) as caught:
            await asyncio.wait_for(
                pipeline.run(
                    [Message("user", "hello")],
                    on_text=_ignore_text,
                    play_audio=_ignore_audio,
                    output_directory=tmp_path / "tts-failure",
                ),
                timeout=1,
            )

        assert caught.value.stage == "tts_synthesize"
        assert caught.value.sequence == 1

    asyncio.run(scenario())


def test_tts_synthesizes_next_sentence_during_playback(
    tmp_path: Path,
) -> None:
    class PrefetchTTS:
        def __init__(self) -> None:
            self.first_playing = asyncio.Event()
            self.second_synthesized = asyncio.Event()

        async def synthesize(
            self,
            text: str,
            *,
            output_path: str | Path | None = None,
        ) -> AudioResult:
            assert output_path is not None
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
            if text == "Second.":
                await asyncio.wait_for(
                    self.first_playing.wait(),
                    timeout=1,
                )
                self.second_synthesized.set()
            return AudioResult(path)

    async def scenario() -> None:
        provider = PrefetchTTS()
        played: list[str] = []

        async def play_audio(path: Path) -> None:
            played.append(path.read_text())
            if len(played) == 1:
                provider.first_playing.set()
                await asyncio.wait_for(
                    provider.second_synthesized.wait(),
                    timeout=1,
                )

        queue = TTSQueue(
            provider,
            play_audio,
            output_directory=tmp_path / "tts-prefetch",
        )
        await queue.put("First.")
        await queue.put("Second.")
        await queue.finish()

        assert played == ["First.", "Second."]

    asyncio.run(scenario())


async def _ignore_text(_value: str) -> None:
    return None


async def _ignore_audio(_path: Path) -> None:
    return None
