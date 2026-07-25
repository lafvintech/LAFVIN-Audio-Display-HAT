#!/usr/bin/env python3
"""Measure the WM8960 microphone path before defining a LAFVIN Mic control.

This is a checkout-developer calibration tool, not an App or Runtime API. It
uses direct ALSA access only while the Runtime is stopped, so temporary capture
gain experiments cannot race an active recording session. Mixer writes require
``--allow-write`` and are restored on exit unless ``--keep-changes`` is given.
"""

from __future__ import annotations

import argparse
import array
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from lafvin_hat.hardware.audio import Wm8960AudioProfile  # noqa: E402


CAPTURE_VOLUME_CONTROL = "Capture Volume"
LEFT_INPUT_BOOST_CONTROL = "Left Input Boost Mixer LINPUT1 Volume"
RIGHT_INPUT_BOOST_CONTROL = "Right Input Boost Mixer RINPUT1 Volume"
ADC_CAPTURE_VOLUME_CONTROL = "ADC PCM Capture Volume"
TUNABLE_CONTROLS = (
    CAPTURE_VOLUME_CONTROL,
    LEFT_INPUT_BOOST_CONTROL,
    RIGHT_INPUT_BOOST_CONTROL,
    ADC_CAPTURE_VOLUME_CONTROL,
)
DEFAULT_SETTLE_MS = 250


@dataclass(frozen=True)
class MixerControlState:
    """Integer ALSA control values and limits returned by ``amixer cget``."""

    name: str
    values: tuple[int, ...]
    minimum: int
    maximum: int
    db_scale_min: str | None
    db_scale_step: str | None


@dataclass(frozen=True)
class SignalMetrics:
    """One channel's level and clipping metrics for one recording segment."""

    sample_count: int
    mean: float
    rms: float
    rms_dbfs: float | None
    peak: int
    peak_dbfs: float | None
    clipped_samples: int
    clipped_percent: float


@dataclass(frozen=True)
class CaptureChannelMetrics:
    name: str
    silence: SignalMetrics
    speech: SignalMetrics


