import asyncio
from pathlib import Path
from typing import Any

import pytest

from lafvin_hat.ai import (
    Message,
    OpenAICompatibleASR,
    OpenAICompatibleLLM,
    OpenAICompatibleTTS,
)
from lafvin_hat.ai import openai_compatible


class FakeTransportError(Exception):
    pass


class FakeHTTPStatusError(Exception):
    def __init__(self, response: "FakeResponse") -> None:
        super().__init__(f"HTTP {response.status_code}")
        self.response = response


class FakeResponse:
    def __init__(
        self,
        *,
        json_value: object | None = None,
        content: bytes = b"",
        lines: list[str] | None = None,
        status_code: int = 200,
    ) -> None:
        self._json_value = json_value
        self.content = content
        self.lines = lines or []
        self.status_code = status_code
        self.context_exit_calls = 0

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise FakeHTTPStatusError(self)

    def json(self) -> object:
        return self._json_value

    async def aiter_lines(self):
        for line in self.lines:
            yield line


class FakeStreamContext:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    async def __aenter__(self) -> FakeResponse:
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        self.response.context_exit_calls += 1
        return None


class CancellableResponse(FakeResponse):
    def __init__(self) -> None:
        super().__init__()
        self.waiting = asyncio.Event()

    async def aiter_lines(self):
        yield 'data: {"choices":[{"delta":{"content":"partial"}}]}'
        self.waiting.set()
        await asyncio.Event().wait()


class BlockingPost:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def wait(self) -> FakeResponse:
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class FakeClient:
    def __init__(self, owner: "FakeHTTPX", **kwargs: Any) -> None:
        self.owner = owner
        self.kwargs = kwargs
        self.close_calls = 0
        owner.clients.append(self)

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.owner.calls.append({"method": "POST", "url": url, **kwargs})
        result = self.owner.post_results.pop(0)
        if isinstance(result, BlockingPost):
            return await result.wait()
        if isinstance(result, Exception):
            raise result
        return result

    def stream(self, method: str, url: str, **kwargs: Any) -> FakeStreamContext:
        self.owner.calls.append({"method": method, "url": url, **kwargs})
        return FakeStreamContext(self.owner.stream_results.pop(0))

    async def aclose(self) -> None:
        self.close_calls += 1


class FakeHTTPX:
    HTTPStatusError = FakeHTTPStatusError
    TransportError = FakeTransportError

    def __init__(self) -> None:
        self.clients: list[FakeClient] = []
        self.calls: list[dict[str, Any]] = []
        self.post_results: list[FakeResponse | BlockingPost | Exception] = []
        self.stream_results: list[FakeResponse] = []

    @staticmethod
    def Limits(**kwargs: Any) -> dict[str, Any]:
        return kwargs

    def AsyncClient(self, **kwargs: Any) -> FakeClient:
        return FakeClient(self, **kwargs)


@pytest.fixture
def fake_httpx(monkeypatch: pytest.MonkeyPatch) -> FakeHTTPX:
    value = FakeHTTPX()
    monkeypatch.setattr(openai_compatible, "_httpx", lambda: value)
    return value


def test_openai_capabilities_reuse_separate_clients(
    tmp_path: Path,
    fake_httpx: FakeHTTPX,
) -> None:
    recording = tmp_path / "recording.wav"
    recording.write_bytes(b"RIFFaudio")
    fake_httpx.post_results = [
        FakeResponse(json_value={"text": "first"}),
        FakeResponse(json_value={"text": "second"}),
        FakeResponse(content=b"RIFFspeech-one"),
        FakeResponse(content=b"RIFFspeech-two"),
    ]
    fake_httpx.stream_results = [
        _llm_response("one"),
        _llm_response("two"),
    ]
    asr = OpenAICompatibleASR(
        base_url="https://openai.invalid/v1",
        provider_name="openai",
    )
    llm = OpenAICompatibleLLM(
        base_url="https://deepseek.invalid",
        provider_name="deepseek",
    )
    tts = OpenAICompatibleTTS(
        base_url="https://openai.invalid/v1",
        provider_name="openai",
    )

    async def scenario() -> None:
        assert await asr.transcribe(recording) == "first"
        assert await asr.transcribe(recording) == "second"
        assert await _collect(llm) == "one"
        assert await _collect(llm) == "two"
        await tts.synthesize("one", output_path=tmp_path / "one.wav")
        await tts.synthesize("two", output_path=tmp_path / "two.wav")

        assert len(fake_httpx.clients) == 3
        await asr.aclose()
        await llm.aclose()
        await tts.aclose()
        assert [client.close_calls for client in fake_httpx.clients] == [1, 1, 1]

    asyncio.run(scenario())


