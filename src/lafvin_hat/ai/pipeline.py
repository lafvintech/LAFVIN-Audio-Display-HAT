from __future__ import annotations

import asyncio
import html
import logging
import os
import re
import time
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .audio_normalization import AudioNormalizationError, pcm_wav_duration_ms
from .models import Message, SpeechSegment, ToolDefinition
from .providers import LLMProvider, TTSProvider, ToolExecutor


logger = logging.getLogger(__name__)


_MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MARKDOWN_AUTOLINK = re.compile(r"<https?://[^>\s]+>", re.IGNORECASE)
_RAW_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")
_FENCED_CODE_MARKER = re.compile(r"```(?:[A-Za-z0-9_+-]+)?")
_MARKDOWN_SEPARATOR = re.compile(r"(?m)^[ \t]*(?:[-*_][ \t]*){3,}$")
_MARKDOWN_LINE_PREFIX = re.compile(
    r"(?m)^[ \t]{0,3}(?:#{1,6}[ \t]+|>[ \t]?|(?:[-+*]|\d+[.)])[ \t]+)"
)
_IPV4_ADDRESS = re.compile(
    r"(?<![\d.])(?P<address>\d{1,3}(?:\.\d{1,3}){3})(?!\d|\.\d)"
)
_DECIMAL_SEPARATOR = re.compile(r"(?<=\d)\.(?=\d)")
_CJK_CHARACTER = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