@dataclass(frozen=True)
class CaptureMetrics:
    silence_path: str
    speech_path: str
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    frame_count: int
    duration_ms: int
    silence_duration_ms: int
    speech_duration_ms: int
    channel_metrics: tuple[CaptureChannelMetrics, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive WM8960 microphone calibration console"
    )
    parser.add_argument(
        "--card",
        help="ALSA card index or name; defaults to the WM8960 profile card",
    )
    parser.add_argument(
        "--silence-seconds",
        type=int,
        default=1,
        help="Initial quiet portion of each capture (default: 1)",
    )
    parser.add_argument(
        "--speech-seconds",
        type=int,
        default=3,
        help="Normal-voice portion of each capture (default: 3)",
    )
    parser.add_argument(
        "--settle-ms",
        type=int,
        default=DEFAULT_SETTLE_MS,
        help=(
            "Discard this much startup audio from each separate capture phase "
            f"(default: {DEFAULT_SETTLE_MS})"
        ),
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Allow temporary direct ALSA writes to candidate capture controls",
    )
    parser.add_argument(
        "--keep-changes",
        action="store_true",
        help=(
            "Do not restore controls on exit. This is for a deliberate final "
            "comparison only; changes are still not persisted into the profile."
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Write controls and capture measurements to this JSON file on exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.silence_seconds < 0:
        parser.error("--silence-seconds must be zero or greater")
    if not 1 <= args.speech_seconds <= 60:
        parser.error("--speech-seconds must be between 1 and 60")
    if not 0 <= args.settle_ms <= 2_000:
        parser.error("--settle-ms must be between 0 and 2000")
    if args.silence_seconds + args.speech_seconds > 60:
        parser.error("combined capture duration must not exceed 60 seconds")
    if args.keep_changes and not args.allow_write:
        parser.error("--keep-changes requires --allow-write")

    try:
        return run_console(args)
    except (OSError, RuntimeError, ValueError, wave.Error) as exc:
        detail = str(exc) or repr(exc)
        print(f"Audio capture console failed: {detail}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nConsole interrupted.")
        return 130


def run_console(args: argparse.Namespace) -> int:
    if _service_is_active("lafvin-hat.service"):
        raise RuntimeError(
            "lafvin-hat.service is active and owns audio. Stop it first with "
            "'sudo systemctl stop lafvin-hat'. Also stop any manually started "
            "Runtime before using this direct ALSA calibration tool."
        )
    for command in ("amixer", "arecord", "aplay"):
        if shutil.which(command) is None:
            raise RuntimeError(f"Required audio command not found: {command}")

    profile = Wm8960AudioProfile()
    card = args.card or profile.find_card()
    with CaptureConsole(args=args, card=str(card), profile=profile) as console:
        result = console.run()
    if args.report is not None:
        console.write_report(args.report)
        print(f"Wrote report: {args.report}")
    return result


class CaptureConsole:
    def __init__(
        self,
        *,
        args: argparse.Namespace,
        card: str,
        profile: Wm8960AudioProfile,
    ) -> None:
        self.args = args
        self.card = card
        self.profile = profile
        self._temporary_directory = tempfile.TemporaryDirectory(
            prefix="lafvin-hat-capture-"
        )
        self._initial_controls: dict[str, MixerControlState] = {}
        self._history: list[dict[str, Any]] = []
        self._last_recording: Path | None = None
        self._changed = False

    def __enter__(self) -> CaptureConsole:
        self._initial_controls = self.read_controls()
        return self

    def __exit__(self, *_: object) -> None:
        try:
            if self._changed and not self.args.keep_changes:
                self.restore_initial_controls()
        finally:
            self._temporary_directory.cleanup()

    def run(self) -> int:
        print("LAFVIN HAT WM8960 Capture Calibration Console")
        print(f"ALSA card: {self.card}")
        print(
            "Direct ALSA calibration: keep Runtime stopped. "
            "Writes are disabled unless --allow-write is supplied."
        )
        if self.args.allow_write:
            print(
                "Temporary writes will be restored on exit. Use --keep-changes "
                "only for a deliberate final comparison."
            )
        self.print_commands()
        self.print_controls(self._initial_controls)

        while True:
            try:
                command = input("capture> ").strip()
            except EOFError:
                print()
                command = "q"
            action = self.handle_command(command)
            if action == "quit":
                break

        return 0

    def handle_command(self, value: str) -> str | None:
        command = value.strip().lower()
        if command in {"q", "quit", "exit"}:
            return "quit"
        if command in {"h", "help", "?"}:
            self.print_commands()
            return None
        if command in {"s", "status"}:
            self.print_controls(self.read_controls())
            return None
        if command in {"r", "record"}:
            self.capture_reference()
            return None
        if command in {"p", "play", "replay"}:
            self.play_last_recording()
            return None
        if command in {"x", "reset", "restore"}:
            self.require_writes("reset controls")
            self.restore_initial_controls()
            self.print_controls(self.read_controls())
            return None

        parsed = parse_tuning_command(command)
        if parsed is None:
            print("Unknown command. Enter h for help.")
            return None
        name, raw_value = parsed
        self.require_writes(f"set {name}")
        self.set_tuning_value(name, raw_value)
        self.print_controls(self.read_controls())
        return None

    def print_commands(self) -> None:
        print(
            "Commands: s status; r record reference; p replay last capture; "
            "c N capture gain (0..63); b N input boost (0..3); "
            "a N ADC gain (0..255); x reset; h help; q quit."
        )
        print(
            "For every capture: stay quiet first, then use the same normal voice, "
            "distance, and phrase: 'LAFVIN microphone calibration one two three "
            "four five.'"
        )

    def read_controls(self) -> dict[str, MixerControlState]:
        return {
            name: read_control(self.card, name)
            for name in TUNABLE_CONTROLS
        }

    def print_controls(self, controls: dict[str, MixerControlState]) -> None:
        print()
        print("Capture path controls")
        for name in TUNABLE_CONTROLS:
            control = controls[name]
            values = ", ".join(str(value) for value in control.values)
            details = f"raw {values}; range {control.minimum}..{control.maximum}"
            if control.db_scale_min is not None:
                details += f"; dB min {control.db_scale_min}"
            if control.db_scale_step is not None:
                details += f"; step {control.db_scale_step}"
            print(f"{name}: {details}")

    def require_writes(self, action: str) -> None:
        if not self.args.allow_write:
            raise RuntimeError(
                f"Refusing to {action} without --allow-write. The default mode "
                "is read-only."
            )

    def set_tuning_value(self, name: str, raw_value: int) -> None:
        # Mark this before the first write so __exit__ restores a partially
        # applied multi-control change if one ALSA command fails.
        self._changed = True
        if name == "capture":
            state = self._initial_controls[CAPTURE_VOLUME_CONTROL]
            ensure_range(raw_value, state, "capture gain")
            set_control(
                self.card,
                CAPTURE_VOLUME_CONTROL,
                tuple(raw_value for _ in state.values),
            )
        elif name == "boost":
            for control_name in (
                LEFT_INPUT_BOOST_CONTROL,
                RIGHT_INPUT_BOOST_CONTROL,
            ):
                state = self._initial_controls[control_name]
                ensure_range(raw_value, state, "input boost")
                set_control(self.card, control_name, (raw_value,))
        elif name == "adc":
            state = self._initial_controls[ADC_CAPTURE_VOLUME_CONTROL]
            ensure_range(raw_value, state, "ADC gain")
            set_control(
                self.card,
                ADC_CAPTURE_VOLUME_CONTROL,
                tuple(raw_value for _ in state.values),
            )
        else:
            raise RuntimeError(f"Unknown tuning control: {name}")
        self.record_event("set", {"control": name, "raw_value": raw_value})

    def capture_reference(self) -> None:
        sequence = len(self._history)
        root = Path(self._temporary_directory.name)
        silence_path = root / f"capture-{sequence:03d}-silence.wav"
        speech_path = root / f"capture-{sequence:03d}-speech.wav"
        print()
        print(
            "Phase 1/2: remain quiet. The silence capture starts after this "
            "countdown."
        )
        for value in (3, 2, 1):
            print(f"Starting in {value}...")
            time.sleep(1)
        self._record_segment(
            silence_path,
            duration_seconds=self.args.silence_seconds,
            phase="silence",
        )
        print(
            "Phase 2/2: SPEAK NOW. Start the displayed phrase immediately and "
            "continue speaking until recording completes."
        )
        self._record_segment(
            speech_path,
            duration_seconds=self.args.speech_seconds,
            phase="speech",
        )
        metrics = measure_capture_pair(
            silence_path,
            speech_path,
            settle_ms=self.args.settle_ms,
        )
        self._last_recording = speech_path
        self.record_event(
            "record",
            {
                "controls": {
                    name: asdict(state)
                    for name, state in self.read_controls().items()
                },
                "metrics": asdict(metrics),
            },
        )
        print_capture_metrics(metrics)

    def _record_segment(
        self,
        destination: Path,
        *,
        duration_seconds: int,
        phase: str,
    ) -> None:
        process = subprocess.Popen(
            self.profile.recording_command(
                self.profile.capture_device(self.card),
                destination,
                max_duration_sec=duration_seconds,
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if phase == "silence":
            print(f"Recording silence for {duration_seconds}s...")
        else:
            print(f"Recording speech for {duration_seconds}s...")
        stdout, stderr = process.communicate()
        if process.returncode != 0 or not destination.is_file():
            detail = (stderr or stdout).strip()
            raise RuntimeError(
                "arecord failed: "
                f"{detail or f'exit code {process.returncode}'}"
            )

    def play_last_recording(self) -> None:
        if self._last_recording is None:
            print("No capture exists yet. Record first with r.")
            return
        result = subprocess.run(
            [
                "aplay",
                "-D",
                self.profile.playback_device(self.card),
                str(self._last_recording),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                "aplay failed: "
                f"{detail or f'exit code {result.returncode}'}"
            )
        self.record_event("play", {"path": str(self._last_recording)})
        print("Played the most recent capture.")

    def restore_initial_controls(self) -> None:
        for name, state in self._initial_controls.items():
            set_control(self.card, name, state.values)
        self._changed = False
        self.record_event("restore", {})
        print("Restored the capture controls recorded when this console started.")

    def record_event(self, action: str, payload: dict[str, Any]) -> None:
        self._history.append(
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "action": action,
                **payload,
            }
        )

    def write_report(self, path: Path) -> None:
        destination = path.expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {
                    "tool": "lafvin-hat-audio-capture-console",
                    "version": 1,
                    "card": self.card,
                    "initial_controls": {
                        name: asdict(state)
                        for name, state in self._initial_controls.items()
                    },
                    "history": self._history,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def parse_tuning_command(value: str) -> tuple[str, int] | None:
    words = value.split()
    if len(words) != 2 or words[0] not in {
        "c",
        "capture",
        "b",
        "boost",
        "a",
        "adc",
    }:
        return None
    if not words[1].isdecimal():
        return None
    name = {
        "c": "capture",
        "capture": "capture",
        "b": "boost",
        "boost": "boost",
        "a": "adc",
        "adc": "adc",
    }[words[0]]
    return name, int(words[1])


def read_control(card: str, name: str) -> MixerControlState:
    output = run_amixer(["-c", card, "cget", f"name={name}"])
    return parse_control_state(output, name=name)


def set_control(card: str, name: str, values: tuple[int, ...]) -> None:
    rendered = ",".join(str(value) for value in values)
    run_amixer(["-c", card, "cset", f"name={name}", rendered])


def run_amixer(arguments: list[str]) -> str:
    result = subprocess.run(
        ["amixer", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            "amixer failed: "
            f"{detail or f'exit code {result.returncode}'}"
        )
    return result.stdout


def parse_control_state(value: str, *, name: str) -> MixerControlState:
    """Parse the integer shape produced by ``amixer cget name=<control>``."""

    metadata = next(
        (
            line.strip()
            for line in value.splitlines()
            if "min=" in line and "max=" in line
        ),
        None,
    )
    values_line = next(
        (
            line.strip()
            for line in value.splitlines()
            if line.strip().startswith(": values=")
        ),
        None,
    )
    if metadata is None or values_line is None:
        raise RuntimeError(f"Could not parse amixer control: {name}")
    limits = _parse_limits(metadata)
    if limits is None:
        raise RuntimeError(f"Could not parse amixer limits: {name}")
    rendered_values = values_line.removeprefix(": values=")
    try:
        values = tuple(int(item) for item in rendered_values.split(","))
    except ValueError as exc:
        raise RuntimeError(f"Could not parse amixer values: {name}") from exc
    if not values:
        raise RuntimeError(f"amixer returned no values: {name}")
    db_line = next(
        (line.strip() for line in value.splitlines() if "dBscale-min=" in line),
        None,
    )
    db_min, db_step = _parse_db_scale(db_line) if db_line else (None, None)
    return MixerControlState(
        name=name,
        values=values,
        minimum=limits[0],
        maximum=limits[1],
        db_scale_min=db_min,
        db_scale_step=db_step,
    )


def _parse_limits(value: str) -> tuple[int, int] | None:
    fields = {
        key.strip(): raw_value.strip()
        for key, raw_value in (
            field.split("=", 1)
            for field in value.replace(";", "").split(",")
            if "=" in field
        )
    }
    try:
        return int(fields["min"]), int(fields["max"])
    except (KeyError, ValueError):
        return None


def _parse_db_scale(value: str) -> tuple[str | None, str | None]:
    fields = {
        key.strip(): raw_value.strip()
        for key, raw_value in (
            field.split("=", 1)
            for field in value.removeprefix("|").split(",")
            if "=" in field
        )
    }
    return fields.get("dBscale-min"), fields.get("step")


def ensure_range(value: int, state: MixerControlState, label: str) -> None:
    if not state.minimum <= value <= state.maximum:
        raise RuntimeError(
            f"{label} must be between {state.minimum} and {state.maximum}"
        )


def measure_capture_pair(
    silence_path: Path,
    speech_path: Path,
    *,
    settle_ms: int,
) -> CaptureMetrics:
    silence_rate, silence_channels, silence_width, silence_frames, silence_data = (
        _read_wav(silence_path)
    )
    speech_rate, speech_channels, speech_width, speech_frames, speech_data = (
        _read_wav(speech_path)
    )
    if (silence_rate, silence_channels, silence_width) != (
        speech_rate,
        speech_channels,
        speech_width,
    ):
        raise RuntimeError("Silence and speech captures have incompatible WAV formats")
    settle_frames = int(settle_ms * silence_rate / 1000)
    silence_start = min(silence_frames, settle_frames)
    speech_start = min(speech_frames, settle_frames)
    captured_channels: list[CaptureChannelMetrics] = []
    for channel_index in range(silence_channels):
        silence_values = silence_data[channel_index::silence_channels]
        speech_values = speech_data[channel_index::speech_channels]
        captured_channels.append(
            CaptureChannelMetrics(
                name=f"Channel {channel_index + 1}",
                silence=measure_signal(silence_values[silence_start:]),
                speech=measure_signal(speech_values[speech_start:]),
            )
        )
    kept_silence_frames = silence_frames - silence_start
    kept_speech_frames = speech_frames - speech_start
    return CaptureMetrics(
        silence_path=str(silence_path),
        speech_path=str(speech_path),
        sample_rate_hz=silence_rate,
        channels=silence_channels,
        sample_width_bytes=silence_width,
        frame_count=kept_silence_frames + kept_speech_frames,
        duration_ms=int((kept_silence_frames + kept_speech_frames) * 1000 / silence_rate),
        silence_duration_ms=int(kept_silence_frames * 1000 / silence_rate),
        speech_duration_ms=int(kept_speech_frames * 1000 / silence_rate),
        channel_metrics=tuple(captured_channels),
    )


def _read_wav(path: Path) -> tuple[int, int, int, int, array.array]:
    with wave.open(str(path), "rb") as input_file:
        channels = input_file.getnchannels()
        sample_width = input_file.getsampwidth()
        sample_rate = input_file.getframerate()
        frames = input_file.getnframes()
        data = input_file.readframes(frames)
    if channels < 1:
        raise RuntimeError("Recording has no audio channels")
    if sample_width != 4:
        raise RuntimeError(
            f"Expected 32-bit capture data, received {sample_width * 8}-bit audio"
        )
    values = array.array("i")
    values.frombytes(data)
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) != frames * channels:
        raise RuntimeError("Recording data length does not match its WAV metadata")
    return sample_rate, channels, sample_width, frames, values


def measure_signal(values: array.array) -> SignalMetrics:
    if not values:
        return SignalMetrics(0, 0.0, 0.0, None, 0, None, 0, 0.0)
    full_scale = (1 << 31) - 1
    count = len(values)
    mean = sum(values) / count
    rms = math.sqrt(sum(float(value) * float(value) for value in values) / count)
    peak = max(abs(value) for value in values)
    clipped_samples = sum(
        1 for value in values if abs(value) >= int(full_scale * 0.999)
    )
    return SignalMetrics(
        sample_count=count,
        mean=mean,
        rms=rms,
        rms_dbfs=to_dbfs(rms, full_scale),
        peak=peak,
        peak_dbfs=to_dbfs(peak, full_scale),
        clipped_samples=clipped_samples,
        clipped_percent=clipped_samples * 100 / count,
    )


def to_dbfs(value: float, full_scale: int) -> float | None:
    if value <= 0:
        return None
    return 20 * math.log10(value / full_scale)


def print_capture_metrics(metrics: CaptureMetrics) -> None:
    print()
    print(
        f"Capture: {metrics.duration_ms} ms, {metrics.sample_rate_hz} Hz, "
        f"{metrics.channels} channels, {metrics.sample_width_bytes * 8}-bit"
    )
    for channel in metrics.channel_metrics:
        silence = channel.silence
        speech = channel.speech
        print(
            f"{channel.name}: silence RMS {format_dbfs(silence.rms_dbfs)}; "
            f"speech RMS {format_dbfs(speech.rms_dbfs)}; "
            f"peak {format_dbfs(speech.peak_dbfs)}; "
            f"clipping {speech.clipped_percent:.3f}%"
        )
        if speech.clipped_percent > 0:
            print("  Review: detected full-scale samples; this setting may clip.")
        if speech.rms_dbfs is not None and silence.rms_dbfs is not None:
            separation = speech.rms_dbfs - silence.rms_dbfs
            print(f"  Speech over silence: {separation:.1f} dB")


def format_dbfs(value: float | None) -> str:
    return "-inf dBFS" if value is None else f"{value:.1f} dBFS"


def _service_is_active(name: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", name],
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())
