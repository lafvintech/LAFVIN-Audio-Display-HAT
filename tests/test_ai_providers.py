import asyncio
from pathlib import Path

import pytest

from lafvin_hat.ai import (
    AIConfigurationError,
    AnthropicLLM,
    FakeASRProvider,
    FakeLLMProvider,
    FakeTTSProvider,
    FishAudioASR,
    FishAudioTTS,
    Message,
    MiniMaxTTS,
    NormalizedASRProvider,
    NormalizedTTSProvider,
    OpenAICompatibleASR,
    OpenAICompatibleLLM,
    OpenAICompatibleTTS,
    providers_from_environment,
)


def test_fake_capabilities_are_independent(tmp_path: Path) -> None:
    async def scenario() -> None:
        recording = tmp_path / "recording.wav"
        recording.write_bytes(b"RIFFfake")
        asr = FakeASRProvider(transcript="hello")
        llm = FakeLLMProvider(response="Hello back.", chunk_size=3)
        tts = FakeTTSProvider()

        assert await asr.transcribe(recording) == "hello"
        chunks = [
            chunk.text
            async for chunk in llm.stream_chat([Message("user", "hello")])
        ]
        assert "".join(chunks) == "Hello back."
        result = await tts.synthesize(
            "Hello back.",
            output_path=tmp_path / "reply.wav",
        )
        assert result.path.is_file()
        assert tts.synthesized_texts == ["Hello back."]

    asyncio.run(scenario())


def test_environment_factory_supports_mixed_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "openai")
    monkeypatch.setenv(
        "LAFVIN_OPENAI_COMPATIBLE_LLM_BASE_URL",
        "https://llm.invalid/v1",
    )
    monkeypatch.setenv(
        "LAFVIN_OPENAI_COMPATIBLE_LLM_API_KEY",
        "llm-secret",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("LAFVIN_OPENAI_COMPATIBLE_LLM_MODEL", "chat-model")
    monkeypatch.setenv("OPENAI_TTS_VOICE", "nova")
    monkeypatch.setenv("LAFVIN_TTS_RETRIES", "4")

    providers = providers_from_environment()

    assert isinstance(providers.asr, FakeASRProvider)
    assert isinstance(providers.llm, OpenAICompatibleLLM)
    assert isinstance(providers.tts, NormalizedTTSProvider)
    assert isinstance(providers.tts.provider, OpenAICompatibleTTS)
    tts = providers.tts.provider
    assert providers.llm.config.normalized_base_url == "https://llm.invalid/v1"
    assert providers.llm.model == "chat-model"
    assert tts.config.normalized_base_url == "https://api.openai.com/v1"
    assert tts.voice == "nova"
    assert tts.config.retries == 4


def test_named_speech_providers_ignore_removed_custom_endpoint_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "openai")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("LAFVIN_ASR_BASE_URL", "https://asr.invalid/v1")
    monkeypatch.setenv("LAFVIN_ASR_API_KEY", "ignored-asr-secret")
    monkeypatch.setenv("LAFVIN_TTS_BASE_URL", "https://tts.invalid/v1")
    monkeypatch.setenv("LAFVIN_TTS_API_KEY", "ignored-tts-secret")

    providers = providers_from_environment()

    assert isinstance(providers.asr, NormalizedASRProvider)
    assert isinstance(providers.asr.provider, OpenAICompatibleASR)
    assert isinstance(providers.tts, NormalizedTTSProvider)
    assert isinstance(providers.tts.provider, OpenAICompatibleTTS)
    assert providers.asr.provider.config.normalized_base_url == (
        "https://api.openai.com/v1"
    )
    assert providers.tts.provider.config.normalized_base_url == (
        "https://api.openai.com/v1"
    )
    assert providers.asr.provider.config.headers() == {
        "Authorization": "Bearer secret"
    }


def test_openai_supports_all_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "openai")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")

    providers = providers_from_environment(require_explicit=True)

    assert isinstance(providers.asr, NormalizedASRProvider)
    assert isinstance(providers.asr.provider, OpenAICompatibleASR)
    assert isinstance(providers.llm, OpenAICompatibleLLM)
    assert isinstance(providers.tts, NormalizedTTSProvider)
    assert isinstance(providers.tts.provider, OpenAICompatibleTTS)
    assert providers.llm.config.normalized_base_url == (
        "https://api.openai.com/v1"
    )


