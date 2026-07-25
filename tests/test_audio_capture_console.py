from __future__ import annotations

import array
import importlib.util
import sys
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "lafvin_audio_capture_console",
    ROOT / "tools" / "audio_capture_console.py",
)
assert SPEC is not None and SPEC.loader is not None
audio_capture_console = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audio_capture_console
SPEC.loader.exec_module(audio_capture_console)


CONTROL_OUTPUT = """
numid=1,iface=MIXER,name='Capture Volume'
; type=INTEGER,access=rw---R--,values=2,min=0,max=63,step=0
: values=39,39
| dBscale-min=-17.25dB,step=0.75dB,mute=0
"""


def test_parse_control_state_reads_values_limits_and_db_scale() -> None:
    state = audio_capture_console.parse_control_state(
        CONTROL_OUTPUT,
        name="Capture Volume",
    )

    assert state.name == "Capture Volume"
    assert state.values == (39, 39)
    assert state.minimum == 0
    assert state.maximum == 63
    assert state.db_scale_min == "-17.25dB"
    assert state.db_scale_step == "0.75dB"


def test_parse_tuning_command_accepts_supported_integer_commands() -> None:
    assert audio_capture_console.parse_tuning_command("c 39") == ("capture", 39)
    assert audio_capture_console.parse_tuning_command("boost 2") == ("boost", 2)
    assert audio_capture_console.parse_tuning_command("a 195") == ("adc", 195)
    assert audio_capture_console.parse_tuning_command("capture -1") is None
    assert audio_capture_console.parse_tuning_command("other 2") is None
    assert audio_capture_console.parse_tuning_command("c") is None


def test_measure_capture_pair_uses_independent_silence_and_speech_files(
    tmp_path: Path,
) -> None:
    silence = tmp_path / "silence.wav"
    speech = tmp_path / "speech.wav"
    _write_stereo_wav(silence, [0, 0, 0, 0], sample_rate=2)
    _write_stereo_wav(
        speech,
        [1_073_741_824, 1_073_741_824, 1_073_741_824, 1_073_741_824],
        sample_rate=2,
    )

    metrics = audio_capture_console.measure_capture_pair(
        silence,
        speech,
        settle_ms=0,
    )

    left = metrics.channel_metrics[0]
    assert left.silence.rms_dbfs is None
    assert left.speech.rms_dbfs is not None
    assert left.speech.clipped_percent == 0


def _write_stereo_wav(path: Path, samples: list[int], *, sample_rate: int) -> None:
    interleaved = array.array(
        "i",
        (value for sample in samples for value in (sample, sample)),
    )
    if sys.byteorder != "little":
        interleaved.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(4)
        output.setframerate(sample_rate)
        output.writeframes(interleaved.tobytes())


def test_measure_signal_returns_negative_infinity_for_silence() -> None:
    values = array.array("i", [0, 0, 0])

    metrics = audio_capture_console.measure_signal(values)

    assert metrics.rms == 0
    assert metrics.rms_dbfs is None
    assert audio_capture_console.format_dbfs(metrics.rms_dbfs) == "-inf dBFS"