def test_openai_retry_reuses_the_same_client(
    tmp_path: Path,
    fake_httpx: FakeHTTPX,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recording = tmp_path / "recording.wav"
    recording.write_bytes(b"RIFFaudio")
    fake_httpx.post_results = [
        FakeTransportError("connection reset"),
        FakeResponse(json_value={"text": "recovered"}),
    ]
    provider = OpenAICompatibleASR(
        base_url="https://openai.invalid/v1",
        retries=1,
    )

    async def no_wait(*_args: object) -> None:
        return None

    monkeypatch.setattr(openai_compatible, "_wait_before_retry", no_wait)

    async def scenario() -> None:
        assert await provider.transcribe(recording) == "recovered"
        assert len(fake_httpx.clients) == 1
        assert len(fake_httpx.calls) == 2
        await provider.aclose()

    asyncio.run(scenario())


def test_cancelled_llm_stream_releases_response_but_keeps_client_reusable(
    fake_httpx: FakeHTTPX,
) -> None:
    provider = OpenAICompatibleLLM(
        base_url="https://deepseek.invalid",
        provider_name="deepseek",
    )

    async def scenario() -> None:
        cancelled_response = CancellableResponse()
        fake_httpx.stream_results.append(cancelled_response)

        async def consume_cancelled_stream() -> None:
            async for _chunk in provider.stream_chat(
                [Message("user", "cancel this")]
            ):
                pass

        task = asyncio.create_task(consume_cancelled_stream())
        await cancelled_response.waiting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert cancelled_response.context_exit_calls == 1
        assert len(fake_httpx.clients) == 1
        assert fake_httpx.clients[0].close_calls == 0

        fake_httpx.stream_results.append(_llm_response("recovered"))
        assert await _collect(provider) == "recovered"
        assert len(fake_httpx.clients) == 1

        await provider.aclose()
        assert fake_httpx.clients[0].close_calls == 1

    asyncio.run(scenario())


def test_cancelled_tts_request_keeps_client_reusable(
    tmp_path: Path,
    fake_httpx: FakeHTTPX,
) -> None:
    provider = OpenAICompatibleTTS(
        base_url="https://openai.invalid/v1",
        provider_name="openai",
    )

    async def scenario() -> None:
        blocked = BlockingPost()
        fake_httpx.post_results.append(blocked)
        task = asyncio.create_task(
            provider.synthesize(
                "cancel this",
                output_path=tmp_path / "cancelled.wav",
            )
        )
        await blocked.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(fake_httpx.clients) == 1
        assert fake_httpx.clients[0].close_calls == 0

        fake_httpx.post_results.append(
            FakeResponse(content=b"RIFFrecovered")
        )
        result = await provider.synthesize(
            "try again",
            output_path=tmp_path / "recovered.wav",
        )
        assert result.path.read_bytes() == b"RIFFrecovered"
        assert len(fake_httpx.clients) == 1

        await provider.aclose()
        assert fake_httpx.clients[0].close_calls == 1

    asyncio.run(scenario())


async def _collect(provider: OpenAICompatibleLLM) -> str:
    return "".join([
        chunk.text
        async for chunk in provider.stream_chat([Message("user", "hello")])
    ])


def _llm_response(text: str) -> FakeResponse:
    return FakeResponse(
        lines=[
            f'data: {{"choices":[{{"delta":{{"content":"{text}"}}}}]}}',
            "data: [DONE]",
        ]
    )
