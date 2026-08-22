import asyncio
import wave
from pathlib import Path

import numpy as np
import pytest

from lafvin_hat.ai import (
    AudioNormalizationError,
    AudioResult,
    NormalizedASRProvider,
    NormalizedTTSProvider,
    normalize_asr_input_wav,
    normalize_tts_output_wav,
)


def test_asr_input_is_pcm_s16_le_16khz_mono(tmp_path: Path) -> None:
    source = tmp_path / "capture.wav"
    destination = tmp_path / "normalized.wav"
    samples = np.array(
        [
            [2147483647, 2147483647],
            [1073741824, -1073741824],
            [-2147483648, -2147483648],
        ],
        dtype="<i4",
    )
    _write_wav(source, samples, sample_rate=16000, sample_width=4)

    normalize_asr_input_wav(source, destination)

    parameters, normalized = _read_wav(destination)
    assert parameters == (1, 2, 16000, 3)
    assert normalized.tolist() == [32767, 0, -32768]


def test_tts_output_is_resampled_to_pcm_s16_le_24khz_mono(
    tmp_path: Path,
) -> None:
    source = tmp_path / "provider.wav"
    destination = tmp_path / "playback.wav"
    positions = np.arange(320, dtype=np.float64)
    samples = np.rint(12000 * np.sin(2 * np.pi * positions / 32)).astype(
        "<i2"
    )
    _write_wav(source, samples, sample_rate=32000, sample_width=2)

    normalize_tts_output_wav(source, destination)

    parameters, normalized = _read_wav(destination)
    assert parameters == (1, 2, 24000, 240)
    assert np.max(np.abs(normalized)) > 10000


def test_unsigned_8bit_pcm_is_converted_to_signed_16bit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "unsigned-8bit.wav"
    destination = tmp_path / "normalized.wav"
    samples = np.array([0, 128, 255], dtype=np.uint8)
    _write_wav(source, samples, sample_rate=16000, sample_width=1)

    normalize_asr_input_wav(source, destination)

    _parameters, normalized = _read_wav(destination)
    assert normalized.tolist() == [-32768, 0, 32512]


def test_signed_24bit_pcm_is_converted_to_signed_16bit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "signed-24bit.wav"
    destination = tmp_path / "normalized.wav"
    values = [-8388608, 0, 8388352]
    frames = b"".join(
        (value & 0xFFFFFF).to_bytes(3, "little") for value in values
    )
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(3)
        output.setframerate(16000)
        output.writeframes(frames)

    normalize_asr_input_wav(source, destination)

    _parameters, normalized = _read_wav(destination)
    assert normalized.tolist() == [-32768, 0, 32767]


def test_invalid_wav_is_rejected_without_creating_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "invalid.wav"
    destination = tmp_path / "normalized.wav"
    source.write_bytes(b"not a wav")

    with pytest.raises(AudioNormalizationError, match="Cannot read PCM WAV"):
        normalize_asr_input_wav(source, destination)

    assert not destination.exists()


def test_overstated_wav_frame_count_uses_complete_physical_frames(
    tmp_path: Path,
) -> None:
    source = tmp_path / "fish-response.wav"
    destination = tmp_path / "normalized.wav"
    samples = np.arange(8, dtype="<i2") * 1000
    _write_wav(source, samples, sample_rate=24000, sample_width=2)
    _set_wav_data_size(source, samples.nbytes + 4)

    normalize_tts_output_wav(source, destination)

    parameters, normalized = _read_wav(destination)
    assert parameters == (1, 2, 24000, 8)
    assert normalized.tolist() == samples.tolist()


def test_partial_pcm_frame_is_still_rejected(tmp_path: Path) -> None:
    source = tmp_path / "truncated.wav"
    destination = tmp_path / "normalized.wav"
    samples = np.arange(8, dtype="<i2") * 1000
    _write_wav(source, samples, sample_rate=24000, sample_width=2)
    source.write_bytes(source.read_bytes()[:-1])

    with pytest.raises(AudioNormalizationError, match="incomplete PCM frame"):
        normalize_tts_output_wav(source, destination)

    assert not destination.exists()


def test_asr_wrapper_normalizes_temporary_recording(tmp_path: Path) -> None:
    class InspectingASR:
        def __init__(self) -> None:
            self.path: Path | None = None
            self.parameters: tuple[int, int, int, int] | None = None

        async def transcribe(self, audio_path: str | Path) -> str:
            self.path = Path(audio_path)
            self.parameters, _samples = _read_wav(self.path)
            return "normalized transcript"

    source = tmp_path / "capture.wav"
    samples = np.array([[1000000000, -500000000]] * 160, dtype="<i4")
    _write_wav(source, samples, sample_rate=16000, sample_width=4)
    inner = InspectingASR()
    provider = NormalizedASRProvider(inner)

    transcript = asyncio.run(provider.transcribe(source))

    assert transcript == "normalized transcript"
    assert inner.parameters == (1, 2, 16000, 160)
    assert inner.path is not None
    assert not inner.path.exists()


def test_tts_wrapper_normalizes_provider_output(tmp_path: Path) -> None:
    class StereoTTS:
        def __init__(self) -> None:
            self.path: Path | None = None

        async def synthesize(
            self,
            text: str,
            *,
            output_path: str | Path | None = None,
        ) -> AudioResult:
            del text
            assert output_path is not None
            self.path = Path(output_path)
            samples = np.array([[12000, -4000]] * 320, dtype="<i2")
            _write_wav(
                self.path,
                samples,
                sample_rate=32000,
                sample_width=2,
            )
            return AudioResult(path=self.path)

    inner = StereoTTS()
    provider = NormalizedTTSProvider(inner)
    destination = tmp_path / "speech.wav"

    result = asyncio.run(
        provider.synthesize("hello", output_path=destination)
    )

    parameters, samples = _read_wav(destination)
    assert result.path == destination
    assert result.format == "wav"
    assert result.duration_ms == 10
    assert parameters == (1, 2, 24000, 240)
    assert np.all(samples == 4000)
    assert inner.path is not None
    assert not inner.path.exists()


def test_normalization_wrappers_forward_close() -> None:
    class ClosingProvider:
        def __init__(self) -> None:
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    asr_inner = ClosingProvider()
    tts_inner = ClosingProvider()

    async def scenario() -> None:
        await NormalizedASRProvider(asr_inner).aclose()  # type: ignore[arg-type]
        await NormalizedTTSProvider(tts_inner).aclose()  # type: ignore[arg-type]

    asyncio.run(scenario())

    assert asr_inner.close_calls == 1
    assert tts_inner.close_calls == 1


def _write_wav(
    path: Path,
    samples: np.ndarray,
    *,
    sample_rate: int,
    sample_width: int,
) -> None:
    channels = 1 if samples.ndim == 1 else samples.shape[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(sample_width)
        output.setframerate(sample_rate)
        output.writeframes(samples.tobytes())


def _read_wav(path: Path) -> tuple[tuple[int, int, int, int], np.ndarray]:
    with wave.open(str(path), "rb") as source:
        parameters = (
            source.getnchannels(),
            source.getsampwidth(),
            source.getframerate(),
            source.getnframes(),
        )
        samples = np.frombuffer(source.readframes(source.getnframes()), "<i2")
    return parameters, samples


def _set_wav_data_size(path: Path, size: int) -> None:
    content = bytearray(path.read_bytes())
    size_offset = content.index(b"data") + 4
    content[size_offset:size_offset + 4] = size.to_bytes(4, "little")
    path.write_bytes(content)
