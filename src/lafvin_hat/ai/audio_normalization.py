from __future__ import annotations

import asyncio
import logging
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .models import AudioResult
from .providers import ASRProvider, TTSProvider, aclose_provider


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PCMFormat:
    sample_rate: int
    channels: int = 1
    sample_width: int = 2


ASR_INPUT_FORMAT = PCMFormat(sample_rate=16000)
TTS_OUTPUT_FORMAT = PCMFormat(sample_rate=24000)


class AudioNormalizationError(RuntimeError):
    pass


def normalize_asr_input_wav(
    source_path: str | Path,
    output_path: str | Path,
) -> Path:
    return normalize_pcm_wav(
        source_path,
        output_path,
        target_format=ASR_INPUT_FORMAT,
    )


def normalize_tts_output_wav(
    source_path: str | Path,
    output_path: str | Path,
) -> Path:
    return normalize_pcm_wav(
        source_path,
        output_path,
        target_format=TTS_OUTPUT_FORMAT,
    )


def pcm_wav_duration_ms(path: str | Path) -> int:
    """Return the duration declared by a valid uncompressed PCM WAV header."""

    source_path = Path(path)
    try:
        with wave.open(str(source_path), "rb") as source:
            if source.getcomptype() != "NONE":
                raise AudioNormalizationError(
                    f"WAV audio must contain uncompressed PCM: {source_path}"
                )
            frame_count = source.getnframes()
            sample_rate = source.getframerate()
    except AudioNormalizationError:
        raise
    except (OSError, EOFError, wave.Error) as exc:
        raise AudioNormalizationError(
            f"Cannot read PCM WAV audio: {source_path}"
        ) from exc

    if frame_count <= 0 or sample_rate <= 0:
        raise AudioNormalizationError(
            f"WAV audio has invalid duration parameters: {source_path}"
        )
    return max(1, round(frame_count * 1000 / sample_rate))


def normalize_pcm_wav(
    source_path: str | Path,
    output_path: str | Path,
    *,
    target_format: PCMFormat,
) -> Path:
    """Convert an integer PCM WAV to signed 16-bit mono PCM WAV."""
    _validate_target_format(target_format)
    source = Path(source_path)
    output = Path(output_path)
    samples, source_rate = _read_pcm_wav(source)
    mono = samples.mean(axis=1, dtype=np.float64)
    resampled = _resample(mono, source_rate, target_format.sample_rate)
    pcm = _encode_pcm_s16_le(resampled)
    _write_pcm_wav_atomic(output, pcm, target_format)
    return output


class NormalizedASRProvider:
    """Normalize each recording before forwarding it to an ASR provider."""

    def __init__(self, provider: ASRProvider) -> None:
        self.provider = provider

    async def transcribe(self, audio_path: str | Path) -> str:
        source = Path(audio_path)
        with tempfile.TemporaryDirectory(prefix="lafvin-asr-") as directory:
            normalized = Path(directory) / source.name
            await asyncio.to_thread(
                normalize_asr_input_wav,
                source,
                normalized,
            )
            return await self.provider.transcribe(normalized)

    async def aclose(self) -> None:
        await aclose_provider(self.provider)


class NormalizedTTSProvider:
    """Normalize provider audio before returning it to the playback pipeline."""

    def __init__(self, provider: TTSProvider) -> None:
        self.provider = provider

    async def synthesize(
        self,
        text: str,
        *,
        output_path: str | Path | None = None,
    ) -> AudioResult:
        destination = (
            Path(output_path)
            if output_path is not None
            else Path(tempfile.mkdtemp(prefix="lafvin-tts-")) / "speech.wav"
        )
        with tempfile.TemporaryDirectory(
            prefix="lafvin-tts-source-"
        ) as directory:
            provider_output = Path(directory) / "speech.wav"
            result = await self.provider.synthesize(
                text,
                output_path=provider_output,
            )
            await asyncio.to_thread(
                normalize_tts_output_wav,
                result.path,
                destination,
            )
        duration_ms = await asyncio.to_thread(pcm_wav_duration_ms, destination)
        return AudioResult(
            path=destination,
            format="wav",
            duration_ms=duration_ms,
        )

    async def aclose(self) -> None:
        await aclose_provider(self.provider)


