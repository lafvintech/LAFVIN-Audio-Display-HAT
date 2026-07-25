import asyncio
from pathlib import Path

import pytest

from lafvin_hat.ai import (
    AIConfigurationError,
    FakeASRProvider,
    FakeLLMProvider,
    FakeTTSProvider,
    Message,
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
    monkeypatch.setenv("LAFVIN_AI_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
    monkeypatch.setenv("LAFVIN_ASR_BASE_URL", "https://asr.invalid/v1")
    monkeypatch.setenv("LAFVIN_LLM_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("LAFVIN_TTS_BASE_URL", "https://tts.invalid/v1")
    monkeypatch.setenv("LAFVIN_LLM_MODEL", "chat-model")
    monkeypatch.setenv("LAFVIN_TTS_VOICE", "nova")
    monkeypatch.setenv("LAFVIN_TTS_RETRIES", "4")

    providers = providers_from_environment()

    assert isinstance(providers.asr, FakeASRProvider)
    assert isinstance(providers.llm, OpenAICompatibleLLM)
    assert isinstance(providers.tts, OpenAICompatibleTTS)
    assert providers.llm.config.normalized_base_url == "https://llm.invalid/v1"
    assert providers.llm.model == "chat-model"
    assert providers.tts.config.normalized_base_url == "https://tts.invalid/v1"
    assert providers.tts.voice == "nova"
    assert providers.tts.config.retries == 4


def test_capability_config_falls_back_to_common_openai_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_AI_PROVIDER", "openai-compatible")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.invalid/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "secret")

    providers = providers_from_environment()

    assert isinstance(providers.asr, OpenAICompatibleASR)
    assert isinstance(providers.llm, OpenAICompatibleLLM)
    assert isinstance(providers.tts, OpenAICompatibleTTS)
    assert providers.asr.config.normalized_base_url == (
        "https://gateway.invalid/v1"
    )
    assert providers.llm.config.headers() == {
        "Authorization": "Bearer secret"
    }


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
        "LAFVIN_AI_PROVIDER",
        "LAFVIN_ASR_PROVIDER",
        "LAFVIN_LLM_PROVIDER",
        "LAFVIN_TTS_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(AIConfigurationError, match="not configured"):
        providers_from_environment(require_explicit=True)


def test_explicit_openai_configuration_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_AI_PROVIDER", "openai-compatible")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(AIConfigurationError, match="OPENAI_API_KEY"):
        providers_from_environment(require_explicit=True)


def test_explicit_fake_configuration_remains_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAFVIN_AI_PROVIDER", "fake")

    providers = providers_from_environment(require_explicit=True)

    assert isinstance(providers.asr, FakeASRProvider)
    assert isinstance(providers.llm, FakeLLMProvider)
    assert isinstance(providers.tts, FakeTTSProvider)
