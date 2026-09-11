from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str
    tool_calls: tuple["ToolCall", ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMChunk:
    text: str
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class AudioResult:
    path: Path
    format: str = "wav"
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    sequence: int
    display_text: str
    speech_text: str
    display_end: int
    path: Path
    duration_ms: int | None = None
