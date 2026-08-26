import asyncio
from pathlib import Path
from typing import Any

import pytest

from lafvin_hat.ai import FishAudioASR
from lafvin_hat.ai import fish_audio


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
        status_code: int = 200,
        json_value: object | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_value = json_value
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise FakeHTTPStatusError(self)

    def json(self) -> object:
        if self._json_value is None:
            raise ValueError("response is not JSON")
        return self._json_value


class FakeAsyncClient:
    responses: list[FakeResponse | Exception] = []
    calls: list[dict[str, Any]] = []
    instances = 0
    close_calls = 0

    def __init__(self, *, timeout: float, limits: object) -> None:
        self.timeout = timeout
        self.limits = limits
        type(self).instances += 1

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str],
        files: dict[str, tuple[str, Any, str]],
    ) -> FakeResponse:
        filename, audio, content_type = files["audio"]
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "data": data,
                "filename": filename,
                "audio": audio.read(),
                "content_type": content_type,
                "timeout": self.timeout,
            }
        )
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def aclose(self) -> None:
        type(self).close_calls += 1


class FakeHTTPX:
    AsyncClient = FakeAsyncClient
    HTTPStatusError = FakeHTTPStatusError
    TransportError = FakeTransportError

    @staticmethod
    def Limits(**kwargs: Any) -> dict[str, Any]:
        return kwargs


@pytest.fixture(autouse=True)
def fake_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.responses = []
    FakeAsyncClient.calls = []
    FakeAsyncClient.instances = 0
    FakeAsyncClient.close_calls = 0
    monkeypatch.setattr(fish_audio, "_httpx", lambda: FakeHTTPX)


def test_fish_audio_asr_uses_multipart_and_returns_text(
    tmp_path: Path,
) -> None:
    recording = tmp_path / "recording.wav"
    recording.write_bytes(b"RIFFaudio")
    FakeAsyncClient.responses = [
        FakeResponse(
            json_value={
                "text": "你好",
                "duration": 1.5,
                "segments": [],
            }
        )
    ]
    provider = FishAudioASR(
        base_url="https://fish.invalid/v1/",
        api_key="fish-secret",
        model="transcribe-1",
        language="zh",
        timeout=12,
        retries=0,
    )

    result = asyncio.run(provider.transcribe(recording))

    assert result == "你好"
    call = FakeAsyncClient.calls[0]
    assert call["url"] == "https://fish.invalid/v1/asr"
    assert call["headers"] == {"Authorization": "Bearer fish-secret"}
    assert call["data"] == {
        "ignore_timestamps": "true",
        "language": "zh",
    }
    assert call["filename"] == "recording.wav"
    assert call["audio"] == b"RIFFaudio"
    assert call["content_type"] == "audio/wav"
    assert call["timeout"] == 12


def test_fish_audio_asr_allows_language_auto_detection(
    tmp_path: Path,
) -> None:
    recording = tmp_path / "recording.wav"
    recording.write_bytes(b"RIFFaudio")
    FakeAsyncClient.responses = [FakeResponse(json_value={"text": "hello"})]
    provider = FishAudioASR(api_key="fish-secret", language=None, retries=0)

    assert asyncio.run(provider.transcribe(recording)) == "hello"
    assert FakeAsyncClient.calls[0]["data"] == {
        "ignore_timestamps": "true"
    }


def test_fish_audio_asr_reports_credit_error_without_retry(
    tmp_path: Path,
) -> None:
    recording = tmp_path / "recording.wav"
    recording.write_bytes(b"RIFFaudio")
    FakeAsyncClient.responses = [
        FakeResponse(
            status_code=402,
            json_value={"message": "Insufficient API credit"},
        ),
        FakeResponse(json_value={"text": "must not be used"}),
    ]
    provider = FishAudioASR(api_key="fish-secret", retries=2)

    with pytest.raises(
        RuntimeError,
        match=r"HTTP 402.*Insufficient API credit",
    ):
        asyncio.run(provider.transcribe(recording))

    assert len(FakeAsyncClient.calls) == 1


def test_fish_audio_asr_rejects_invalid_response(tmp_path: Path) -> None:
    recording = tmp_path / "recording.wav"
    recording.write_bytes(b"RIFFaudio")
    FakeAsyncClient.responses = [FakeResponse(json_value={"duration": 1.0})]
    provider = FishAudioASR(api_key="fish-secret", retries=0)

    with pytest.raises(RuntimeError, match="does not contain text"):
        asyncio.run(provider.transcribe(recording))


def test_fish_audio_asr_rejects_missing_audio(tmp_path: Path) -> None:
    provider = FishAudioASR(api_key="fish-secret", retries=0)

    with pytest.raises(FileNotFoundError):
        asyncio.run(provider.transcribe(tmp_path / "missing.wav"))


def test_fish_audio_asr_rejects_unsupported_model() -> None:
    with pytest.raises(ValueError, match="FISH_AUDIO_ASR_MODEL=transcribe-1"):
        FishAudioASR(model="whisper-1")


def test_fish_audio_asr_reuses_client_and_closes_once(tmp_path: Path) -> None:
    recording = tmp_path / "recording.wav"
    recording.write_bytes(b"RIFFaudio")
    FakeAsyncClient.responses = [
        FakeResponse(json_value={"text": "one"}),
        FakeResponse(json_value={"text": "two"}),
    ]
    provider = FishAudioASR(api_key="fish-secret", retries=0)

    async def scenario() -> None:
        assert await provider.transcribe(recording) == "one"
        assert await provider.transcribe(recording) == "two"
        assert FakeAsyncClient.instances == 1
        await provider.aclose()
        await provider.aclose()
        assert FakeAsyncClient.close_calls == 1

    asyncio.run(scenario())
