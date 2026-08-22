from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from .anthropic import AnthropicLLM
from .audio_normalization import NormalizedASRProvider, NormalizedTTSProvider
from .cloud_tts import FishAudioTTS, MiniMaxTTS
from .fake import FakeASRProvider, FakeLLMProvider, FakeTTSProvider
from .fish_audio import FishAudioASR
from .openai_compatible import (
    OpenAICompatibleASR,
    OpenAICompatibleLLM,
    OpenAICompatibleTTS,
)
from .providers import ASRProvider, LLMProvider, TTSProvider, aclose_provider
from .registry import AIProviderRegistry


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AIProviderSet:
    asr: ASRProvider
    llm: LLMProvider
    tts: TTSProvider

    async def aclose(self) -> None:
        failures: list[tuple[str, Exception]] = []
        closed_ids: set[int] = set()
        for capability, provider in (
            ("asr", self.asr),
            ("llm", self.llm),
            ("tts", self.tts),
        ):
            if id(provider) in closed_ids:
                continue
            closed_ids.add(id(provider))
            try:
                await aclose_provider(provider)
            except Exception as exc:
                logger.exception(
                    "stage=provider_shutdown event=close_failed "
                    "capability=%s provider_type=%s error_type=%s",
                    capability,
                    type(provider).__name__,
                    type(exc).__name__,
                )
                failures.append((capability, exc))
        if failures:
            capability, failure = failures[0]
            raise RuntimeError(
                f"Failed to close {capability.upper()} provider: {failure}"
            ) from failure


class AIConfigurationError(ValueError):
    pass


_PROVIDER_API_KEY_ENV = {
    "claude": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "fish": "FISH_AUDIO_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai-compatible": "LAFVIN_LLM_API_KEY",
}


def providers_from_environment(
    *,
    fake_transcript: str = "What can this platform do?",
    fake_response: str = "This is a deterministic response.",
    require_explicit: bool = False,
) -> AIProviderSet:
    common_provider = os.getenv("LAFVIN_AI_PROVIDER")
    capability_variables = {
        "ASR": "LAFVIN_ASR_PROVIDER",
        "LLM": "LAFVIN_LLM_PROVIDER",
        "TTS": "LAFVIN_TTS_PROVIDER",
    }
    if require_explicit and not common_provider:
        missing = [
            name
            for name in capability_variables.values()
            if not os.getenv(name)
        ]
        if missing:
            raise AIConfigurationError(
                "AI capability providers are not fully configured. Set "
                "LAFVIN_ASR_PROVIDER, LAFVIN_LLM_PROVIDER, and "
                f"LAFVIN_TTS_PROVIDER. Missing: {', '.join(missing)}."
            )
    fallback_provider = common_provider or "fake"
    asr_provider = os.getenv("LAFVIN_ASR_PROVIDER") or fallback_provider
    llm_provider = os.getenv("LAFVIN_LLM_PROVIDER") or fallback_provider
    tts_provider = os.getenv("LAFVIN_TTS_PROVIDER") or fallback_provider
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
        normalized = provider.strip().lower()
        if normalized == "openai-compatible" and capability != "LLM":
            continue
        key_name = _PROVIDER_API_KEY_ENV.get(normalized)
        if key_name is None:
            continue
        if not os.getenv(key_name):
            raise AIConfigurationError(
                f"{capability} provider is {normalized} but no API key "
                f"is configured. Set {key_name}."
            )


def _create_asr(provider: str, fake_transcript: str) -> ASRProvider:
    instance = provider_registry.create_asr(provider, fake_transcript)
    if provider.strip().lower() == "fake":
        return instance
    return NormalizedASRProvider(instance)


def _create_llm(provider: str, fake_response: str) -> LLMProvider:
    return provider_registry.create_llm(provider, fake_response)


def _create_tts(provider: str) -> TTSProvider:
    instance = provider_registry.create_tts(provider)
    if provider.strip().lower() == "fake":
        return instance
    return NormalizedTTSProvider(instance)


def _create_fake_asr(fake_transcript: str) -> ASRProvider:
    return FakeASRProvider(
        transcript=os.getenv(
            "LAFVIN_FAKE_ASR_TRANSCRIPT",
            fake_transcript,
        )
    )


def _create_openai_asr(_fake_transcript: str) -> ASRProvider:
    return OpenAICompatibleASR(
        base_url=_service_base_url(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ),
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("LAFVIN_ASR_MODEL", "whisper-1"),
        timeout=_timeout("ASR"),
        retries=_retries("ASR"),
        provider_name="openai",
    )


def _create_fish_asr(_fake_transcript: str) -> ASRProvider:
    return FishAudioASR(
        base_url=_service_base_url(
            "FISH_AUDIO_BASE_URL",
            "https://api.fish.audio/v1",
        ),
        api_key=os.getenv("FISH_AUDIO_API_KEY"),
        model=os.getenv("LAFVIN_ASR_MODEL", "transcribe-1"),
        language=os.getenv("LAFVIN_ASR_LANGUAGE"),
        timeout=_timeout("ASR"),
        retries=_retries("ASR"),
    )


def _create_fake_llm(fake_response: str) -> LLMProvider:
    return FakeLLMProvider(
        response=os.getenv(
            "LAFVIN_FAKE_LLM_RESPONSE",
            fake_response,
        ),
        chunk_size=_positive_int("LAFVIN_FAKE_LLM_CHUNK_SIZE", 8),
    )


