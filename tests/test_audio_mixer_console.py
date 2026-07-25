from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from lafvin_hat.runtime.config import RuntimeEndpoint


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "lafvin_audio_mixer_console",
    ROOT / "tools" / "audio_mixer_console.py",
)
assert SPEC is not None and SPEC.loader is not None
audio_mixer_console = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audio_mixer_console
SPEC.loader.exec_module(audio_mixer_console)


MIXER_OUTPUT = """
Simple mixer control 'Speaker',0
  Capabilities: pvolume
  Playback channels: Front Left - Front Right
  Limits: Playback 0 - 127
  Mono:
  Front Left: Playback 109 [86%] [-12.00dB]
  Front Right: Playback 109 [86%] [-12.00dB]
"""


def test_parse_mixer_state_reads_raw_percent_and_db() -> None:
    state = audio_mixer_console.parse_mixer_state(
        MIXER_OUTPUT,
        card="wm8960soundcard",
        control="Speaker",
    )

    assert state.card == "wm8960soundcard"
    assert state.control == "Speaker"
    assert state.raw_min == 0
    assert state.raw_max == 127
    assert state.primary.raw_value == 109
    assert state.primary.percent == 86
    assert state.primary.db == "-12.00dB"
    assert len(state.channels) == 2


def test_parse_volume_command_accepts_only_logical_volume_range() -> None:
    assert audio_mixer_console.parse_volume_command("0") == 0
    assert audio_mixer_console.parse_volume_command("100") == 100
    assert audio_mixer_console.parse_volume_command("101") is None
    assert audio_mixer_console.parse_volume_command("-1") is None
    assert audio_mixer_console.parse_volume_command("tone") is None


def test_console_uses_longer_timeout_for_reference_audio() -> None:
    args = audio_mixer_console.build_parser().parse_args([])

    assert args.request_timeout == 30.0


def test_console_compares_curve_target_with_actual_raw_value(capsys) -> None:
    mixer = audio_mixer_console.parse_mixer_state(
        MIXER_OUTPUT,
        card="wm8960soundcard",
        control="Speaker",
    )

    audio_mixer_console.print_state(
        audio_mixer_console.RuntimeMixerState(
            runtime_volume=40,
            playback_owner=None,
            mixer=mixer,
            expected_raw=109,
        )
    )

    output = capsys.readouterr().out
    assert "Volume           : 40%" in output
    assert "Curve target    : raw 109" in output
    assert "Relationship    : MATCH" in output


def test_write_report_serializes_history(tmp_path: Path) -> None:
    destination = tmp_path / "reports" / "mixer.json"
    history = [{"action": "initial", "runtime_volume": 70}]

    audio_mixer_console.write_report(
        destination,
        RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=8765),
        history,
    )

    report = json.loads(destination.read_text(encoding="utf-8"))
    assert report["tool"] == "lafvin-hat-audio-mixer-console"
    assert report["endpoint"] == "tcp://127.0.0.1:8765"
    assert report["history"] == history
