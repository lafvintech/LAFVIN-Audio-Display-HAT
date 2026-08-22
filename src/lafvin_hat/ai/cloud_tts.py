from __future__ import annotations

import asyncio
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .http_client import ReusableHTTPClient
from .models import AudioResult


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CloudTTSConfig:
    provider_name: str
    base_url: str
    api_key: str | None = None
    timeout: float = 60.0
    retries: int = 2

    def __post_init__(self) -> None:
        if not self.provider_name.strip():
            raise ValueError("TTS provider_name cannot be empty")
        if not self.base_url.strip():
            raise ValueError(f"{self.provider_name} TTS base_url cannot be empty")
        if self.timeout <= 0:
            raise ValueError(f"{self.provider_name} TTS timeout must be positive")
        if self.retries < 0:
            raise ValueError(
                f"{self.provider_name} TTS retries cannot be negative"
            )

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")

    def authorization_headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}


class MiniMaxTTS:
    def __init__(
        self,
        *,
        base_url: str = "https://api.minimaxi.com/v1",
        api_key: str | None = None,
        model: str = "speech-2.8-turbo",
        voice: str = "male-qn-qingse",
        timeout: float = 60.0,
        retries: int = 2,
    ) -> None:
        self.config = CloudTTSConfig(
            provider_name="MiniMax",
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            retries=retries,
        )
        self.model = _required_text(model, "MiniMax TTS model")
        self.voice = _required_text(voice, "MiniMax TTS voice")
        self._http_client = ReusableHTTPClient(
            capability="tts",
            provider_name=self.config.provider_name,
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
        payload = {
            "model": self.model,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": self.voice,
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
        response = await _post_with_retries(
            httpx,
            await self._http_client.get(),
            self.config,
            f"{self.config.normalized_base_url}/t2a_v2",
            headers={
                **self.config.authorization_headers(),
                "Content-Type": "application/json",
            },
            json=payload,
        )
        value = response.json()
        if not isinstance(value, dict):
            raise RuntimeError("MiniMax TTS response is not a JSON object")
        base_response = value.get("base_resp")
        status_code = (
            base_response.get("status_code")
            if isinstance(base_response, dict)
            else None
        )
        if status_code != 0:
            status_message = (
                base_response.get("status_msg")
                if isinstance(base_response, dict)
                else None
            )
            raise RuntimeError(
                "MiniMax TTS request failed: "
                f"status_code={status_code}, status_msg={status_message!r}"
            )
        data = value.get("data")
        if not isinstance(data, dict) or data.get("status") != 2:
            raise RuntimeError("MiniMax TTS response did not finish successfully")
        audio_hex = data.get("audio")
        if not isinstance(audio_hex, str) or not audio_hex:
            raise RuntimeError("MiniMax TTS response does not contain audio")
        try:
            audio = bytes.fromhex(audio_hex)
        except ValueError as exc:
            raise RuntimeError("MiniMax TTS audio is not valid hexadecimal") from exc
        return _write_wav(audio, output_path)

    async def aclose(self) -> None:
        await self._http_client.aclose()


class FishAudioTTS:
    _LATENCIES = {"low", "balanced", "normal"}

    def __init__(
        self,
        *,
        base_url: str = "https://api.fish.audio/v1",
        api_key: str | None = None,
        model: str = "s2.1-pro",
        voice: str | None = None,
        latency: str = "balanced",
        timeout: float = 60.0,
        retries: int = 2,
    ) -> None:
        self.config = CloudTTSConfig(
            provider_name="Fish Audio",
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            retries=retries,
        )
        self.model = _required_text(model, "Fish Audio TTS model")
        self.voice = voice.strip() if voice and voice.strip() else None
        self.latency = latency.strip().lower()
        if self.latency not in self._LATENCIES:
            values = ", ".join(sorted(self._LATENCIES))
            raise ValueError(f"Fish Audio TTS latency must be one of: {values}")
        self._http_client = ReusableHTTPClient(
            capability="tts",
            provider_name=self.config.provider_name,
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
        payload: dict[str, object] = {
            "text": text,
            "format": "wav",
            "sample_rate": 24000,
            "normalize": True,
            "latency": self.latency,
        }
        if self.voice:
            payload["reference_id"] = self.voice
        response = await _post_with_retries(
            httpx,
            await self._http_client.get(),
            self.config,
            f"{self.config.normalized_base_url}/tts",
            headers={
                **self.config.authorization_headers(),
                "Content-Type": "application/json",
                "model": self.model,
            },
            json=payload,
        )
        return _write_wav(response.content, output_path)

    async def aclose(self) -> None:
        await self._http_client.aclose()


async def _post_with_retries(
    httpx: Any,
    client: Any,
    config: CloudTTSConfig,
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, object],
) -> Any:
    for attempt in range(config.retries + 1):
        try:
            response = await client.post(
                url,
                headers=headers,
                json=json,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            if not _should_retry(httpx, exc, attempt, config):
                raise _request_error(config, exc) from exc
            await _wait_before_retry(config.provider_name, attempt, exc)
    raise RuntimeError(f"{config.provider_name} TTS request did not complete")


def _request_error(config: CloudTTSConfig, exc: Exception) -> RuntimeError:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is None:
        return RuntimeError(
            f"{config.provider_name} TTS request failed: {exc}"
        )
    detail = _response_detail(response)
    suffix = f": {detail}" if detail else ""
    return RuntimeError(
        f"{config.provider_name} TTS request failed: HTTP {status_code}{suffix}"
    )


def _response_detail(response: Any) -> str:
    try:
        value = response.json()
    except Exception:
        value = getattr(response, "text", "")
    detail = str(value).strip()
    return detail[:500]


def _write_wav(
    audio: bytes,
    output_path: str | Path | None,
) -> AudioResult:
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise RuntimeError("TTS response does not contain valid WAV audio")
    path = (
        Path(output_path)
        if output_path is not None
        else Path(tempfile.mkdtemp(prefix="lafvin-tts-")) / "speech.wav"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return AudioResult(path=path)


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty")
    return normalized


def _httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError(
            'Cloud TTS providers require: pip install -e ".[ai]"'
        ) from exc
    return httpx


def _should_retry(
    httpx: Any,
    exc: Exception,
    attempt: int,
    config: CloudTTSConfig,
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
    provider_name: str,
    attempt: int,
    exc: Exception,
) -> None:
    delay = min(4.0, 0.5 * (2**attempt))
    logger.warning(
        "stage=tts provider=%s event=retry attempt=%s delay_ms=%s "
        "error_type=%s",
        provider_name,
        attempt + 1,
        int(delay * 1000),
        type(exc).__name__,
    )
    await asyncio.sleep(delay)
