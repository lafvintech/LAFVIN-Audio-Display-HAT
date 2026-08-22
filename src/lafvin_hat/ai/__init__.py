"""Provider-independent AI Runtime interfaces and helpers."""

from .anthropic import AnthropicConfig, AnthropicLLM
from .audio_normalization import (
    ASR_INPUT_FORMAT,
    TTS_OUTPUT_FORMAT,
    AudioNormalizationError,
    NormalizedASRProvider,
    NormalizedTTSProvider,
    PCMFormat,
    normalize_asr_input_wav,
    normalize_pcm_wav,
    normalize_tts_output_wav,
    pcm_wav_duration_ms,
)
from .config import (
    AIConfigurationError,
    AIProviderSet,
    provider_registry,
    providers_from_environment,
)
from .cloud_tts import CloudTTSConfig, FishAudioTTS, MiniMaxTTS
from .diagnostics import configure_ai_logging
from .fake import (
    FakeAIProvider,
    FakeASRProvider,
    FakeLLMProvider,
    FakeTTSProvider,
)
from .fish_audio import FishAudioASR, FishAudioASRConfig
from .models import AudioResult, LLMChunk, Message, SpeechSegment
from .openai_compatible import (
    OpenAICompatibleASR,
    OpenAICompatibleConfig,
    OpenAICompatibleLLM,
    OpenAICompatibleProvider,
    OpenAICompatibleTTS,
)
from .pipeline import (
    PipelineStageError,
    SentenceSplitter,
    StreamingSpeechPipeline,
    TTSQueue,
    prepare_text_for_speech,
)
from .providers import ASRProvider, LLMProvider, TTSProvider, aclose_provider
from .registry import AIProviderRegistry

__all__ = [
    "ASRProvider",
    "AIConfigurationError",
    "AIProviderRegistry",
    "AIProviderSet",
    "AnthropicConfig",
    "AnthropicLLM",
    "ASR_INPUT_FORMAT",
    "AudioNormalizationError",
    "AudioResult",
    "CloudTTSConfig",
    "FakeAIProvider",
    "FakeASRProvider",
    "FakeLLMProvider",
    "FakeTTSProvider",
    "FishAudioTTS",
    "FishAudioASR",
    "FishAudioASRConfig",
    "LLMChunk",
    "LLMProvider",
    "Message",
    "MiniMaxTTS",
    "NormalizedASRProvider",
    "NormalizedTTSProvider",
    "OpenAICompatibleASR",
    "OpenAICompatibleConfig",
    "OpenAICompatibleLLM",
    "OpenAICompatibleProvider",
    "OpenAICompatibleTTS",
    "PipelineStageError",
    "PCMFormat",
    "SentenceSplitter",
    "SpeechSegment",
    "StreamingSpeechPipeline",
    "TTSProvider",
    "TTS_OUTPUT_FORMAT",
    "TTSQueue",
    "configure_ai_logging",
    "aclose_provider",
    "normalize_asr_input_wav",
    "normalize_pcm_wav",
    "normalize_tts_output_wav",
    "pcm_wav_duration_ms",
    "provider_registry",
    "providers_from_environment",
    "prepare_text_for_speech",
]
