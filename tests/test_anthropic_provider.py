import asyncio
from typing import Any

import pytest

from lafvin_hat.ai import (
    AnthropicLLM,
    Message,
    ToolCall,
    ToolDefinition,
)
from lafvin_hat.ai import anthropic as anthropic_module


class _FakeResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _StreamContext:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeResponse:
        return self._response

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _FakeClient:
    def __init__(
        self,
        owner: "_FakeHTTPX",
        *,
        timeout: float,
        limits: object,
    ) -> None:
        self._owner = owner
        self._owner.timeout = timeout
        self._owner.limits = limits
        self._owner.client_count += 1

    def stream(self, method: str, url: str, **kwargs: Any) -> _StreamContext:
        self._owner.request = {
            "method": method,
            "url": url,
            **kwargs,
        }
        self._owner.requests.append(self._owner.request)
        return _StreamContext(_FakeResponse(self._owner.lines))

    async def aclose(self) -> None:
        self._owner.close_count += 1


class _FakeHTTPX:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.request: dict[str, Any] = {}
        self.requests: list[dict[str, Any]] = []
        self.timeout = 0.0
        self.limits: object | None = None
        self.client_count = 0
        self.close_count = 0

    @staticmethod
    def Limits(**kwargs: Any) -> dict[str, Any]:
        return kwargs

    def AsyncClient(self, *, timeout: float, limits: object) -> _FakeClient:
        return _FakeClient(self, timeout=timeout, limits=limits)


def test_anthropic_stream_maps_system_messages_and_text_deltas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_httpx = _FakeHTTPX(
        [
            "event: message_start",
            'data: {"type":"message_start"}',
            "event: content_block_delta",
            (
                'data: {"type":"content_block_delta","delta":'
                '{"type":"text_delta","text":"Hello"}}'
            ),
            (
                'data: {"type":"message_delta","delta":'
                '{"stop_reason":"end_turn"}}'
            ),
            'data: {"type":"message_stop"}',
        ]
    )
    monkeypatch.setattr(anthropic_module, "_httpx", lambda: fake_httpx)
    provider = AnthropicLLM(
        api_key="secret",
        model="claude-model",
        max_tokens=256,
    )

    async def scenario() -> None:
        chunks = [
            chunk
            async for chunk in provider.stream_chat(
                [
                    Message("system", "Be concise."),
                    Message("user", "Hi"),
                ]
            )
        ]
        repeated = [
            chunk
            async for chunk in provider.stream_chat([Message("user", "Again")])
        ]

        assert [chunk.text for chunk in chunks] == ["Hello", ""]
        assert chunks[-1].finish_reason == "end_turn"
        assert [chunk.text for chunk in repeated] == ["Hello", ""]
        assert fake_httpx.client_count == 1
        await provider.aclose()
        assert fake_httpx.close_count == 1

    asyncio.run(scenario())

    first_request = fake_httpx.requests[0]
    assert first_request["method"] == "POST"
    assert first_request["url"] == "https://api.anthropic.com/v1/messages"
    assert first_request["headers"]["x-api-key"] == "secret"
    assert first_request["json"] == {
        "model": "claude-model",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": True,
        "system": "Be concise.",
    }


def test_anthropic_tool_message_requires_call_id() -> None:
    provider = AnthropicLLM(api_key="secret", model="claude-model")

    async def scenario() -> None:
        with pytest.raises(ValueError, match="requires tool_call_id"):
            await anext(provider.stream_chat([Message("tool", "result")]))

    asyncio.run(scenario())


def test_anthropic_tool_use_executes_and_continues_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_httpx = _FakeHTTPX(
        [
            (
                'data: {"type":"content_block_start","index":0,'
                '"content_block":{"type":"tool_use","id":"tool-1",'
                '"name":"get_volume","input":{}}}'
            ),
            (
                'data: {"type":"content_block_delta","index":0,'
                '"delta":{"type":"input_json_delta","partial_json":"{}"}}'
            ),
            'data: {"type":"content_block_stop","index":0}',
            (
                'data: {"type":"message_delta",'
                '"delta":{"stop_reason":"tool_use"}}'
            ),
            'data: {"type":"message_stop"}',
        ]
    )
    monkeypatch.setattr(anthropic_module, "_httpx", lambda: fake_httpx)
    provider = AnthropicLLM(
        api_key="secret",
        model="claude-model",
        max_tokens=256,
    )
    definition = ToolDefinition(
        "get_volume",
        "Get speaker volume.",
        {"type": "object", "properties": {}},
    )
    observed: list[ToolCall] = []

    async def execute(call: ToolCall) -> str:
        observed.append(call)
        fake_httpx.lines = [
            (
                'data: {"type":"content_block_delta","index":0,'
                '"delta":{"type":"text_delta",'
                '"text":"The volume is 70%."}}'
            ),
            (
                'data: {"type":"message_delta",'
                '"delta":{"stop_reason":"end_turn"}}'
            ),
            'data: {"type":"message_stop"}',
        ]
        return '{"ok":true,"volume_percent":70}'

    async def scenario() -> None:
        result = "".join([
            chunk.text
            async for chunk in provider.stream_chat(
                [Message("user", "What is the volume?")],
                tools=[definition],
                tool_executor=execute,
            )
        ])

        assert result == "The volume is 70%."
        assert observed == [ToolCall("tool-1", "get_volume", {})]
        await provider.aclose()

    asyncio.run(scenario())

    assert len(fake_httpx.requests) == 2
    assert fake_httpx.requests[0]["json"]["tools"] == [
        {
            "name": "get_volume",
            "description": "Get speaker volume.",
            "input_schema": definition.parameters,
        }
    ]
    follow_up = fake_httpx.requests[1]["json"]["messages"]
    assert follow_up[-2]["content"] == [
        {
            "type": "tool_use",
            "id": "tool-1",
            "name": "get_volume",
            "input": {},
        }
    ]
    assert follow_up[-1]["content"] == [
        {
            "type": "tool_result",
            "tool_use_id": "tool-1",
            "content": '{"ok":true,"volume_percent":70}',
        }
    ]
