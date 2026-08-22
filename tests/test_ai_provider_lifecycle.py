import asyncio

import pytest

from lafvin_hat.ai import AIProviderSet


class ClosingProvider:
    def __init__(
        self,
        name: str,
        events: list[str],
        *,
        failure: Exception | None = None,
    ) -> None:
        self.name = name
        self.events = events
        self.failure = failure
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1
        self.events.append(self.name)
        if self.failure is not None:
            raise self.failure


def test_provider_set_closes_unique_providers_once() -> None:
    events: list[str] = []
    shared = ClosingProvider("shared", events)
    tts = ClosingProvider("tts", events)
    providers = AIProviderSet(asr=shared, llm=shared, tts=tts)  # type: ignore[arg-type]

    asyncio.run(providers.aclose())

    assert events == ["shared", "tts"]
    assert shared.close_calls == 1
    assert tts.close_calls == 1


def test_provider_set_attempts_every_close_and_reports_capability() -> None:
    events: list[str] = []
    asr = ClosingProvider("asr", events, failure=OSError("socket close failed"))
    llm = ClosingProvider("llm", events)
    tts = ClosingProvider("tts", events)
    providers = AIProviderSet(asr=asr, llm=llm, tts=tts)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="Failed to close ASR provider"):
        asyncio.run(providers.aclose())

    assert events == ["asr", "llm", "tts"]