def _validate_target_format(target_format: PCMFormat) -> None:
    if target_format.sample_rate <= 0:
        raise ValueError("target sample rate must be positive")
    if target_format.channels != 1 or target_format.sample_width != 2:
        raise ValueError("target format must be signed 16-bit mono PCM")


def _read_pcm_wav(path: Path) -> tuple[np.ndarray, int]:
    try:
        with wave.open(str(path), "rb") as source:
            if source.getcomptype() != "NONE":
                raise AudioNormalizationError(
                    f"WAV audio must contain uncompressed PCM: {path}"
                )
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            sample_rate = source.getframerate()
            frame_count = source.getnframes()
            frames = source.readframes(frame_count)
    except AudioNormalizationError:
        raise
    except (OSError, EOFError, wave.Error) as exc:
        raise AudioNormalizationError(f"Cannot read PCM WAV audio: {path}") from exc

    if channels <= 0 or sample_rate <= 0:
        raise AudioNormalizationError(f"WAV audio has invalid parameters: {path}")
    bytes_per_frame = channels * sample_width
    if bytes_per_frame <= 0 or len(frames) % bytes_per_frame:
        raise AudioNormalizationError(
            f"WAV audio ends with an incomplete PCM frame: {path}"
        )
    actual_frame_count = len(frames) // bytes_per_frame
    if actual_frame_count <= 0:
        raise AudioNormalizationError(f"WAV audio contains no samples: {path}")
    if actual_frame_count != frame_count:
        logger.warning(
            "stage=audio_normalization event=wav_frame_count_mismatch "
            "path=%s declared_frames=%s actual_frames=%s",
            path,
            frame_count,
            actual_frame_count,
        )
    decoded = _decode_integer_pcm(frames, sample_width)
    expected_samples = actual_frame_count * channels
    if decoded.size != expected_samples:
        raise AudioNormalizationError(
            f"WAV audio contains incomplete PCM samples: {path}"
        )
    return decoded.reshape(actual_frame_count, channels), sample_rate


def _decode_integer_pcm(frames: bytes, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        values = np.frombuffer(frames, dtype=np.uint8).astype(np.float64)
        return (values - 128.0) / 128.0
    if sample_width == 2:
        values = np.frombuffer(frames, dtype="<i2").astype(np.float64)
        return values / 32768.0
    if sample_width == 3:
        raw = np.frombuffer(frames, dtype=np.uint8)
        if raw.size % 3:
            raise AudioNormalizationError("24-bit PCM data is incomplete")
        triples = raw.reshape(-1, 3).astype(np.int32)
        values = triples[:, 0] | (triples[:, 1] << 8) | (triples[:, 2] << 16)
        values = (values ^ 0x800000) - 0x800000
        return values.astype(np.float64) / 8388608.0
    if sample_width == 4:
        values = np.frombuffer(frames, dtype="<i4").astype(np.float64)
        return values / 2147483648.0
    raise AudioNormalizationError(
        f"Unsupported integer PCM sample width: {sample_width} bytes"
    )


def _resample(
    samples: np.ndarray,
    source_rate: int,
    target_rate: int,
) -> np.ndarray:
    if source_rate == target_rate:
        return samples
    target_count = max(1, round(samples.size * target_rate / source_rate))
    if samples.size == 1:
        return np.full(target_count, samples[0], dtype=np.float64)
    source_positions = (
        np.arange(target_count, dtype=np.float64) * source_rate / target_rate
    )
    np.minimum(source_positions, samples.size - 1, out=source_positions)
    return np.interp(
        source_positions,
        np.arange(samples.size, dtype=np.float64),
        samples,
    )


def _encode_pcm_s16_le(samples: np.ndarray) -> bytes:
    maximum = 32767.0 / 32768.0
    clipped = np.clip(samples, -1.0, maximum)
    return np.rint(clipped * 32768.0).astype("<i2").tobytes()


def _write_pcm_wav_atomic(
    output_path: Path,
    frames: bytes,
    target_format: PCMFormat,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
        delete=False,
    )
    temporary_path = Path(temporary_file.name)
    temporary_file.close()
    try:
        with wave.open(str(temporary_path), "wb") as output:
            output.setnchannels(target_format.channels)
            output.setsampwidth(target_format.sample_width)
            output.setframerate(target_format.sample_rate)
            output.writeframes(frames)
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
