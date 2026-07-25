from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import AudioResult, LLMChunk, Message


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    base_url: str
    api_key: str | None = None
    timeout: float = 60.0
    retries: int = 2

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("OpenAI-compatible base_url cannot be empty")
        if self.timeout <= 0:
            raise ValueError("OpenAI-compatible timeout must be positive")
        if self.retries < 0:
            raise ValueError("OpenAI-compatible retries cannot be negative")

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")

    def headers(self) -> dict[str, str]:
        key = self.api_key or os.getenv("OPENAI_API_KEY")
        return {"Authorization": f"Bearer {key}"} if key else {}


class OpenAICompatibleASR:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        model: str = "whisper-1",
        timeout: float = 60.0,
        retries: int = 2,
    ) -> None:
        self.config = OpenAICompatibleConfig(
            base_url,
            api_key,
            timeout,
            retries,
        )
        self.model = model

    async def transcribe(self, audio_path: str | Path) -> str:
        httpx = _httpx()
        path = Path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            for attempt in range(self.config.retries + 1):
                try:
                    with path.open("rb") as audio:
                        response = await client.post(
                            (
                                f"{self.config.normalized_base_url}"
                                "/audio/transcriptions"
                            ),
                            headers=self.config.headers(),
                            data={"model": self.model},
                            files={"file": (path.name, audio, "audio/wav")},
                        )
                    response.raise_for_status()
                    break
                except Exception as exc:
                    if not _should_retry(httpx, exc, attempt, self.config):
                        raise
                    await _wait_before_retry("asr", attempt, exc)
        value = response.json()
        text = value.get("text")
        if not isinstance(text, str):
            raise RuntimeError("ASR response does not contain text")
        return text


class OpenAICompatibleLLM:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        retries: int = 2,
    ) -> None:
        self.config = OpenAICompatibleConfig(
            base_url,
            api_key,
            timeout,
            retries,
        )
        self.model = model

    async def stream_chat(
        self,
        messages: list[Message],
    ) -> AsyncIterator[LLMChunk]:
        httpx = _httpx()
        payload = {
            "model": self.model,
            "stream": True,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
        }
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.config.normalized_base_url}/chat/completions",
                headers={
                    **self.config.headers(),
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    value = json.loads(data)
                    choice = value.get("choices", [{}])[0]
                    delta = choice.get("delta") or {}
                    text = delta.get("content") or ""
                    finish_reason = choice.get("finish_reason")
                    if text or finish_reason:
                        yield LLMChunk(
                            text=str(text),
                            finish_reason=(
                                str(finish_reason)
                                if finish_reason is not None
                                else None
                            ),
                        )


class OpenAICompatibleTTS:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        model: str = "tts-1",
        voice: str = "alloy",
        timeout: float = 60.0,
        retries: int = 2,
    ) -> None:
        self.config = OpenAICompatibleConfig(
            base_url,
            api_key,
            timeout,
            retries,
        )
        self.model = model
        self.voice = voice

    async def synthesize(
        self,
        text: str,
        *,
        output_path: str | Path | None = None,
    ) -> AudioResult:
        httpx = _httpx()
        path = (
            Path(output_path)
            if output_path is not None
            else Path(tempfile.mkdtemp(prefix="lafvin-tts-")) / "speech.wav"
        )
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            for attempt in range(self.config.retries + 1):
                try:
                    response = await client.post(
                        f"{self.config.normalized_base_url}/audio/speech",
                        headers={
                            **self.config.headers(),
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "voice": self.voice,
                            "input": text,
                            "response_format": "wav",
                        },
                    )
                    response.raise_for_status()
                    break
                except Exception as exc:
                    if not _should_retry(httpx, exc, attempt, self.config):
                        raise
                    await _wait_before_retry("tts", attempt, exc)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return AudioResult(path=path)


class OpenAICompatibleProvider:
    """Compatibility wrapper; new code should inject ASR, LLM, and TTS separately."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        llm_model: str,
        asr_model: str,
        tts_model: str,
        tts_voice: str = "alloy",
        timeout: float = 60.0,
        retries: int = 2,
    ) -> None:
        self.asr = OpenAICompatibleASR(
            base_url=base_url,
            api_key=api_key,
            model=asr_model,
            timeout=timeout,
            retries=retries,
        )
        self.llm = OpenAICompatibleLLM(
            base_url=base_url,
            api_key=api_key,
            model=llm_model,
            timeout=timeout,
            retries=retries,
        )
        self.tts = OpenAICompatibleTTS(
            base_url=base_url,
            api_key=api_key,
            model=tts_model,
            voice=tts_voice,
            timeout=timeout,
            retries=retries,
        )

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


def _httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError(
            'OpenAI-compatible providers require: pip install -e ".[ai]"'
        ) from exc
    return httpx


def _should_retry(
    httpx: Any,
    exc: Exception,
    attempt: int,
    config: OpenAICompatibleConfig,
) -> bool:
    if attempt >= config.retries:
        return False
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status in {408, 409, 429} or status >= 500
    return False


async def _wait_before_retry(
    capability: str,
    attempt: int,
    exc: Exception,
) -> None:
    delay = min(4.0, 0.5 * (2 ** attempt))
    logger.warning(
        "stage=%s event=retry attempt=%s delay_ms=%s error_type=%s",
        capability,
        attempt + 1,
        int(delay * 1000),
        type(exc).__name__,
    )
    started_at = time.monotonic()
    await asyncio.sleep(delay)
    logger.debug(
        "stage=%s event=retry_wait_done duration_ms=%s",
        capability,
        int((time.monotonic() - started_at) * 1000),
    )
