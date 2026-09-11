from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .http_client import ReusableHTTPClient
from .models import (
    AudioResult,
    LLMChunk,
    Message,
    ToolCall,
    ToolDefinition,
)
from .providers import ToolExecutor


logger = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 3


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
        provider_name: str = "openai-compatible",
    ) -> None:
        self.config = OpenAICompatibleConfig(
            base_url,
            api_key,
            timeout,
            retries,
        )
        self.model = model
        self.provider_name = provider_name
        self._http_client = ReusableHTTPClient(
            capability="asr",
            provider_name=provider_name,
            timeout=timeout,
            httpx_loader=_httpx,
        )

    async def transcribe(self, audio_path: str | Path) -> str:
        httpx = _httpx()
        path = Path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        client = await self._http_client.get()
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
                await _wait_before_retry(
                    "asr",
                    self.provider_name,
                    attempt,
                    exc,
                )
        value = response.json()
        text = value.get("text")
        if not isinstance(text, str):
            raise RuntimeError("ASR response does not contain text")
        return text

    async def aclose(self) -> None:
        await self._http_client.aclose()


class OpenAICompatibleLLM:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        retries: int = 2,
        provider_name: str = "openai-compatible",
    ) -> None:
        self.config = OpenAICompatibleConfig(
            base_url,
            api_key,
            timeout,
            retries,
        )
        self.model = model
        self.provider_name = provider_name
        self._http_client = ReusableHTTPClient(
            capability="llm",
            provider_name=provider_name,
            timeout=timeout,
            httpx_loader=_httpx,
        )

    async def stream_chat(
        self,
        messages: list[Message],
        *,
        tools: Sequence[ToolDefinition] = (),
        tool_executor: ToolExecutor | None = None,
    ) -> AsyncIterator[LLMChunk]:
        conversation = list(messages)
        client = await self._http_client.get()
        for tool_round in range(MAX_TOOL_ROUNDS + 1):
            payload: dict[str, Any] = {
                "model": self.model,
                "stream": True,
                "messages": [
                    _openai_message(message) for message in conversation
                ],
            }
            if tools:
                payload["tools"] = [_openai_tool(tool) for tool in tools]

            tool_parts: dict[int, dict[str, str]] = {}
            response_text = ""
            finish_reason: str | None = None
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
                        break
                    value = json.loads(data)
                    choice = value.get("choices", [{}])[0]
                    delta = choice.get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        response_text += str(text)
                        yield LLMChunk(text=str(text))
                    _merge_openai_tool_parts(
                        tool_parts,
                        delta.get("tool_calls"),
                    )
                    raw_finish_reason = choice.get("finish_reason")
                    if raw_finish_reason is not None:
                        finish_reason = str(raw_finish_reason)

            tool_calls = _openai_tool_calls(tool_parts, tool_round)
            if not tool_calls:
                if finish_reason is not None:
                    yield LLMChunk(text="", finish_reason=finish_reason)
                return
            if tool_executor is None:
                raise RuntimeError(
                    "The LLM requested a tool but no tool executor is configured"
                )
            if tool_round >= MAX_TOOL_ROUNDS:
                raise RuntimeError(
                    f"LLM exceeded the {MAX_TOOL_ROUNDS}-round tool-call limit"
                )

            conversation.append(
                Message(
                    "assistant",
                    response_text,
                    tool_calls=tuple(tool_calls),
                )
            )
            for call in tool_calls:
                try:
                    result = await tool_executor(call)
                except Exception as exc:
                    logger.exception(
                        "stage=llm_tool event=execution_failed tool=%s",
                        call.name,
                    )
                    result = json.dumps(
                        {
                            "ok": False,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                        ensure_ascii=False,
                    )
                conversation.append(
                    Message(
                        "tool",
                        result,
                        tool_call_id=call.call_id,
                    )
                )

    async def aclose(self) -> None:
        await self._http_client.aclose()


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
        provider_name: str = "openai-compatible",
    ) -> None:
        self.config = OpenAICompatibleConfig(
            base_url,
            api_key,
            timeout,
            retries,
        )
        self.model = model
        self.voice = voice
        self.provider_name = provider_name
        self._http_client = ReusableHTTPClient(
            capability="tts",
            provider_name=provider_name,
            timeout=timeout,
            httpx_loader=_httpx,
        )

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
        client = await self._http_client.get()
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
                await _wait_before_retry(
                    "tts",
                    self.provider_name,
                    attempt,
                    exc,
                )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return AudioResult(path=path)

    async def aclose(self) -> None:
        await self._http_client.aclose()


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
        *,
        tools: Sequence[ToolDefinition] = (),
        tool_executor: ToolExecutor | None = None,
    ) -> AsyncIterator[LLMChunk]:
        return self.llm.stream_chat(
            messages,
            tools=tools,
            tool_executor=tool_executor,
        )

    async def synthesize(
        self,
        text: str,
        *,
        output_path: str | Path | None = None,
    ) -> AudioResult:
        return await self.tts.synthesize(text, output_path=output_path)

    async def aclose(self) -> None:
        results = await asyncio.gather(
            self.asr.aclose(),
            self.llm.aclose(),
            self.tts.aclose(),
            return_exceptions=True,
        )
        failure = next(
            (result for result in results if isinstance(result, BaseException)),
            None,
        )
        if failure is not None:
            raise RuntimeError(
                f"Failed to close OpenAI-compatible provider: {failure}"
            ) from failure


def _openai_tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _openai_message(message: Message) -> dict[str, Any]:
    result: dict[str, Any] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_calls:
        result["tool_calls"] = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(
                        call.arguments,
                        ensure_ascii=False,
                    ),
                },
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        result["tool_call_id"] = message.tool_call_id
    return result


def _merge_openai_tool_parts(
    buffers: dict[int, dict[str, str]],
    raw_parts: Any,
) -> None:
    if not isinstance(raw_parts, list):
        return
    for raw_part in raw_parts:
        if not isinstance(raw_part, dict):
            continue
        raw_index = raw_part.get("index", 0)
        index = raw_index if isinstance(raw_index, int) else 0
        buffer = buffers.setdefault(
            index,
            {"id": "", "name": "", "arguments": ""},
        )
        call_id = raw_part.get("id")
        if isinstance(call_id, str):
            buffer["id"] = call_id
        function = raw_part.get("function") or {}
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        arguments = function.get("arguments")
        if isinstance(name, str):
            buffer["name"] += name
        if isinstance(arguments, str):
            buffer["arguments"] += arguments


def _openai_tool_calls(
    buffers: dict[int, dict[str, str]],
    tool_round: int,
) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for index, buffer in sorted(buffers.items()):
        name = buffer["name"].strip()
        if not name:
            continue
        try:
            arguments = json.loads(buffer["arguments"] or "{}")
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append(
            ToolCall(
                call_id=buffer["id"] or f"tool-{tool_round}-{index}",
                name=name,
                arguments=arguments,
            )
        )
    return calls


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
    provider_name: str,
    attempt: int,
    exc: Exception,
) -> None:
    delay = min(4.0, 0.5 * (2 ** attempt))
    logger.warning(
        "stage=%s provider=%s event=retry attempt=%s delay_ms=%s "
        "error_type=%s",
        capability,
        provider_name,
        attempt + 1,
        int(delay * 1000),
        type(exc).__name__,
    )
    started_at = time.monotonic()
    await asyncio.sleep(delay)
    logger.debug(
        "stage=%s provider=%s event=retry_wait_done duration_ms=%s",
        capability,
        provider_name,
        int((time.monotonic() - started_at) * 1000),
    )
