from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from .http_client import ReusableHTTPClient
from .models import LLMChunk, Message


@dataclass(frozen=True, slots=True)
class AnthropicConfig:
    base_url: str = "https://api.anthropic.com/v1"
    api_key: str | None = None
    timeout: float = 60.0
    version: str = "2023-06-01"

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("Anthropic base_url cannot be empty")
        if self.timeout <= 0:
            raise ValueError("Anthropic timeout must be positive")
        if not self.version.strip():
            raise ValueError("Anthropic API version cannot be empty")

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")

    def headers(self) -> dict[str, str]:
        headers = {
            "anthropic-version": self.version,
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers


class AnthropicLLM:
    def __init__(
        self,
        *,
        base_url: str = "https://api.anthropic.com/v1",
        api_key: str | None = None,
        model: str,
        max_tokens: int = 1024,
        timeout: float = 60.0,
        version: str = "2023-06-01",
        provider_name: str = "claude",
    ) -> None:
        if not model.strip():
            raise ValueError("Anthropic model cannot be empty")
        if max_tokens <= 0:
            raise ValueError("Anthropic max_tokens must be positive")
        self.config = AnthropicConfig(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            version=version,
        )
        self.model = model
        self.max_tokens = max_tokens
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
    ) -> AsyncIterator[LLMChunk]:
        system, conversation = _anthropic_messages(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": conversation,
            "stream": True,
        }
        if system:
            payload["system"] = system

        client = await self._http_client.get()
        async with client.stream(
            "POST",
            f"{self.config.normalized_base_url}/messages",
            headers=self.config.headers(),
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                value = json.loads(data)
                event_type = value.get("type")
                if event_type == "error":
                    error = value.get("error") or {}
                    message = error.get("message") or "unknown error"
                    raise RuntimeError(f"Anthropic stream failed: {message}")
                if event_type == "content_block_delta":
                    delta = value.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        text = delta.get("text")
                        if isinstance(text, str) and text:
                            yield LLMChunk(text=text)
                elif event_type == "message_delta":
                    delta = value.get("delta") or {}
                    finish_reason = delta.get("stop_reason")
                    if finish_reason is not None:
                        yield LLMChunk(
                            text="",
                            finish_reason=str(finish_reason),
                        )
                elif event_type == "message_stop":
                    return

    async def aclose(self) -> None:
        await self._http_client.aclose()


def _anthropic_messages(
    messages: list[Message],
) -> tuple[str, list[dict[str, str]]]:
    system: list[str] = []
    conversation: list[dict[str, str]] = []
    for message in messages:
        role = message.role.strip().lower()
        if role == "system":
            system.append(message.content)
        elif role in {"user", "assistant"}:
            conversation.append(
                {
                    "role": role,
                    "content": message.content,
                }
            )
        else:
            raise ValueError(f"Unsupported Anthropic message role: {message.role}")
    if not conversation:
        raise ValueError("Anthropic requires at least one user or assistant message")
    return "\n\n".join(system), conversation


def _httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError(
            'Anthropic provider requires: pip install -e ".[ai]"'
        ) from exc
    return httpx
