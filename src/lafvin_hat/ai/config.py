from __future__ import annotations

import os
from dataclasses import dataclass

from .fake import FakeASRProvider, FakeLLMProvider, FakeTTSProvider
from .openai_compatible import (
    OpenAICompatibleASR,
    OpenAICompatibleLLM,
    OpenAICompatibleTTS,
)
from .providers import ASRProvider, LLMProvider, TTSProvider


@dataclass(frozen=True, slots=True)
class AIProviderSet:
    asr: ASRProvider
    llm: LLMProvider
    tts: TTSProvider


class AIConfigurationError(ValueError):
    pass


def providers_from_environment(
    *,
    fake_transcript: str = "What can this platform do?",
    fake_response: str = "This is a deterministic response.",
    require_explicit: bool = False,
) -> AIProviderSet:
    common_provider = os.getenv("LAFVIN_AI_PROVIDER")
    if require_explicit and not common_provider and not any(
        os.getenv(name)
        for name in (
            "LAFVIN_ASR_PROVIDER",
            "LAFVIN_LLM_PROVIDER",
            "LAFVIN_TTS_PROVIDER",
        )
    ):
        raise AIConfigurationError(
            "LAFVIN_AI_PROVIDER is not configured. Set it to "
            "openai-compatible and provide OPENAI_API_KEY."
        )
    common_provider = common_provider or "fake"
    asr_provider = os.getenv("LAFVIN_ASR_PROVIDER", common_provider)
    llm_provider = os.getenv("LAFVIN_LLM_PROVIDER", common_provider)
    tts_provider = os.getenv("LAFVIN_TTS_PROVIDER", common_provider)
    if require_explicit:
        _validate_provider_credentials(
            {
                "ASR": asr_provider,
                "LLM": llm_provider,
                "TTS": tts_provider,
            }
        )
    return AIProviderSet(
        asr=_create_asr(asr_provider, fake_transcript),
        llm=_create_llm(llm_provider, fake_response),
        tts=_create_tts(tts_provider),
    )


def _validate_provider_credentials(providers: dict[str, str]) -> None:
    for capability, provider in providers.items():
        if provider != "openai-compatible":
            continue
        if not _api_key(capability):
            raise AIConfigurationError(
                f"{capability} provider is openai-compatible but no API key "
                f"is configured. Set LAFVIN_{capability}_API_KEY or "
                "OPENAI_API_KEY."
            )


def _create_asr(provider: str, fake_transcript: str) -> ASRProvider:
    if provider == "fake":
        return FakeASRProvider(
            transcript=os.getenv(
                "LAFVIN_FAKE_ASR_TRANSCRIPT",
                fake_transcript,
            )
        )
    if provider == "openai-compatible":
        return OpenAICompatibleASR(
            base_url=_base_url("ASR"),
            api_key=_api_key("ASR"),
            model=os.getenv("LAFVIN_ASR_MODEL", "whisper-1"),
            timeout=_timeout("ASR"),
            retries=_retries("ASR"),
        )
    raise ValueError(f"Unsupported ASR provider: {provider}")


def _create_llm(provider: str, fake_response: str) -> LLMProvider:
    if provider == "fake":
        return FakeLLMProvider(
            response=os.getenv(
                "LAFVIN_FAKE_LLM_RESPONSE",
                fake_response,
            ),
            chunk_size=_positive_int("LAFVIN_FAKE_LLM_CHUNK_SIZE", 8),
        )
    if provider == "openai-compatible":
        return OpenAICompatibleLLM(
            base_url=_base_url("LLM"),
            api_key=_api_key("LLM"),
            model=os.getenv("LAFVIN_LLM_MODEL", "gpt-4o-mini"),
            timeout=_timeout("LLM"),
            retries=_retries("LLM"),
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")


def _create_tts(provider: str) -> TTSProvider:
    if provider == "fake":
        return FakeTTSProvider()
    if provider == "openai-compatible":
        return OpenAICompatibleTTS(
            base_url=_base_url("TTS"),
            api_key=_api_key("TTS"),
            model=os.getenv("LAFVIN_TTS_MODEL", "tts-1"),
            voice=os.getenv("LAFVIN_TTS_VOICE", "alloy"),
            timeout=_timeout("TTS"),
            retries=_retries("TTS"),
        )
    raise ValueError(f"Unsupported TTS provider: {provider}")


def _base_url(capability: str) -> str:
    value = (
        os.getenv(f"LAFVIN_{capability}_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    return value.rstrip("/")


def _api_key(capability: str) -> str | None:
    return (
        os.getenv(f"LAFVIN_{capability}_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


def _timeout(capability: str) -> float:
    name = f"LAFVIN_{capability}_TIMEOUT_SEC"
    raw = os.getenv(name, os.getenv("LAFVIN_AI_TIMEOUT_SEC", "60"))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _retries(capability: str) -> int:
    name = f"LAFVIN_{capability}_RETRIES"
    raw = os.getenv(name, os.getenv("LAFVIN_AI_RETRIES", "2"))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value
