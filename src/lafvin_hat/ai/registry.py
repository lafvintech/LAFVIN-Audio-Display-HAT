from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias

from .providers import ASRProvider, LLMProvider, TTSProvider


ASRFactory: TypeAlias = Callable[..., ASRProvider]
LLMFactory: TypeAlias = Callable[..., LLMProvider]
TTSFactory: TypeAlias = Callable[..., TTSProvider]


class AIProviderRegistry:
    """Internal registry for independently selectable AI capabilities."""

    def __init__(self) -> None:
        self._asr: dict[str, ASRFactory] = {}
        self._llm: dict[str, LLMFactory] = {}
        self._tts: dict[str, TTSFactory] = {}

    def register_asr(
        self,
        name: str,
        factory: ASRFactory,
        *,
        replace: bool = False,
    ) -> None:
        self._register(self._asr, name, factory, replace=replace)

    def register_llm(
        self,
        name: str,
        factory: LLMFactory,
        *,
        replace: bool = False,
    ) -> None:
        self._register(self._llm, name, factory, replace=replace)

    def register_tts(
        self,
        name: str,
        factory: TTSFactory,
        *,
        replace: bool = False,
    ) -> None:
        self._register(self._tts, name, factory, replace=replace)

    def create_asr(self, name: str, *args: Any, **kwargs: Any) -> ASRProvider:
        return self._create("ASR", self._asr, name, *args, **kwargs)

    def create_llm(self, name: str, *args: Any, **kwargs: Any) -> LLMProvider:
        return self._create("LLM", self._llm, name, *args, **kwargs)

    def create_tts(self, name: str, *args: Any, **kwargs: Any) -> TTSProvider:
        return self._create("TTS", self._tts, name, *args, **kwargs)

    def available_asr(self) -> tuple[str, ...]:
        return tuple(sorted(self._asr))

    def available_llm(self) -> tuple[str, ...]:
        return tuple(sorted(self._llm))

    def available_tts(self) -> tuple[str, ...]:
        return tuple(sorted(self._tts))

    @staticmethod
    def _register(
        factories: dict[str, Callable[..., object]],
        name: str,
        factory: Callable[..., object],
        *,
        replace: bool,
    ) -> None:
        normalized = _normalize_name(name)
        if normalized in factories and not replace:
            raise ValueError(f"AI provider is already registered: {normalized}")
        factories[normalized] = factory

    @staticmethod
    def _create(
        capability: str,
        factories: dict[str, Callable[..., Any]],
        name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        normalized = _normalize_name(name)
        try:
            factory = factories[normalized]
        except KeyError as exc:
            available = ", ".join(sorted(factories)) or "none"
            raise ValueError(
                f"Unsupported {capability} provider: {name}. "
                f"Available providers: {available}"
            ) from exc
        return factory(*args, **kwargs)


def _normalize_name(name: str) -> str:
    normalized = name.strip().lower()
    if not normalized:
        raise ValueError("AI provider name cannot be empty")
    return normalized
