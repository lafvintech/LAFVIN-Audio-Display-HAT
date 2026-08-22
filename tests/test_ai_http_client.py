import asyncio
import logging
from typing import Any

import pytest

from lafvin_hat.ai.http_client import (
    HTTPClientLifecycleError,
    ReusableHTTPClient,
)


class FakeClient:
    def __init__(self, owner: "FakeHTTPX", **kwargs: Any) -> None:
        self.owner = owner
        self.kwargs = kwargs
        self.close_calls = 0
        owner.clients.append(self)

    async def aclose(self) -> None:
        self.close_calls += 1
        if self.owner.close_error is not None:
            raise self.owner.close_error


class FakeHTTPX:
    def __init__(self) -> None:
        self.clients: list[FakeClient] = []
        self.limits: list[dict[str, Any]] = []
        self.close_error: Exception | None = None

    def Limits(self, **kwargs: Any) -> dict[str, Any]:
        self.limits.append(kwargs)
        return kwargs

    def AsyncClient(self, **kwargs: Any) -> FakeClient:
        return FakeClient(self, **kwargs)


def test_reusable_http_client_creates_once_and_closes_once() -> None:
    fake_httpx = FakeHTTPX()
    owner = ReusableHTTPClient(
        capability="tts",
        provider_name="Fish Audio",
        timeout=12,
        httpx_loader=lambda: fake_httpx,
    )

    async def scenario() -> None:
        first, second = await asyncio.gather(owner.get(), owner.get())
        assert first is second
        assert len(fake_httpx.clients) == 1
        assert first.kwargs == {
            "timeout": 12,
            "limits": {
                "max_connections": 2,
                "max_keepalive_connections": 1,
                "keepalive_expiry": 60.0,
            },
        }

        await owner.aclose()
        await owner.aclose()
        assert first.close_calls == 1

    asyncio.run(scenario())


def test_reusable_http_client_reports_use_after_close(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_httpx = FakeHTTPX()
    owner = ReusableHTTPClient(
        capability="asr",
        provider_name="Fish Audio",
        timeout=60,
        httpx_loader=lambda: fake_httpx,
    )
    caplog.set_level(logging.ERROR, logger="lafvin_hat.ai.http_client")

    async def scenario() -> None:
        await owner.aclose()
        with pytest.raises(
            HTTPClientLifecycleError,
            match="Fish Audio ASR HTTP client has already been closed",
        ):
            await owner.get()

    asyncio.run(scenario())

    assert "event=use_after_close capability=asr provider=Fish Audio" in (
        caplog.text
    )


def test_reusable_http_client_reports_creation_location(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_to_import() -> Any:
        raise ImportError("httpx unavailable")

    owner = ReusableHTTPClient(
        capability="llm",
        provider_name="DeepSeek",
        timeout=60,
        httpx_loader=fail_to_import,
    )
    caplog.set_level(logging.ERROR, logger="lafvin_hat.ai.http_client")

    async def scenario() -> None:
        with pytest.raises(
            HTTPClientLifecycleError,
            match="Failed to create DeepSeek LLM HTTP client",
        ):
            await owner.get()

    asyncio.run(scenario())

    assert "event=create_failed capability=llm provider=DeepSeek" in caplog.text


def test_reusable_http_client_reports_close_location(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_httpx = FakeHTTPX()
    fake_httpx.close_error = RuntimeError("socket cleanup failed")
    owner = ReusableHTTPClient(
        capability="tts",
        provider_name="MiniMax",
        timeout=60,
        httpx_loader=lambda: fake_httpx,
    )
    caplog.set_level(logging.ERROR, logger="lafvin_hat.ai.http_client")

    async def scenario() -> None:
        client = await owner.get()
        with pytest.raises(
            HTTPClientLifecycleError,
            match="Failed to close MiniMax TTS HTTP client",
        ):
            await owner.aclose()
        await owner.aclose()
        assert client.close_calls == 1

    asyncio.run(scenario())

    assert "event=close_failed capability=tts provider=MiniMax" in caplog.text
