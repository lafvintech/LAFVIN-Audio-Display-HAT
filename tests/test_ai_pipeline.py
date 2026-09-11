import asyncio
import logging
import wave
from pathlib import Path

import pytest

from lafvin_hat.ai import (
    AudioResult,
    FakeAIProvider,
    FakeTTSProvider,
    LLMChunk,
    Message,
    PipelineStageError,
    SentenceSplitter,
    SpeechSegment,
    StreamingSpeechPipeline,
    TTSQueue,
    prepare_text_for_speech,
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


def test_sentence_splitter_keeps_list_numbers_decimals_and_urls_together(
) -> None:
    splitter = SentenceSplitter()

    assert splitter.feed("1. First item. Version 2.0 works.") == [
        "1. First item.",
    ]
    assert splitter.feed(" See https://example.com/docs.") == [
        "Version 2.0 works.",
    ]
    assert splitter.flush() == "See https://example.com/docs."


def test_sentence_splitter_defers_stream_trailing_periods_in_numbers() -> None:
    splitter = SentenceSplitter()

    assert splitter.feed("Model Rev 1.") == []
    assert splitter.feed("0 uses IP 192.") == []
    assert splitter.feed("168.3.") == []
    assert splitter.feed("2. CPU usage is 13.") == [
        "Model Rev 1.0 uses IP 192.168.3.2.",
    ]
    assert splitter.feed("3 percent.") == []
    assert splitter.flush() == "CPU usage is 13.3 percent."


def test_sentence_splitter_reports_absolute_display_offsets() -> None:
    splitter = SentenceSplitter()

    first = splitter.feed_parts(" 你好。下一")
    second = splitter.feed_parts("句！ 结尾")
    remainder = splitter.flush_part()

    assert [(part.text, part.display_end) for part in first] == [("你好。", 4)]
    assert [(part.text, part.display_end) for part in second] == [("下一句！", 8)]
    assert remainder is not None
    assert (remainder.text, remainder.display_end) == ("结尾", 11)


def test_prepare_text_for_speech_removes_markdown_and_urls() -> None:
    source = """## **答案**
- 请查看 [官方文档](https://example.com/docs)。
- 运行 `pip install package`。👍
***
"""

    assert prepare_text_for_speech(source) == (
        "答案 请查看 官方文档。 运行 pip install package。"
    )


def test_prepare_text_for_speech_skips_symbol_only_text() -> None:
    assert prepare_text_for_speech("**\n***\n👍") == ""


def test_prepare_text_for_speech_pronounces_numeric_periods() -> None:
    assert prepare_text_for_speech(
        "IP 192.168.3.2. Rev 1.0, CPU 13.3 percent."
    ) == (
        "IP 192 dot 168 dot 3 dot 2. Rev 1 point 0, "
        "CPU 13 point 3 percent."
    )
    assert prepare_text_for_speech("地址 192.168.3.2，温度 47.2。") == (
        "地址 192点168点3点2，温度 47点2。"
    )


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


def test_pipeline_keeps_first_sentence_fast_and_combines_later_sentences(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        response = "First response. Second short. Third short. Final sentence."
        provider = FakeAIProvider(response=response, chunk_size=3)

        result = await StreamingSpeechPipeline(provider, provider).run(
            [Message("user", "hello")],
            on_text=_ignore_text,
            play_audio=_ignore_audio,
            output_directory=tmp_path / "tts-medium-chunks",
            speech_chunk_target_units=120,
            speech_chunk_max_sentences=2,
            speech_chunk_hard_limit_units=180,
        )

        assert result == response
        assert provider.synthesized_texts == [
            "First response.",
            "Second short. Third short.",
            "Final sentence.",
        ]

    asyncio.run(scenario())


def test_pi_zero_status_stream_becomes_four_coherent_speech_chunks(
    tmp_path: Path,
) -> None:
    class LoggedChunkLLM:
        async def stream_chat(self, _messages, **_kwargs):
            for text in (
                "Here is the current system status.",
                " The device is a Raspberry Pi Zero 2 W Rev 1.",
                "0, with hostname pi2w and IP address 192.",
                "168.3.",
                "2. Runtime uptime is about 227 seconds.",
                " CPU usage is 13.",
                "3 percent, memory usage is 68.",
                "6 percent, temperature is 47.",
                "2 degrees Celsius, and storage usage is 19.",
                "2 percent. There are 7 installed applications.",
            ):
                yield LLMChunk(text)

    async def scenario() -> None:
        tts = FakeTTSProvider()
        await StreamingSpeechPipeline(LoggedChunkLLM(), tts).run(
            [Message("user", "status")],
            on_text=_ignore_text,
            play_audio=_ignore_audio,
            output_directory=tmp_path / "tts-pi-zero-regression",
            speech_chunk_target_units=120,
            speech_chunk_max_sentences=2,
            speech_chunk_hard_limit_units=180,
        )

        assert len(tts.synthesized_texts) == 4
        assert tts.synthesized_texts[0] == "Here is the current system status."
        assert "Rev 1 point 0" in tts.synthesized_texts[1]
        assert "192 dot 168 dot 3 dot 2" in tts.synthesized_texts[1]
        assert "13 point 3 percent" in tts.synthesized_texts[2]
        assert "68 point 6 percent" in tts.synthesized_texts[2]
        assert "47 point 2 degrees" in tts.synthesized_texts[2]
        assert "19 point 2 percent" in tts.synthesized_texts[2]
        assert tts.synthesized_texts[3] == (
            "There are 7 installed applications."
        )

    asyncio.run(scenario())


def test_pipeline_splits_long_speech_chunks_and_keeps_display_offsets(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        response = "First. " + "word " * 45 + "done."
        provider = FakeAIProvider(response=response, chunk_size=7)
        starts: list[SpeechSegment] = []

        async def on_start(segment: SpeechSegment) -> None:
            starts.append(segment)

        await StreamingSpeechPipeline(provider, provider).run(
            [Message("user", "hello")],
            on_text=_ignore_text,
            play_audio=_ignore_audio,
            output_directory=tmp_path / "tts-bounded-chunks",
            on_playback_start=on_start,
            speech_chunk_target_units=40,
            speech_chunk_max_sentences=2,
            speech_chunk_hard_limit_units=50,
        )

        assert provider.synthesized_texts[0] == "First."
        assert all(len(text) <= 50 for text in provider.synthesized_texts)
        assert [segment.display_end for segment in starts] == sorted(
            segment.display_end for segment in starts
        )
        assert starts[-1].display_end == len(response)

    asyncio.run(scenario())


def test_pipeline_reports_ordered_speech_segments_with_duration(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        response = "**First.** Second!"
        provider = FakeAIProvider(response=response, chunk_size=3)
        events: list[tuple[str, SpeechSegment, bool | None]] = []

        async def on_start(segment: SpeechSegment) -> None:
            events.append(("start", segment, None))

        async def on_end(segment: SpeechSegment, completed: bool) -> None:
            events.append(("end", segment, completed))

        result = await StreamingSpeechPipeline(provider, provider).run(
            [Message("user", "hello")],
            on_text=_ignore_text,
            play_audio=_ignore_audio,
            output_directory=tmp_path / "tts-segments",
            on_playback_start=on_start,
            on_playback_end=on_end,
        )

        assert result == response
        assert [event[0] for event in events] == [
            "start",
            "end",
            "start",
            "end",
        ]
        starts = [event[1] for event in events if event[0] == "start"]
        assert [segment.display_text for segment in starts] == [
            "**First.",
            "** Second!",
        ]
        assert [segment.speech_text for segment in starts] == [
            "First.",
            "Second!",
        ]
        assert [segment.display_end for segment in starts] == [
            response.index(".") + 1,
            len(response),
        ]
        assert all(segment.duration_ms is not None for segment in starts)
        assert all(segment.duration_ms > 0 for segment in starts if segment.duration_ms)
        assert [event[2] for event in events if event[0] == "end"] == [
            True,
            True,
        ]

    asyncio.run(scenario())


def test_runtime_playback_starts_before_slow_display_observer(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        provider = FakeAIProvider(response="Playback starts.")
        playback_started = asyncio.Event()
        observer_saw_playback = False

        async def play_audio(_path: Path) -> None:
            playback_started.set()
            await asyncio.sleep(0.01)

        async def on_start(_segment: SpeechSegment) -> None:
            nonlocal observer_saw_playback
            await asyncio.wait_for(playback_started.wait(), timeout=0.5)
            observer_saw_playback = True

        await StreamingSpeechPipeline(provider, provider).run(
            [Message("user", "hello")],
            on_text=_ignore_text,
            play_audio=play_audio,
            output_directory=tmp_path / "tts-nonblocking-observer",
            on_playback_start=on_start,
        )

        assert observer_saw_playback is True

    asyncio.run(scenario())


def test_playback_observer_failure_does_not_block_audio(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        provider = FakeAIProvider(response="Still plays.")
        played: list[Path] = []

        async def fail_start(_segment: SpeechSegment) -> None:
            raise RuntimeError("display unavailable")

        async def fail_end(
            _segment: SpeechSegment,
            _completed: bool,
        ) -> None:
            raise RuntimeError("display unavailable")

        async def play_audio(path: Path) -> None:
            played.append(path)

        result = await StreamingSpeechPipeline(provider, provider).run(
            [Message("user", "hello")],
            on_text=_ignore_text,
            play_audio=play_audio,
            output_directory=tmp_path / "tts-observer-failure",
            on_playback_start=fail_start,
            on_playback_end=fail_end,
        )

        assert result == "Still plays."
        assert len(played) == 1

    caplog.set_level(logging.ERROR, logger="lafvin_hat.ai.pipeline")
    asyncio.run(scenario())

    assert caplog.text.count("event=callback_failed") == 2


def test_pipeline_displays_raw_markdown_but_sends_clean_text_to_tts(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        response = "**重要。**\n***\n[文档](https://example.com/docs)！👍"
        provider = FakeAIProvider(response=response, chunk_size=2)
        displayed: list[str] = []

        pipeline = StreamingSpeechPipeline(provider, provider)
        result = await pipeline.run(
            [Message("user", "hello")],
            on_text=_append_to(displayed),
            play_audio=_ignore_audio,
            output_directory=tmp_path / "tts-markdown",
        )

        assert result == response
        assert "".join(displayed) == response
        assert provider.synthesized_texts == ["重要。", "文档！"]

    asyncio.run(scenario())


def test_content_logging_records_llm_and_final_tts_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        provider = FakeAIProvider(response="**Hello.**", chunk_size=3)
        pipeline = StreamingSpeechPipeline(provider, provider)
        await pipeline.run(
            [Message("user", "hello")],
            on_text=_ignore_text,
            play_audio=_ignore_audio,
            output_directory=tmp_path / "tts-content-log",
        )

    monkeypatch.setenv("LAFVIN_AI_LOG_CONTENT", "1")
    caplog.set_level(logging.INFO, logger="lafvin_hat.ai.pipeline")

    asyncio.run(scenario())

    assert "event=response_text text='**Hello.**'" in caplog.text
    assert "event=request_text sequence=1 text='Hello.'" in caplog.text


def test_content_logging_is_disabled_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        provider = FakeAIProvider(response="Private response.")
        pipeline = StreamingSpeechPipeline(provider, provider)
        await pipeline.run(
            [Message("user", "hello")],
            on_text=_ignore_text,
            play_audio=_ignore_audio,
            output_directory=tmp_path / "tts-private-log",
        )

    monkeypatch.delenv("LAFVIN_AI_LOG_CONTENT", raising=False)
    caplog.set_level(logging.INFO, logger="lafvin_hat.ai.pipeline")

    asyncio.run(scenario())

    assert "event=response_text" not in caplog.text
    assert "event=request_text" not in caplog.text


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


def test_cancelled_finish_reaps_active_playback_worker(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        provider = FakeAIProvider(response="unused")
        playback_started = asyncio.Event()
        runtime_stopped = asyncio.Event()
        playback_results: list[tuple[int, bool]] = []

        async def play_audio(_path: Path) -> None:
            playback_started.set()
            await runtime_stopped.wait()
            raise RuntimeError("playback stopped by runtime")

        async def on_playback_end(
            segment: SpeechSegment,
            completed: bool,
        ) -> None:
            playback_results.append((segment.sequence, completed))

        queue = TTSQueue(
            provider,
            play_audio,
            output_directory=tmp_path / "tts-cancel-finish",
            on_playback_end=on_playback_end,
        )
        await queue.put("First sentence.")
        finish_task = asyncio.create_task(queue.finish())
        await asyncio.wait_for(playback_started.wait(), timeout=1)
        await asyncio.sleep(0)
        playback_task = queue._playback_task
        assert playback_task is not None

        finish_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await finish_task
        runtime_stopped.set()
        await asyncio.sleep(0)

        assert playback_task.done()
        assert playback_task.cancelled()
        assert queue._synthesis_task is None
        assert queue._playback_task is None
        assert playback_results == [(1, False)]

    asyncio.run(scenario())


async def _ignore_text(_value: str) -> None:
    return None


async def _ignore_audio(_path: Path) -> None:
    return None


def _append_to(values: list[str]):
    async def append(value: str) -> None:
        values.append(value)

    return append