class PipelineStageError(RuntimeError):
    def __init__(
        self,
        stage: str,
        message: str,
        *,
        sequence: int | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.sequence = sequence


@dataclass(frozen=True, slots=True)
class SentencePart:
    text: str
    display_end: int


class SentenceSplitter:
    def __init__(self) -> None:
        self._buffer = ""
        self._buffer_start = 0

    def feed(self, text: str) -> list[str]:
        return [part.text for part in self.feed_parts(text)]

    def feed_parts(self, text: str) -> list[SentencePart]:
        self._buffer += text
        result: list[SentencePart] = []
        start = 0
        for index, char in enumerate(self._buffer):
            if char in ".!?。！？\n" and _is_sentence_boundary(
                self._buffer,
                index,
                char,
            ):
                raw_sentence = self._buffer[start:index + 1]
                sentence = raw_sentence.strip()
                if sentence:
                    trailing_whitespace = len(raw_sentence) - len(
                        raw_sentence.rstrip()
                    )
                    result.append(
                        SentencePart(
                            sentence,
                            self._buffer_start + index + 1 - trailing_whitespace,
                        )
                    )
                start = index + 1
        self._buffer = self._buffer[start:]
        self._buffer_start += start
        return result

    def flush(self) -> str | None:
        part = self.flush_part()
        return part.text if part is not None else None

    def flush_part(self) -> SentencePart | None:
        raw_sentence = self._buffer
        value = raw_sentence.strip()
        trailing_whitespace = len(raw_sentence) - len(raw_sentence.rstrip())
        display_end = self._buffer_start + len(raw_sentence) - trailing_whitespace
        self._buffer_start += len(raw_sentence)
        self._buffer = ""
        if not value:
            return None
        return SentencePart(value, display_end)


class SpeechChunker:
    """Combine sentence parts into bounded, ordered TTS request units."""

    def __init__(
        self,
        *,
        target_units: int,
        max_sentences: int,
        hard_limit_units: int,
        first_chunk_immediate: bool = True,
    ) -> None:
        if target_units <= 0:
            raise ValueError("target_units must be positive")
        if max_sentences <= 0:
            raise ValueError("max_sentences must be positive")
        if hard_limit_units < target_units:
            raise ValueError(
                "hard_limit_units must be greater than or equal to target_units"
            )
        self._target_units = target_units
        self._max_sentences = max_sentences
        self._hard_limit_units = hard_limit_units
        self._first_chunk_immediate = first_chunk_immediate
        self._pending: list[SentencePart] = []
        self._emitted = False

    def feed(self, part: SentencePart) -> list[SentencePart]:
        emitted: list[SentencePart] = []
        for candidate in _split_long_speech_part(
            part,
            self._hard_limit_units,
        ):
            if self._first_chunk_immediate and not self._emitted:
                emitted.append(candidate)
                self._emitted = True
                continue

            if self._pending and (
                _combined_speech_units([*self._pending, candidate])
                > self._hard_limit_units
            ):
                emitted.append(self._take_pending())

            self._pending.append(candidate)
            if (
                _combined_speech_units(self._pending) >= self._target_units
                or len(self._pending) >= self._max_sentences
            ):
                emitted.append(self._take_pending())

        return emitted

    def flush(self) -> SentencePart | None:
        if not self._pending:
            return None
        return self._take_pending()

    def _take_pending(self) -> SentencePart:
        combined = SentencePart(
            " ".join(
                part.text.strip()
                for part in self._pending
                if part.text.strip()
            ),
            self._pending[-1].display_end,
        )
        self._pending.clear()
        self._emitted = True
        return combined


@dataclass(frozen=True, slots=True)
class _PendingSpeech:
    display_text: str
    speech_text: str
    display_end: int


class TTSQueue:
    def __init__(
        self,
        provider: TTSProvider,
        play_audio: Callable[[Path], Awaitable[None]],
        *,
        output_directory: Path,
        max_queue_size: int = 3,
        on_playback_start: Callable[[SpeechSegment], Awaitable[None]] | None = None,
        on_playback_end: (
            Callable[[SpeechSegment, bool], Awaitable[None]] | None
        ) = None,
    ) -> None:
        self._provider = provider
        self._play_audio = play_audio
        self._output_directory = output_directory
        self._on_playback_start = on_playback_start
        self._on_playback_end = on_playback_end
        self._sentence_queue: asyncio.Queue[_PendingSpeech | None] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._audio_queue: asyncio.Queue[SpeechSegment | None] = asyncio.Queue(
            maxsize=2
        )
        self._synthesis_task: asyncio.Task[None] | None = None
        self._playback_task: asyncio.Task[None] | None = None
        self._sequence = 0

    async def start(self) -> None:
        if self._synthesis_task is None:
            self._synthesis_task = asyncio.create_task(
                self._synthesize(),
                name="tts-synthesis",
            )
            self._playback_task = asyncio.create_task(
                self._play(),
                name="tts-playback",
            )

    async def put(
        self,
        sentence: str,
        *,
        display_end: int | None = None,
    ) -> None:
        speech_text = prepare_text_for_speech(sentence)
        if not speech_text:
            logger.info(
                "stage=tts_prepare event=skipped reason=no_speakable_text "
                "source_chars=%s",
                len(sentence),
            )
            return
        pending_speech = _PendingSpeech(
            display_text=sentence,
            speech_text=speech_text,
            display_end=len(sentence) if display_end is None else display_end,
        )
        await self.start()
        put_task = asyncio.create_task(self._sentence_queue.put(pending_speech))
        workers = {
            task
            for task in (self._synthesis_task, self._playback_task)
            if task is not None
        }
        done, _pending = await asyncio.wait(
            {put_task, *workers},
            return_when=asyncio.FIRST_COMPLETED,
        )
        failed_worker = next(
            (
                task
                for task in done
                if task is not put_task
                and not task.cancelled()
                and task.exception() is not None
            ),
            None,
        )
        if failed_worker is not None:
            put_task.cancel()
            await asyncio.gather(put_task, return_exceptions=True)
            raise failed_worker.exception()  # type: ignore[misc]
        await put_task

    async def finish(self) -> None:
        if self._synthesis_task is None or self._playback_task is None:
            return
        tasks = (self._synthesis_task, self._playback_task)
        try:
            await self._sentence_queue.put(None)
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_EXCEPTION,
            )
            failure = next(
                (
                    task.exception()
                    for task in done
                    if not task.cancelled() and task.exception() is not None
                ),
                None,
            )
            if failure is not None:
                raise failure
            await asyncio.gather(*pending)
        except BaseException:
            await self._cancel_tasks(tasks)
            raise
        finally:
            self._synthesis_task = None
            self._playback_task = None

    async def cancel(self) -> None:
        tasks = [
            task
            for task in (self._synthesis_task, self._playback_task)
            if task is not None
        ]
        await self._cancel_tasks(tasks)
        self._synthesis_task = None
        self._playback_task = None
        self._clear_queue(self._sentence_queue)
        self._clear_queue(self._audio_queue)

    async def _cancel_tasks(
        self,
        tasks: tuple[asyncio.Task[None], ...] | list[asyncio.Task[None]],
    ) -> None:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _synthesize(self) -> None:
        self._output_directory.mkdir(parents=True, exist_ok=True)
        try:
            while True:
                pending = await self._sentence_queue.get()
                if pending is None:
                    return
                self._sequence += 1
                output = (
                    self._output_directory
                    / f"speech-{self._sequence:04d}.wav"
                )
                logger.info(
                    "stage=tts_synthesize event=start sequence=%s chars=%s",
                    self._sequence,
                    len(pending.speech_text),
                )
                if _content_logging_enabled():
                    logger.info(
                        "stage=tts_synthesize event=request_text "
                        "sequence=%s text=%r",
                        self._sequence,
                        pending.speech_text,
                    )
                started_at = time.monotonic()
                try:
                    result = await self._provider.synthesize(
                        pending.speech_text,
                        output_path=output,
                    )
                except Exception as exc:
                    raise PipelineStageError(
                        "tts_synthesize",
                        (
                            f"TTS synthesis failed for sentence "
                            f"{self._sequence}: {exc}"
                        ),
                        sequence=self._sequence,
                    ) from exc
                logger.info(
                    "stage=tts_synthesize event=done sequence=%s "
                    "duration_ms=%s",
                    self._sequence,
                    int((time.monotonic() - started_at) * 1000),
                )
                await self._audio_queue.put(
                    SpeechSegment(
                        sequence=self._sequence,
                        display_text=pending.display_text,
                        speech_text=pending.speech_text,
                        display_end=pending.display_end,
                        path=result.path,
                        duration_ms=_audio_duration_ms(result.path, result.duration_ms),
                    )
                )
        finally:
            current = asyncio.current_task()
            if current is None or not current.cancelling():
                await self._audio_queue.put(None)

    async def _play(self) -> None:
        while True:
            segment = await self._audio_queue.get()
            if segment is None:
                return
            logger.info(
                "stage=audio_playback event=start sequence=%s path=%s "
                "expected_duration_ms=%s display_end=%s",
                segment.sequence,
                segment.path,
                segment.duration_ms,
                segment.display_end,
            )
            completed = False
            playback_duration_ms: int | None = None
            playback_task: asyncio.Task[None] | None = None
            try:
                started_at = time.monotonic()
                playback_task = asyncio.create_task(
                    self._play_audio(segment.path),
                    name=f"audio-playback-{segment.sequence}",
                )
                # Let the Runtime playback request leave the App before a
                # potentially expensive display observer calculates layout.
                await asyncio.sleep(0)
                await self._notify_playback_start(segment)
                await playback_task
                completed = True
                playback_duration_ms = int(
                    (time.monotonic() - started_at) * 1000
                )
            except asyncio.CancelledError:
                if playback_task is not None:
                    if not playback_task.done():
                        playback_task.cancel()
                    await asyncio.gather(playback_task, return_exceptions=True)
                raise
            except Exception as exc:
                if playback_task is not None:
                    if not playback_task.done():
                        playback_task.cancel()
                    await asyncio.gather(playback_task, return_exceptions=True)
                raise PipelineStageError(
                    "audio_playback",
                    (
                        "Audio playback failed for sentence "
                        f"{segment.sequence}: {exc}"
                    ),
                    sequence=segment.sequence,
                ) from exc
            finally:
                await self._notify_playback_end(segment, completed)
            logger.info(
                "stage=audio_playback event=done sequence=%s duration_ms=%s",
                segment.sequence,
                playback_duration_ms,
            )

    async def _notify_playback_start(self, segment: SpeechSegment) -> None:
        if self._on_playback_start is None:
            return
        try:
            await self._on_playback_start(segment)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "stage=playback_observer event=callback_failed "
                "phase=start sequence=%s",
                segment.sequence,
            )

    async def _notify_playback_end(
        self,
        segment: SpeechSegment,
        completed: bool,
    ) -> None:
        if self._on_playback_end is None:
            return
        try:
            await self._on_playback_end(segment, completed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "stage=playback_observer event=callback_failed "
                "phase=end sequence=%s completed=%s",
                segment.sequence,
                completed,
            )

    def _clear_queue(self, queue: asyncio.Queue[object]) -> None:
        while not queue.empty():
            queue.get_nowait()