@pytest.mark.parametrize(
    ("provider_name", "key_name", "model_name", "base_url"),
    [
        (
            "deepseek",
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_LLM_MODEL",
            "https://api.deepseek.com",
        ),
        (
            "kimi",
            "MOONSHOT_API_KEY",
            "MOONSHOT_LLM_MODEL",
            "https://api.moonshot.cn/v1",
        ),
    ],
)
def test_openai_compatible_llm_presets_set_service_defaults(
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
    key_name: str,
    model_name: str,
    base_url: str,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", provider_name)
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
    monkeypatch.setenv(key_name, "provider-secret")
    monkeypatch.setenv(model_name, "provider-model")

    providers = providers_from_environment(require_explicit=True)

    assert isinstance(providers.llm, OpenAICompatibleLLM)
    assert providers.llm.config.normalized_base_url == base_url
    assert providers.llm.config.headers() == {
        "Authorization": "Bearer provider-secret"
    }
    assert providers.llm.model == "provider-model"


def test_claude_uses_native_anthropic_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "claude")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("ANTHROPIC_LLM_MODEL", "claude-model")

    providers = providers_from_environment(require_explicit=True)

    assert isinstance(providers.llm, AnthropicLLM)
    assert providers.llm.config.normalized_base_url == (
        "https://api.anthropic.com/v1"
    )
    assert providers.llm.config.headers()["x-api-key"] == "anthropic-secret"
    assert providers.llm.model == "claude-model"


@pytest.mark.parametrize(
    (
        "provider_name",
        "key_name",
        "expected_type",
        "base_url",
        "model",
    ),
    [
        (
            "minimax",
            "MINIMAX_API_KEY",
            MiniMaxTTS,
            "https://api.minimaxi.com/v1",
            "speech-2.8-turbo",
        ),
        (
            "fish",
            "FISH_AUDIO_API_KEY",
            FishAudioTTS,
            "https://api.fish.audio/v1",
            "s2.1-pro",
        ),
    ],
)
def test_named_tts_providers_use_service_defaults(
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
    key_name: str,
    expected_type: type[MiniMaxTTS] | type[FishAudioTTS],
    base_url: str,
    model: str,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", provider_name)
    monkeypatch.setenv(key_name, "provider-secret")
    monkeypatch.delenv("MINIMAX_TTS_MODEL", raising=False)
    monkeypatch.delenv("MINIMAX_TTS_VOICE", raising=False)
    monkeypatch.delenv("FISH_AUDIO_TTS_MODEL", raising=False)
    monkeypatch.delenv("FISH_AUDIO_TTS_VOICE", raising=False)

    providers = providers_from_environment(require_explicit=True)

    assert isinstance(providers.tts, NormalizedTTSProvider)
    assert isinstance(providers.tts.provider, expected_type)
    tts = providers.tts.provider
    assert tts.config.normalized_base_url == base_url
    assert tts.config.authorization_headers() == {
        "Authorization": "Bearer provider-secret"
    }
    assert tts.model == model


def test_tts_provider_settings_can_coexist_without_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "fake")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-secret")
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "fish-secret")
    monkeypatch.setenv("OPENAI_TTS_MODEL", "openai-model")
    monkeypatch.setenv("OPENAI_TTS_VOICE", "openai-voice")
    monkeypatch.setenv("MINIMAX_TTS_MODEL", "minimax-model")
    monkeypatch.setenv("MINIMAX_TTS_VOICE", "minimax-voice")
    monkeypatch.setenv("FISH_AUDIO_TTS_MODEL", "fish-model")
    monkeypatch.setenv("FISH_AUDIO_TTS_VOICE", "fish-voice")

    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fish")
    fish_set = providers_from_environment(require_explicit=True)
    assert isinstance(fish_set.tts, NormalizedTTSProvider)
    assert isinstance(fish_set.tts.provider, FishAudioTTS)
    assert fish_set.tts.provider.model == "fish-model"
    assert fish_set.tts.provider.voice == "fish-voice"

    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "minimax")
    minimax_set = providers_from_environment(require_explicit=True)
    assert isinstance(minimax_set.tts, NormalizedTTSProvider)
    assert isinstance(minimax_set.tts.provider, MiniMaxTTS)
    assert minimax_set.tts.provider.model == "minimax-model"
    assert minimax_set.tts.provider.voice == "minimax-voice"

    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "openai")
    openai_set = providers_from_environment(require_explicit=True)
    assert isinstance(openai_set.tts, NormalizedTTSProvider)
    assert isinstance(openai_set.tts.provider, OpenAICompatibleTTS)
    assert openai_set.tts.provider.model == "openai-model"
    assert openai_set.tts.provider.voice == "openai-voice"


