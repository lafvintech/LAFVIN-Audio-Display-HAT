from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .http_client import ReusableHTTPClient


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FishAudioASRConfig:
    base_url: str = "https://api.fish.audio/v1"
    api_key: str | None = None
    timeout: float = 60.0
    retries: int = 2

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("Fish Audio ASR base_url cannot be empty")
        if self.timeout <= 0:
            raise ValueError("Fish Audio ASR timeout must be positive")
        if self.retries < 0:
            raise ValueError("Fish Audio ASR retries cannot be negative")

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")

    def authorization_headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}


class FishAudioASR:
    _MODEL = "transcribe-1"

    def __init__(
        self,
        *,
        base_url: str = "https://api.fish.audio/v1",
        api_key: str | None = None,
        model: str = _MODEL,
        language: str | None = None,
        timeout: float = 60.0,
        retries: int = 2,
    ) -> None:
        self.config = FishAudioASRConfig(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            retries=retries,
        )
        self.model = model.strip()
        if self.model != self._MODEL:
            raise ValueError(
                "Fish Audio ASR model must be transcribe-1; "
                "set FISH_AUDIO_ASR_MODEL=transcribe-1"
            )
        self.language = (
            language.strip() if language and language.strip() else None
        )
        self._http_client = ReusableHTTPClient(
            capability="asr",
            provider_name="Fish Audio",
            timeout=timeout,
            httpx_loader=_httpx,
        )

    async def transcribe(self, audio_path: str | Path) -> str:
        httpx = _httpx()
        path = Path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(path)

        form_data = {"ignore_timestamps": "true"}
        if self.language:
            form_data["language"] = self.language

        client = await self._http_client.get()
        for attempt in range(self.config.retries + 1):
            try:
                with path.open("rb") as audio:
                    response = await client.post(
                        f"{self.config.normalized_base_url}/asr",
                        headers=self.config.authorization_headers(),
                        data=form_data,
                        files={
                            "audio": (path.name, audio, "audio/wav"),
                        },
                    )
                response.raise_for_status()
                break
            except Exception as exc:
                if not _should_retry(httpx, exc, attempt, self.config):
                    raise _request_error(exc) from exc
                await _wait_before_retry(attempt, exc)

        value = response.json()
        if not isinstance(value, dict):
            raise RuntimeError("Fish Audio ASR response is not a JSON object")
        text = value.get("text")
        if not isinstance(text, str):
            raise RuntimeError("Fish Audio ASR response does not contain text")
        return text

    async def aclose(self) -> None:
        await self._http_client.aclose()


def _httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError(
            'Fish Audio ASR requires: pip install -e ".[ai]"'
        ) from exc
    return httpx


def _should_retry(
    httpx: Any,
    exc: Exception,
    attempt: int,
    config: FishAudioASRConfig,
) -> bool:
    if attempt >= config.retries:
        return False
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status in {408, 409, 429} or status >= 500
    return False


def _request_error(exc: Exception) -> RuntimeError:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is None:
        return RuntimeError(f"Fish Audio ASR request failed: {exc}")
    detail = _response_detail(response)
    suffix = f": {detail}" if detail else ""
    return RuntimeError(
        f"Fish Audio ASR request failed: HTTP {status_code}{suffix}"
    )


def _response_detail(response: Any) -> str:
    try:
        value = response.json()
    except Exception:
        value = getattr(response, "text", "")
    return str(value).strip()[:500]


async def _wait_before_retry(attempt: int, exc: Exception) -> None:
    delay = min(4.0, 0.5 * (2**attempt))
    logger.warning(
        "stage=asr provider=Fish Audio event=retry attempt=%s delay_ms=%s "
        "error_type=%s",
        attempt + 1,
        int(delay * 1000),
        type(exc).__name__,
    )
    await asyncio.sleep(delay)