class StreamingSpeechPipeline:
    def __init__(
        self,
        llm: LLMProvider,
        tts: TTSProvider,
    ) -> None:
        self._llm = llm
        self._tts = tts

    async def run(
        self,
        messages: list[Message],
        *,
        on_text: Callable[[str], Awaitable[None]],
        play_audio: Callable[[Path], Awaitable[None]],
        output_directory: Path,
        text_flush_interval: float = 0.05,
        on_playback_start: Callable[[SpeechSegment], Awaitable[None]] | None = None,
        on_playback_end: (
            Callable[[SpeechSegment, bool], Awaitable[None]] | None
        ) = None,
        tools: Sequence[ToolDefinition] = (),
        tool_executor: ToolExecutor | None = None,
        speech_chunk_target_units: int | None = None,
        speech_chunk_max_sentences: int = 2,
        speech_chunk_hard_limit_units: int = 180,
    ) -> str:
        splitter = SentenceSplitter()
        chunker = (
            SpeechChunker(
                target_units=speech_chunk_target_units,
                max_sentences=speech_chunk_max_sentences,
                hard_limit_units=speech_chunk_hard_limit_units,
            )
            if speech_chunk_target_units is not None
            else None
        )
        queue = TTSQueue(
            self._tts,
            play_audio,
            output_directory=output_directory,
            on_playback_start=on_playback_start,
            on_playback_end=on_playback_end,
        )
        full_text = ""
        pending_text = ""
        next_flush = time.monotonic() + text_flush_interval
        try:
            logger.info("stage=llm_stream event=start messages=%s", len(messages))
            try:
                async for chunk in self._llm.stream_chat(
                    messages,
                    tools=tools,
                    tool_executor=tool_executor,
                ):
                    if chunk.text:
                        full_text += chunk.text
                        pending_text += chunk.text
                        parts = splitter.feed_parts(chunk.text)
                        if parts and pending_text:
                            await on_text(pending_text)
                            pending_text = ""
                            next_flush = time.monotonic() + text_flush_interval
                        for part in parts:
                            speech_parts = (
                                chunker.feed(part)
                                if chunker is not None
                                else [part]
                            )
                            for speech_part in speech_parts:
                                await queue.put(
                                    speech_part.text,
                                    display_end=speech_part.display_end,
                                )
                        if (
                            text_flush_interval <= 0
                            or time.monotonic() >= next_flush
                        ):
                            await on_text(pending_text)
                            pending_text = ""
                            next_flush = time.monotonic() + text_flush_interval
            except PipelineStageError:
                raise
            except Exception as exc:
                raise PipelineStageError(
                    "llm_stream",
                    f"LLM stream failed after {len(full_text)} characters: {exc}",
                ) from exc
            logger.info(
                "stage=llm_stream event=done chars=%s",
                len(full_text),
            )
            if _content_logging_enabled():
                logger.info(
                    "stage=llm_stream event=response_text text=%r",
                    full_text,
                )
            if pending_text:
                await on_text(pending_text)
            remainder = splitter.flush_part()
            if remainder:
                speech_parts = (
                    chunker.feed(remainder) if chunker is not None else [remainder]
                )
                for speech_part in speech_parts:
                    await queue.put(
                        speech_part.text,
                        display_end=speech_part.display_end,
                    )
            final_speech_part = chunker.flush() if chunker is not None else None
            if final_speech_part is not None:
                await queue.put(
                    final_speech_part.text,
                    display_end=final_speech_part.display_end,
                )
            await queue.finish()
            return full_text
        except BaseException:
            await queue.cancel()
            raise


