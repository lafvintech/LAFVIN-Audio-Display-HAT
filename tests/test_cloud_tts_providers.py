import asyncio
from pathlib import Path
from typing import Any

import pytest

from lafvin_hat.ai import FishAudioTTS, MiniMaxTTS
from lafvin_hat.ai import cloud_tts


WAV_AUDIO = b"RIFF\x04\x00\x00\x00WAVEdata"


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
        content: bytes = b"",
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_value = json_value
        self.content = content
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise FakeHTTPStatusError(self)

    def json(self) -> object:
        if self._json_value is None:
            raise ValueError("response is not JSON")
        return self._json_value


class FakeAsyncClient:
    responses: list[FakeResponse] = []
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
        json: dict[str, object],
    ) -> FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": self.timeout,
            }
        )
        return self.responses.pop(0)

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
    monkeypatch.setattr(cloud_tts, "_httpx", lambda: FakeHTTPX)


def test_minimax_tts_writes_wav_and_uses_expected_request(
    tmp_path: Path,
) -> None:
    FakeAsyncClient.responses = [
        FakeResponse(
            json_value={
                "data": {"audio": WAV_AUDIO.hex(), "status": 2},
                "base_resp": {"status_code": 0, "status_msg": "success"},
            }
        )
    ]
    provider = MiniMaxTTS(
        base_url="https://minimax.invalid/v1/",
        api_key="minimax-secret",
        model="speech-model",
        voice="voice-id",
        timeout=12,
        retries=0,
    )
    output_path = tmp_path / "speech.wav"

    result = asyncio.run(provider.synthesize("你好", output_path=output_path))

    assert result.path == output_path
    assert output_path.read_bytes() == WAV_AUDIO
    call = FakeAsyncClient.calls[0]
    assert call["url"] == "https://minimax.invalid/v1/t2a_v2"
    assert call["headers"]["Authorization"] == "Bearer minimax-secret"
    assert call["json"] == {
        "model": "speech-model",
        "text": "你好",
        "stream": False,
        "voice_setting": {
            "voice_id": "voice-id",
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 24000,
            "bitrate": 128000,
            "format": "wav",
            "channel": 1,
        },
    }
    assert call["timeout"] == 12


def test_minimax_tts_reports_api_status_error(tmp_path: Path) -> None:
    FakeAsyncClient.responses = [
        FakeResponse(
            json_value={
                "base_resp": {
                    "status_code": 1004,
                    "status_msg": "authentication failed",
                }
            }
        )
    ]
    provider = MiniMaxTTS(api_key="invalid", retries=0)

    with pytest.raises(RuntimeError, match="authentication failed"):
        asyncio.run(
            provider.synthesize("test", output_path=tmp_path / "speech.wav")
        )


def test_fish_audio_tts_writes_direct_wav_and_uses_reference_id(
    tmp_path: Path,
) -> None:
    FakeAsyncClient.responses = [FakeResponse(content=WAV_AUDIO)]
    provider = FishAudioTTS(
        base_url="https://fish.invalid/v1/",
        api_key="fish-secret",
        model="s2.1-pro",
        voice="reference-id",
        latency="low",
        retries=0,
    )
    output_path = tmp_path / "speech.wav"

    result = asyncio.run(provider.synthesize("Hello", output_path=output_path))

    assert result.path == output_path
    assert output_path.read_bytes() == WAV_AUDIO
    call = FakeAsyncClient.calls[0]
    assert call["url"] == "https://fish.invalid/v1/tts"
    assert call["headers"]["Authorization"] == "Bearer fish-secret"
    assert call["headers"]["model"] == "s2.1-pro"
    assert call["json"] == {
        "text": "Hello",
        "format": "wav",
        "sample_rate": 24000,
        "normalize": True,
        "latency": "low",
        "reference_id": "reference-id",
    }


def test_fish_audio_tts_allows_default_voice(tmp_path: Path) -> None:
    FakeAsyncClient.responses = [FakeResponse(content=WAV_AUDIO)]
    provider = FishAudioTTS(api_key="fish-secret", voice=None, retries=0)

    asyncio.run(
        provider.synthesize("Hello", output_path=tmp_path / "speech.wav")
    )

    assert "reference_id" not in FakeAsyncClient.calls[0]["json"]


def test_cloud_tts_rejects_non_wav_response(tmp_path: Path) -> None:
    FakeAsyncClient.responses = [FakeResponse(content=b'{"error":"failed"}')]
    provider = FishAudioTTS(api_key="fish-secret", retries=0)

    with pytest.raises(RuntimeError, match="valid WAV"):
        asyncio.run(
            provider.synthesize("test", output_path=tmp_path / "speech.wav")
        )

    assert not (tmp_path / "speech.wav").exists()


def test_cloud_tts_http_error_includes_safe_response_detail(
    tmp_path: Path,
) -> None:
    FakeAsyncClient.responses = [
        FakeResponse(
            status_code=401,
            json_value={"message": "invalid token"},
        )
    ]
    provider = FishAudioTTS(api_key="invalid", retries=0)

    with pytest.raises(RuntimeError, match=r"HTTP 401.*invalid token"):
        asyncio.run(
            provider.synthesize("test", output_path=tmp_path / "speech.wav")
        )


def test_fish_audio_rejects_unknown_latency() -> None:
    with pytest.raises(ValueError, match="latency must be one of"):
        FishAudioTTS(latency="fastest")


@pytest.mark.parametrize("provider_type", [MiniMaxTTS, FishAudioTTS])
def test_cloud_tts_reuses_client_and_closes_once(
    tmp_path: Path,
    provider_type: type[MiniMaxTTS] | type[FishAudioTTS],
) -> None:
    if provider_type is MiniMaxTTS:
        response = FakeResponse(
            json_value={
                "data": {"audio": WAV_AUDIO.hex(), "status": 2},
                "base_resp": {"status_code": 0, "status_msg": "success"},
            }
        )
    else:
        response = FakeResponse(content=WAV_AUDIO)
    FakeAsyncClient.responses = [response, response]
    provider = provider_type(api_key="secret", retries=0)

    async def scenario() -> None:
        await provider.synthesize("one", output_path=tmp_path / "one.wav")
        await provider.synthesize("two", output_path=tmp_path / "two.wav")
        assert FakeAsyncClient.instances == 1
        await provider.aclose()
        await provider.aclose()
        assert FakeAsyncClient.close_calls == 1

    asyncio.run(scenario())
