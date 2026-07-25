from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from .models import Message
from .providers import LLMProvider, TTSProvider


logger = logging.getLogger(__name__)


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


class SentenceSplitter:
    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, text: str) -> list[str]:
        self._buffer += text
        result: list[str] = []
        start = 0
        for index, char in enumerate(self._buffer):
            if char in ".!?。！？\n":
                sentence = self._buffer[start:index + 1].strip()
                if sentence:
                    result.append(sentence)
                start = index + 1
        self._buffer = self._buffer[start:]
        return result

    def flush(self) -> str | None:
        value = self._buffer.strip()
        self._buffer = ""
        return value or None


class TTSQueue:
    def __init__(
        self,
        provider: TTSProvider,
        play_audio: Callable[[Path], Awaitable[None]],
        *,
        output_directory: Path,
        max_queue_size: int = 3,
    ) -> None:
        self._provider = provider
        self._play_audio = play_audio
        self._output_directory = output_directory
        self._sentence_queue: asyncio.Queue[str | None] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._audio_queue: asyncio.Queue[Path | None] = asyncio.Queue(
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

    async def put(self, sentence: str) -> None:
        await self.start()
        put_task = asyncio.create_task(self._sentence_queue.put(sentence))
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
        await self._sentence_queue.put(None)
        tasks = (self._synthesis_task, self._playback_task)
        try:
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
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                raise failure
            await asyncio.gather(*pending)
        finally:
            self._synthesis_task = None
            self._playback_task = None

    async def cancel(self) -> None:
        tasks = [
            task
            for task in (self._synthesis_task, self._playback_task)
            if task is not None
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._synthesis_task = None
        self._playback_task = None
        self._clear_queue(self._sentence_queue)
        self._clear_queue(self._audio_queue)

    async def _synthesize(self) -> None:
        self._output_directory.mkdir(parents=True, exist_ok=True)
        try:
            while True:
                sentence = await self._sentence_queue.get()
                if sentence is None:
                    return
                self._sequence += 1
                output = (
                    self._output_directory
                    / f"speech-{self._sequence:04d}.wav"
                )
                logger.info(
                    "stage=tts_synthesize event=start sequence=%s chars=%s",
                    self._sequence,
                    len(sentence),
                )
                started_at = time.monotonic()
                try:
                    result = await self._provider.synthesize(
                        sentence,
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
                await self._audio_queue.put(result.path)
        finally:
            current = asyncio.current_task()
            if current is None or not current.cancelling():
                await self._audio_queue.put(None)

    async def _play(self) -> None:
        while True:
            path = await self._audio_queue.get()
            if path is None:
                return
            sequence = _sequence_from_path(path)
            logger.info(
                "stage=audio_playback event=start sequence=%s path=%s",
                sequence,
                path,
            )
            started_at = time.monotonic()
            try:
                await self._play_audio(path)
            except Exception as exc:
                raise PipelineStageError(
                    "audio_playback",
                    f"Audio playback failed for sentence {sequence}: {exc}",
                    sequence=sequence,
                ) from exc
            logger.info(
                "stage=audio_playback event=done sequence=%s duration_ms=%s",
                sequence,
                int((time.monotonic() - started_at) * 1000),
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
    ) -> str:
        splitter = SentenceSplitter()
        queue = TTSQueue(
            self._tts,
            play_audio,
            output_directory=output_directory,
        )
        full_text = ""
        pending_text = ""
        next_flush = time.monotonic() + text_flush_interval
        try:
            logger.info("stage=llm_stream event=start messages=%s", len(messages))
            try:
                async for chunk in self._llm.stream_chat(messages):
                    if chunk.text:
                        full_text += chunk.text
                        pending_text += chunk.text
                        for sentence in splitter.feed(chunk.text):
                            await queue.put(sentence)
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
            if pending_text:
                await on_text(pending_text)
            remainder = splitter.flush()
            if remainder:
                await queue.put(remainder)
            await queue.finish()
            return full_text
        except BaseException:
            await queue.cancel()
            raise


def _sequence_from_path(path: Path) -> int | None:
    try:
        return int(path.stem.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None
