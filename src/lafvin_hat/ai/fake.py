from __future__ import annotations

import asyncio
import math
import struct
import tempfile
import wave
from collections.abc import AsyncIterator
from pathlib import Path

from .models import AudioResult, LLMChunk, Message


class FakeASRProvider:
    def __init__(
        self,
        *,
        transcript: str = "test recording",
    ) -> None:
        self.transcript = transcript

    async def transcribe(self, audio_path: str | Path) -> str:
        if not Path(audio_path).is_file():
            raise FileNotFoundError(audio_path)
        await asyncio.sleep(0)
        return self.transcript


class FakeLLMProvider:
    def __init__(
        self,
        *,
        response: str = "This is a deterministic response. It is ready.",
        chunk_size: int = 8,
    ) -> None:
        self.response = response
        self.chunk_size = chunk_size

    async def stream_chat(
        self,
        messages: list[Message],
    ) -> AsyncIterator[LLMChunk]:
        del messages
        for offset in range(0, len(self.response), self.chunk_size):
            await asyncio.sleep(0)
            yield LLMChunk(self.response[offset:offset + self.chunk_size])
        yield LLMChunk("", finish_reason="stop")


class FakeTTSProvider:
    def __init__(self) -> None:
        self.synthesized_texts: list[str] = []

    async def synthesize(
        self,
        text: str,
        *,
        output_path: str | Path | None = None,
    ) -> AudioResult:
        self.synthesized_texts.append(text)
        path = (
            Path(output_path)
            if output_path is not None
            else Path(tempfile.mkdtemp(prefix="lafvin-fake-tts-")) / "speech.wav"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            duration_sec = min(0.8, max(0.25, len(text) * 0.012))
            total_samples = int(16000 * duration_sec)
            frames = bytearray()
            for index in range(total_samples):
                envelope = min(
                    1.0,
                    index / 320,
                    (total_samples - index) / 640,
                )
                sample = int(
                    9000
                    * max(0.0, envelope)
                    * math.sin(2 * math.pi * 660 * index / 16000)
                )
                frames.extend(struct.pack("<h", sample))
            output.writeframes(frames)
        return AudioResult(path=path)


class FakeAIProvider:
    """Compatibility wrapper for M4 code that used one provider object."""

    def __init__(
        self,
        *,
        transcript: str = "test recording",
        response: str = "This is a deterministic response. It is ready.",
        chunk_size: int = 8,
    ) -> None:
        self.asr = FakeASRProvider(transcript=transcript)
        self.llm = FakeLLMProvider(
            response=response,
            chunk_size=chunk_size,
        )
        self.tts = FakeTTSProvider()

    @property
    def synthesized_texts(self) -> list[str]:
        return self.tts.synthesized_texts

    async def transcribe(self, audio_path: str | Path) -> str:
        return await self.asr.transcribe(audio_path)

    def stream_chat(
        self,
        messages: list[Message],
    ) -> AsyncIterator[LLMChunk]:
        return self.llm.stream_chat(messages)

    async def synthesize(
        self,
        text: str,
        *,
        output_path: str | Path | None = None,
    ) -> AudioResult:
        return await self.tts.synthesize(text, output_path=output_path)