def _create_openai_compatible_llm(_fake_response: str) -> LLMProvider:
    return OpenAICompatibleLLM(
        base_url=_custom_llm_base_url(),
        api_key=os.getenv("LAFVIN_LLM_API_KEY"),
        model=_required_model("LLM", "openai-compatible"),
        timeout=_timeout("LLM"),
        retries=_retries("LLM"),
        provider_name="openai-compatible",
    )


def _create_openai_llm(_fake_response: str) -> LLMProvider:
    return OpenAICompatibleLLM(
        base_url=_service_base_url(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ),
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("LAFVIN_LLM_MODEL", "gpt-4o-mini"),
        timeout=_timeout("LLM"),
        retries=_retries("LLM"),
        provider_name="openai",
    )


def _create_deepseek_llm(_fake_response: str) -> LLMProvider:
    return OpenAICompatibleLLM(
        base_url=_service_base_url(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com",
        ),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        model=_required_model("LLM", "deepseek"),
        timeout=_timeout("LLM"),
        retries=_retries("LLM"),
        provider_name="deepseek",
    )


def _create_kimi_llm(_fake_response: str) -> LLMProvider:
    return OpenAICompatibleLLM(
        base_url=_service_base_url(
            "MOONSHOT_BASE_URL",
            "https://api.moonshot.cn/v1",
        ),
        api_key=os.getenv("MOONSHOT_API_KEY"),
        model=_required_model("LLM", "kimi"),
        timeout=_timeout("LLM"),
        retries=_retries("LLM"),
        provider_name="kimi",
    )


def _create_claude_llm(_fake_response: str) -> LLMProvider:
    return AnthropicLLM(
        base_url=_service_base_url(
            "ANTHROPIC_BASE_URL",
            "https://api.anthropic.com/v1",
        ),
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        model=_required_model("LLM", "claude"),
        max_tokens=_positive_int("LAFVIN_LLM_MAX_TOKENS", 1024),
        timeout=_timeout("LLM"),
        version=os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
    )


def _create_fake_tts() -> TTSProvider:
    return FakeTTSProvider()


def _create_openai_tts() -> TTSProvider:
    return OpenAICompatibleTTS(
        base_url=_service_base_url(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ),
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("LAFVIN_TTS_MODEL", "tts-1"),
        voice=os.getenv("LAFVIN_TTS_VOICE", "alloy"),
        timeout=_timeout("TTS"),
        retries=_retries("TTS"),
        provider_name="openai",
    )


def _create_minimax_tts() -> TTSProvider:
    return MiniMaxTTS(
        base_url=_service_base_url(
            "MINIMAX_TTS_BASE_URL",
            "https://api.minimaxi.com/v1",
        ),
        api_key=os.getenv("MINIMAX_API_KEY"),
        model=os.getenv("LAFVIN_TTS_MODEL", "speech-2.8-turbo"),
        voice=os.getenv("LAFVIN_TTS_VOICE", "male-qn-qingse"),
        timeout=_timeout("TTS"),
        retries=_retries("TTS"),
    )


def _create_fish_tts() -> TTSProvider:
    return FishAudioTTS(
        base_url=_service_base_url(
            "FISH_AUDIO_BASE_URL",
            "https://api.fish.audio/v1",
        ),
        api_key=os.getenv("FISH_AUDIO_API_KEY"),
        model=os.getenv("LAFVIN_TTS_MODEL", "s2.1-pro"),
        voice=os.getenv("LAFVIN_TTS_VOICE"),
        latency=os.getenv("FISH_AUDIO_TTS_LATENCY", "balanced"),
        timeout=_timeout("TTS"),
        retries=_retries("TTS"),
    )


def _custom_llm_base_url() -> str:
    value = os.getenv("LAFVIN_LLM_BASE_URL", "").strip()
    if not value:
        raise AIConfigurationError(
            "LLM provider is openai-compatible but no endpoint is configured. "
            "Set LAFVIN_LLM_BASE_URL."
        )
    return value.rstrip("/")


def _service_base_url(
    provider_variable: str,
    default: str,
) -> str:
    value = os.getenv(provider_variable) or default
    return value.rstrip("/")


def _required_model(capability: str, provider: str) -> str:
    name = f"LAFVIN_{capability}_MODEL"
    value = os.getenv(name, "").strip()
    if not value:
        raise AIConfigurationError(
            f"{capability} provider is {provider} but no model is configured. "
            f"Set {name}."
        )
    return value


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


provider_registry = AIProviderRegistry()
provider_registry.register_asr("fake", _create_fake_asr)
provider_registry.register_asr("fish", _create_fish_asr)
provider_registry.register_asr("openai", _create_openai_asr)
provider_registry.register_llm("fake", _create_fake_llm)
provider_registry.register_llm("openai", _create_openai_llm)
provider_registry.register_llm("deepseek", _create_deepseek_llm)
provider_registry.register_llm("kimi", _create_kimi_llm)
provider_registry.register_llm("claude", _create_claude_llm)
provider_registry.register_llm(
    "openai-compatible",
    _create_openai_compatible_llm,
)
provider_registry.register_tts("fake", _create_fake_tts)
provider_registry.register_tts("fish", _create_fish_tts)
provider_registry.register_tts("minimax", _create_minimax_tts)
provider_registry.register_tts("openai", _create_openai_tts)
