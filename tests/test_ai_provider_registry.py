import pytest

from lafvin_hat.ai import (
    AIProviderRegistry,
    FakeASRProvider,
    FakeLLMProvider,
    FakeTTSProvider,
    provider_registry,
)


def test_builtin_provider_registry_preserves_existing_providers() -> None:
    assert provider_registry.available_asr() == (
        "fake",
        "fish",
        "openai",
    )
    assert provider_registry.available_llm() == (
        "claude",
        "deepseek",
        "fake",
        "kimi",
        "openai",
        "openai-compatible",
    )
    assert provider_registry.available_tts() == (
        "fake",
        "fish",
        "minimax",
        "openai",
    )


@pytest.mark.parametrize("capability", ["asr", "tts"])
def test_custom_openai_compatible_is_llm_only(capability: str) -> None:
    creator = getattr(provider_registry, f"create_{capability}")

    with pytest.raises(ValueError, match=f"Unsupported {capability.upper()} provider"):
        creator("openai-compatible")


def test_registry_keeps_capability_factories_independent() -> None:
    registry = AIProviderRegistry()
    registry.register_asr(
        "example",
        lambda: FakeASRProvider(transcript="hello"),
    )
    registry.register_llm(
        "example",
        lambda: FakeLLMProvider(response="reply"),
    )
    registry.register_tts("example", FakeTTSProvider)

    assert isinstance(registry.create_asr("EXAMPLE"), FakeASRProvider)
    assert isinstance(registry.create_llm(" example "), FakeLLMProvider)
    assert isinstance(registry.create_tts("example"), FakeTTSProvider)


def test_registry_rejects_duplicate_names_unless_replace_is_explicit() -> None:
    registry = AIProviderRegistry()
    registry.register_tts("example", FakeTTSProvider)

    with pytest.raises(ValueError, match="already registered"):
        registry.register_tts("EXAMPLE", FakeTTSProvider)

    registry.register_tts("example", FakeTTSProvider, replace=True)


def test_registry_error_lists_available_provider_names() -> None:
    registry = AIProviderRegistry()
    registry.register_asr(
        "example",
        lambda: FakeASRProvider(transcript="hello"),
    )

    with pytest.raises(
        ValueError,
        match=r"Unsupported ASR provider: missing.*example",
    ):
        registry.create_asr("missing")