def _audio_duration_ms(path: Path, declared_duration_ms: int | None) -> int | None:
    if declared_duration_ms is not None and declared_duration_ms > 0:
        return declared_duration_ms
    try:
        return pcm_wav_duration_ms(path)
    except AudioNormalizationError as exc:
        logger.warning(
            "stage=audio_playback event=duration_unavailable path=%s "
            "error_type=%s",
            path,
            type(exc).__name__,
        )
        return None


def prepare_text_for_speech(text: str) -> str:
    """Remove Markdown presentation syntax without changing displayed text."""
    value = html.unescape(text)
    value = _MARKDOWN_IMAGE.sub(lambda match: match.group(1), value)
    value = _MARKDOWN_LINK.sub(lambda match: match.group(1), value)
    value = _MARKDOWN_AUTOLINK.sub(" ", value)
    value = _RAW_URL.sub(" ", value)
    value = _HTML_TAG.sub(" ", value)
    value = _FENCED_CODE_MARKER.sub(" ", value)
    value = _MARKDOWN_SEPARATOR.sub(" ", value)
    value = _MARKDOWN_LINE_PREFIX.sub("", value)
    value = value.replace("**", " ").replace("__", " ")
    value = value.replace("~~", " ").replace("`", "")
    value = re.sub(r"(?<!\w)[*_](?=\w)", "", value)
    value = re.sub(r"(?<=\w)[*_](?!\w)", "", value)
    value = value.replace("|", " ")
    numeric_separator = "点" if _CJK_CHARACTER.search(value) else None
    value = _IPV4_ADDRESS.sub(
        lambda match: _spoken_ipv4(
            match.group("address"),
            separator=numeric_separator or "dot",
        ),
        value,
    )
    value = _DECIMAL_SEPARATOR.sub(
        numeric_separator or " point ",
        value,
    )
    value = "".join(
        " " if unicodedata.category(char) in {"So", "Sk"} else char
        for char in value
    )
    value = re.sub(r"\s+", " ", value).strip()
    if not any(char.isalnum() for char in value):
        return ""
    return value


