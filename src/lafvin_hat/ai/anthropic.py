from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

from .http_client import ReusableHTTPClient
from .models import LLMChunk, Message, ToolCall, ToolDefinition
from .providers import ToolExecutor


logger = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 3


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
        *,
        tools: Sequence[ToolDefinition] = (),
        tool_executor: ToolExecutor | None = None,
    ) -> AsyncIterator[LLMChunk]:
        active_messages = list(messages)
        client = await self._http_client.get()
        for tool_round in range(MAX_TOOL_ROUNDS + 1):
            system, conversation = _anthropic_messages(active_messages)
            payload: dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": conversation,
                "stream": True,
            }
            if system:
                payload["system"] = system
            if tools:
                payload["tools"] = [_anthropic_tool(tool) for tool in tools]

            response_text = ""
            finish_reason: str | None = None
            tool_parts: dict[int, dict[str, str]] = {}
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
                        raise RuntimeError(
                            f"Anthropic stream failed: {message}"
                        )
                    if event_type == "content_block_start":
                        _start_anthropic_content_block(
                            tool_parts,
                            value,
                        )
                    elif event_type == "content_block_delta":
                        delta = value.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            text = delta.get("text")
                            if isinstance(text, str) and text:
                                response_text += text
                                yield LLMChunk(text=text)
                        elif delta.get("type") == "input_json_delta":
                            _append_anthropic_tool_input(tool_parts, value)
                    elif event_type == "message_delta":
                        delta = value.get("delta") or {}
                        raw_finish_reason = delta.get("stop_reason")
                        if raw_finish_reason is not None:
                            finish_reason = str(raw_finish_reason)

            tool_calls = _anthropic_tool_calls(tool_parts, tool_round)
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

            active_messages.append(
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
                active_messages.append(
                    Message(
                        "tool",
                        result,
                        tool_call_id=call.call_id,
                    )
                )

    async def aclose(self) -> None:
        await self._http_client.aclose()


def _anthropic_messages(
    messages: list[Message],
) -> tuple[str, list[dict[str, Any]]]:
    system: list[str] = []
    conversation: list[dict[str, Any]] = []
    for message in messages:
        role = message.role.strip().lower()
        if role == "system":
            system.append(message.content)
        elif role in {"user", "assistant"}:
            content: str | list[dict[str, Any]] = message.content
            if role == "assistant" and message.tool_calls:
                blocks: list[dict[str, Any]] = []
                if message.content:
                    blocks.append({"type": "text", "text": message.content})
                blocks.extend(
                    {
                        "type": "tool_use",
                        "id": call.call_id,
                        "name": call.name,
                        "input": call.arguments,
                    }
                    for call in message.tool_calls
                )
                content = blocks
            conversation.append(
                {
                    "role": role,
                    "content": content,
                }
            )
        elif role == "tool":
            if not message.tool_call_id:
                raise ValueError("Anthropic tool message requires tool_call_id")
            block = {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": message.content,
            }
            if conversation and conversation[-1].get("_tool_results"):
                conversation[-1]["content"].append(block)
            else:
                conversation.append(
                    {
                        "role": "user",
                        "content": [block],
                        "_tool_results": True,
                    }
                )
        else:
            raise ValueError(f"Unsupported Anthropic message role: {message.role}")
    for item in conversation:
        item.pop("_tool_results", None)
    if not conversation:
        raise ValueError("Anthropic requires at least one user or assistant message")
    return "\n\n".join(system), conversation


def _anthropic_tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.parameters,
    }


def _start_anthropic_content_block(
    tool_parts: dict[int, dict[str, str]],
    value: dict[str, Any],
) -> None:
    raw_index = value.get("index", 0)
    index = raw_index if isinstance(raw_index, int) else 0
    block = value.get("content_block") or {}
    if not isinstance(block, dict):
        return
    block_type = str(block.get("type") or "")
    if block_type != "tool_use":
        return
    initial_input = block.get("input")
    initial_json = (
        json.dumps(initial_input, ensure_ascii=False)
        if isinstance(initial_input, dict) and initial_input
        else ""
    )
    tool_parts[index] = {
        "id": str(block.get("id") or ""),
        "name": str(block.get("name") or ""),
        "arguments": initial_json,
    }


def _append_anthropic_tool_input(
    tool_parts: dict[int, dict[str, str]],
    value: dict[str, Any],
) -> None:
    raw_index = value.get("index", 0)
    index = raw_index if isinstance(raw_index, int) else 0
    buffer = tool_parts.get(index)
    delta = value.get("delta") or {}
    partial_json = delta.get("partial_json") if isinstance(delta, dict) else None
    if buffer is not None and isinstance(partial_json, str):
        buffer["arguments"] += partial_json


def _anthropic_tool_calls(
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
            'Anthropic provider requires: pip install -e ".[ai]"'
        ) from exc
    return httpx
