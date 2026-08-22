import asyncio
from typing import Any

import pytest

from lafvin_hat.ai import AnthropicLLM, Message
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


def test_anthropic_rejects_unsupported_message_roles() -> None:
    provider = AnthropicLLM(api_key="secret", model="claude-model")

    async def scenario() -> None:
        with pytest.raises(ValueError, match="Unsupported Anthropic message role"):
            await anext(provider.stream_chat([Message("tool", "result")]))

    asyncio.run(scenario())