def test_asr_provider_settings_can_coexist_without_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "fish-secret")
    monkeypatch.setenv("OPENAI_ASR_MODEL", "openai-asr-model")
    monkeypatch.setenv("FISH_AUDIO_ASR_MODEL", "transcribe-1")
    monkeypatch.setenv("FISH_AUDIO_ASR_LANGUAGE", "zh")

    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fish")
    fish_set = providers_from_environment(require_explicit=True)
    assert isinstance(fish_set.asr, NormalizedASRProvider)
    assert isinstance(fish_set.asr.provider, FishAudioASR)
    assert fish_set.asr.provider.model == "transcribe-1"
    assert fish_set.asr.provider.language == "zh"

    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "openai")
    openai_set = providers_from_environment(require_explicit=True)
    assert isinstance(openai_set.asr, NormalizedASRProvider)
    assert isinstance(openai_set.asr.provider, OpenAICompatibleASR)
    assert openai_set.asr.provider.model == "openai-asr-model"


def test_llm_provider_settings_can_coexist_without_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
    monkeypatch.setenv("DEEPSEEK_LLM_MODEL", "deepseek-model")
    monkeypatch.setenv("MOONSHOT_LLM_MODEL", "kimi-model")

    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "deepseek")
    deepseek_set = providers_from_environment(require_explicit=True)
    assert isinstance(deepseek_set.llm, OpenAICompatibleLLM)
    assert deepseek_set.llm.provider_name == "deepseek"
    assert deepseek_set.llm.model == "deepseek-model"

    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "kimi")
    kimi_set = providers_from_environment(require_explicit=True)
    assert isinstance(kimi_set.llm, OpenAICompatibleLLM)
    assert kimi_set.llm.provider_name == "kimi"
    assert kimi_set.llm.model == "kimi-model"


def test_removed_shared_model_and_voice_variables_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fish")
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "fish-secret")
    monkeypatch.setenv("LAFVIN_TTS_MODEL", "removed-model")
    monkeypatch.setenv("LAFVIN_TTS_VOICE", "removed-voice")

    providers = providers_from_environment(require_explicit=True)

    assert isinstance(providers.tts, NormalizedTTSProvider)
    assert isinstance(providers.tts.provider, FishAudioTTS)
    assert providers.tts.provider.model == "s2.1-pro"
    assert providers.tts.provider.voice is None


def test_fish_audio_asr_uses_service_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fish")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "provider-secret")
    monkeypatch.setenv("FISH_AUDIO_ASR_MODEL", "transcribe-1")
    monkeypatch.setenv("FISH_AUDIO_ASR_LANGUAGE", "zh")

    providers = providers_from_environment(require_explicit=True)

    assert isinstance(providers.asr, NormalizedASRProvider)
    assert isinstance(providers.asr.provider, FishAudioASR)
    asr = providers.asr.provider
    assert asr.config.normalized_base_url == (
        "https://api.fish.audio/v1"
    )
    assert asr.config.authorization_headers() == {
        "Authorization": "Bearer provider-secret"
    }
    assert asr.model == "transcribe-1"
    assert asr.language == "zh"


def test_explicit_fish_asr_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fish")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
    monkeypatch.setenv("FISH_AUDIO_ASR_MODEL", "transcribe-1")
    monkeypatch.delenv("FISH_AUDIO_API_KEY", raising=False)

    with pytest.raises(AIConfigurationError, match="FISH_AUDIO_API_KEY"):
        providers_from_environment(require_explicit=True)


@pytest.mark.parametrize(
    ("provider_name", "key_name"),
    [
        ("minimax", "MINIMAX_API_KEY"),
        ("fish", "FISH_AUDIO_API_KEY"),
    ],
)
def test_explicit_named_tts_provider_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
    key_name: str,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", provider_name)
    monkeypatch.delenv(key_name, raising=False)

    with pytest.raises(AIConfigurationError, match=key_name):
        providers_from_environment(require_explicit=True)


