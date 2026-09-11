from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from pathlib import Path
from typing import Protocol

from .models import AudioResult, LLMChunk, Message, ToolCall, ToolDefinition


ToolExecutor = Callable[[ToolCall], Awaitable[str]]


class ASRProvider(Protocol):
    async def transcribe(self, audio_path: str | Path) -> str: ...


class LLMProvider(Protocol):
    def stream_chat(
        self,
        messages: list[Message],
        *,
        tools: Sequence[ToolDefinition] = (),
        tool_executor: ToolExecutor | None = None,
    ) -> AsyncIterator[LLMChunk]: ...


class TTSProvider(Protocol):
    async def synthesize(
        self,
        text: str,
        *,
        output_path: str | Path | None = None,
    ) -> AudioResult: ...


async def aclose_provider(provider: object) -> None:
    close = getattr(provider, "aclose", None)
    if close is not None:
        await close()