def _is_sentence_boundary(text: str, index: int, char: str) -> bool:
    if char != ".":
        return True
    if index + 1 >= len(text):
        return False
    previous = text[index - 1] if index > 0 else ""
    following = text[index + 1] if index + 1 < len(text) else ""
    if previous.isalnum() and following.isalnum():
        return False
    line_start = text.rfind("\n", 0, index) + 1
    if re.fullmatch(r"[ \t]*\d+\.", text[line_start:index + 1]):
        return False
    return True


def _spoken_ipv4(address: str, *, separator: str) -> str:
    joiner = separator if separator == "点" else f" {separator} "
    return joiner.join(address.split("."))


def _speech_units(text: str) -> int:
    return sum(2 if _CJK_CHARACTER.fullmatch(char) else 1 for char in text)


def _combined_speech_units(parts: Sequence[SentencePart]) -> int:
    if not parts:
        return 0
    return (
        sum(_speech_units(part.text.strip()) for part in parts)
        + len(parts)
        - 1
    )


def _split_long_speech_part(
    part: SentencePart,
    hard_limit_units: int,
) -> list[SentencePart]:
    text = part.text.strip()
    if not text or _speech_units(text) <= hard_limit_units:
        return [part]

    part_start = part.display_end - len(text)
    pieces: list[SentencePart] = []
    start = 0
    while start < len(text):
        end = start
        units = 0
        while end < len(text):
            char_units = _speech_units(text[end])
            if units and units + char_units > hard_limit_units:
                break
            units += char_units
            end += 1
        if end >= len(text):
            raw_piece = text[start:]
            piece = raw_piece.strip()
            if piece:
                pieces.append(SentencePart(piece, part.display_end))
            break

        whitespace = next(
            (
                index
                for index in range(end - 1, start, -1)
                if text[index].isspace()
            ),
            None,
        )
        cut = whitespace if whitespace is not None else end
        raw_piece = text[start:cut]
        piece = raw_piece.strip()
        if piece:
            piece_end = cut - len(raw_piece) + len(raw_piece.rstrip())
            pieces.append(
                SentencePart(
                    piece,
                    part_start + piece_end,
                )
            )
        start = cut
        while start < len(text) and text[start].isspace():
            start += 1
    return pieces


def _content_logging_enabled() -> bool:
    return os.getenv("LAFVIN_AI_LOG_CONTENT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