def test_named_llm_provider_requires_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "provider-secret")
    monkeypatch.delenv("DEEPSEEK_LLM_MODEL", raising=False)

    with pytest.raises(AIConfigurationError, match="DEEPSEEK_LLM_MODEL"):
        providers_from_environment(require_explicit=True)


def test_unknown_provider_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="Unsupported ASR provider"):
        providers_from_environment()


def test_explicit_configuration_rejects_missing_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "LAFVIN_ASR_PROVIDER",
        "LAFVIN_LLM_PROVIDER",
        "LAFVIN_TTS_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(AIConfigurationError, match="not fully configured"):
        providers_from_environment(require_explicit=True)


def test_explicit_configuration_requires_every_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LAFVIN_ASR_PROVIDER", raising=False)
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "fake")
    monkeypatch.delenv("LAFVIN_TTS_PROVIDER", raising=False)

    with pytest.raises(AIConfigurationError) as error:
        providers_from_environment(require_explicit=True)

    assert "LAFVIN_ASR_PROVIDER" in str(error.value)
    assert "LAFVIN_TTS_PROVIDER" in str(error.value)


def test_explicit_independent_fake_configuration_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")

    providers = providers_from_environment(require_explicit=True)

    assert isinstance(providers.asr, FakeASRProvider)
    assert isinstance(providers.llm, FakeLLMProvider)
    assert isinstance(providers.tts, FakeTTSProvider)


def test_explicit_custom_llm_configuration_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
    monkeypatch.setenv(
        "LAFVIN_OPENAI_COMPATIBLE_LLM_BASE_URL",
        "https://llm.invalid/v1",
    )
    monkeypatch.delenv(
        "LAFVIN_OPENAI_COMPATIBLE_LLM_API_KEY",
        raising=False,
    )

    with pytest.raises(
        AIConfigurationError,
        match="LAFVIN_OPENAI_COMPATIBLE_LLM_API_KEY",
    ):
        providers_from_environment(require_explicit=True)


def test_explicit_custom_llm_name_normalization_still_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", " OpenAI-Compatible ")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
    monkeypatch.setenv(
        "LAFVIN_OPENAI_COMPATIBLE_LLM_BASE_URL",
        "https://llm.invalid/v1",
    )
    monkeypatch.delenv(
        "LAFVIN_OPENAI_COMPATIBLE_LLM_API_KEY",
        raising=False,
    )

    with pytest.raises(
        AIConfigurationError,
        match="LAFVIN_OPENAI_COMPATIBLE_LLM_API_KEY",
    ):
        providers_from_environment(require_explicit=True)


def test_custom_llm_requires_an_explicit_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_OPENAI_COMPATIBLE_LLM_API_KEY", "secret")
    monkeypatch.delenv(
        "LAFVIN_OPENAI_COMPATIBLE_LLM_BASE_URL",
        raising=False,
    )

    with pytest.raises(
        AIConfigurationError,
        match="LAFVIN_OPENAI_COMPATIBLE_LLM_BASE_URL",
    ):
        providers_from_environment(require_explicit=True)


def test_custom_llm_requires_an_explicit_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_OPENAI_COMPATIBLE_LLM_API_KEY", "secret")
    monkeypatch.setenv(
        "LAFVIN_OPENAI_COMPATIBLE_LLM_BASE_URL",
        "https://llm.invalid/v1",
    )
    monkeypatch.delenv(
        "LAFVIN_OPENAI_COMPATIBLE_LLM_MODEL",
        raising=False,
    )

    with pytest.raises(
        AIConfigurationError,
        match="LAFVIN_OPENAI_COMPATIBLE_LLM_MODEL",
    ):
        providers_from_environment(require_explicit=True)


def test_removed_common_provider_variable_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_AI_PROVIDER", "openai")
    monkeypatch.delenv("LAFVIN_ASR_PROVIDER", raising=False)
    monkeypatch.delenv("LAFVIN_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LAFVIN_TTS_PROVIDER", raising=False)

    providers = providers_from_environment()

    assert isinstance(providers.asr, FakeASRProvider)
    assert isinstance(providers.llm, FakeLLMProvider)
    assert isinstance(providers.tts, FakeTTSProvider)
