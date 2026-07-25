from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class LLMChunk:
    text: str
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class AudioResult:
    path: Path
    format: str = "wav"
