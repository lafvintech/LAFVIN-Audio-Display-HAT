#!/usr/bin/env python3
"""Inspect and exercise the Runtime-owned WM8960 volume path.

The console never writes ALSA directly. It asks the Runtime to change Volume,
then reads ``amixer`` to show the resulting hardware state and whether it
matches the active LAFVIN volume curve.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from lafvin_hat.runtime.config import (  # noqa: E402
    RuntimeEndpoint,
    default_runtime_endpoint,
    parse_endpoint,
)
from lafvin_hat.hardware.audio import (  # noqa: E402
    Wm8960MixerState,
    parse_mixer_state as parse_profile_mixer_state,
)
from lafvin_hat.sdk.client import RuntimeClient, RuntimeClientError  # noqa: E402


DEFAULT_CONTROL = "Speaker"
SHORT_TONE = (880, 700)
DEFAULT_REQUEST_TIMEOUT_SEC = 30.0


@dataclass(frozen=True)
class RuntimeMixerState:
    runtime_volume: int
    playback_owner: str | None
    mixer: Wm8960MixerState
    expected_raw: int | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Interactive Runtime-owned WM8960 mixer diagnostic console"
        )
    )
    parser.add_argument(
        "--endpoint",
        help="Runtime endpoint URI; defaults to the active user or service socket",
    )
    parser.add_argument(
        "--card",
        help="ALSA card index or name; defaults to the Runtime audio card",
    )
    parser.add_argument(
        "--control",
        help="ALSA simple mixer control; defaults to the Runtime profile value",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=5,
        help="Logical-volume increment for '+' and '-' (default: 5)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Write the observed Runtime/Mixer states to this JSON file on exit",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_SEC,
        help=(
            "Seconds to wait for a Runtime response, including reference "
            "audio playback (default: 30)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.step <= 100:
        parser.error("--step must be between 1 and 100")
    if args.request_timeout <= 0:
        parser.error("--request-timeout must be greater than zero")
    try:
        return asyncio.run(run_console(args))
    except RuntimeClientError as exc:
        print(f"Runtime error: {exc.code}: {exc.message}", file=sys.stderr)
        return 2
    except asyncio.TimeoutError:
        print(
            "Audio mixer console timed out waiting for Runtime. "
            "Playback may still be active; wait for it to finish or use "
            "--request-timeout SECONDS.",
            file=sys.stderr,
        )
        return 2
    except (OSError, RuntimeError, ValueError) as exc:
        detail = str(exc) or repr(exc)
        print(f"Audio mixer console failed: {detail}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nConsole interrupted.")
        return 130


async def run_console(args: argparse.Namespace) -> int:
    endpoint = (
        parse_endpoint(args.endpoint)
        if args.endpoint
        else default_runtime_endpoint()
    )
    client = RuntimeClient(endpoint, timeout=args.request_timeout)
    history: list[dict[str, Any]] = []

    print("LAFVIN HAT Runtime Audio Mixer Console")
    print(f"Endpoint: {endpoint.as_uri()}")
    print("Writes use Runtime ownership; amixer is read-only in this tool.")
    print_commands(args.step)

    current = await collect_state(client, args)
    record_state(history, "initial", current)
    print_state(current)

    while True:
        try:
            command = input("mixer> ").strip().lower()
        except EOFError:
            print()
            command = "q"
        if command in {"q", "quit", "exit"}:
            break
        if command in {"h", "help", "?"}:
            print_commands(args.step)
            continue

        action: str | None = None
        if command in {"r", "refresh"}:
            action = "refresh"
        elif command in {"+", "up"}:
            value = min(100, current.runtime_volume + args.step)
            await set_runtime_volume(client, value)
            action = f"set:{value}"
        elif command in {"-", "down"}:
            value = max(0, current.runtime_volume - args.step)
            await set_runtime_volume(client, value)
            action = f"set:{value}"
        elif command in {"p", "tone", "short"}:
            await play_tone(client, current, *SHORT_TONE)
            action = "tone:short"
        elif command in {"l", "long", "reference"}:
            await play_reference_audio(client, current)
            action = "reference"
        else:
            value = parse_volume_command(command)
            if value is None:
                print("Unknown command. Enter h for help.")
                continue
            await set_runtime_volume(client, value)
            action = f"set:{value}"

        current = await collect_state(client, args)
        record_state(history, action, current)
        print_state(current)

    if args.report is not None:
        write_report(args.report, endpoint, history)
        print(f"Wrote report: {args.report}")
    return 0


def parse_volume_command(value: str) -> int | None:
    if not value.isdecimal():
        return None
    parsed = int(value)
    return parsed if 0 <= parsed <= 100 else None


async def collect_state(
    client: RuntimeClient,
    args: argparse.Namespace,
) -> RuntimeMixerState:
    status = await client.request("runtime.status")
    audio = status.get("audio")
    if not isinstance(audio, dict):
        raise RuntimeError("Runtime status does not contain an audio snapshot")
    runtime_volume = audio.get("volume")
    if isinstance(runtime_volume, bool) or not isinstance(runtime_volume, int):
        raise RuntimeError("Runtime audio volume is unavailable")
    card = args.card or audio.get("card")
    if card is None or not str(card).strip():
        raise RuntimeError(
            "Runtime did not report an ALSA card; use --card after checking "
            "install_driver.sh --check"
        )
    profile = audio.get("profile")
    profile_control = (
        profile.get("mixer_control") if isinstance(profile, dict) else None
    )
    control = args.control or profile_control or DEFAULT_CONTROL
    mixer = read_mixer_state(str(card), str(control))
    runtime_mixer = audio.get("mixer")
    expected_raw = (
        runtime_mixer.get("expected_raw")
        if isinstance(runtime_mixer, dict)
        else None
    )
    if isinstance(expected_raw, bool) or not isinstance(expected_raw, int):
        expected_raw = None
    owner = audio.get("playing_app_id")
    return RuntimeMixerState(
        runtime_volume=runtime_volume,
        playback_owner=owner if isinstance(owner, str) else None,
        mixer=mixer,
        expected_raw=expected_raw,
    )


async def set_runtime_volume(client: RuntimeClient, value: int) -> None:
    result = await client.request(
        "diagnostics.audio.volume.set",
        {"value": value},
    )
    actual = result.get("value")
    print(f"Volume set to {actual}%.")


async def play_tone(
    client: RuntimeClient,
    state: RuntimeMixerState,
    frequency_hz: int,
    duration_ms: int,
) -> None:
    if state.playback_owner is not None:
        print(
            "Playback is active for "
            f"{state.playback_owner}; stop it before playing a diagnostic tone."
        )
        return
    await client.request(
        "diagnostics.audio.tone.play",
        {
            "frequency_hz": frequency_hz,
            "duration_ms": duration_ms,
        },
    )
    print(f"Played {frequency_hz} Hz tone for {duration_ms} ms via Runtime.")


async def play_reference_audio(
    client: RuntimeClient,
    state: RuntimeMixerState,
) -> None:
    if state.playback_owner is not None:
        print(
            "Playback is active for "
            f"{state.playback_owner}; stop it before playing reference audio."
        )
        return
    result = await client.request("diagnostics.audio.reference.play")
    print(f"Played {result['resource']} via Runtime.")


def read_mixer_state(card: str, control: str) -> Wm8960MixerState:
    try:
        result = subprocess.run(
            ["amixer", "-c", card, "sget", control],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("amixer is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("amixer did not respond within 5 seconds") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"amixer could not read {control!r} on card {card!r}: {detail}"
        )
    return parse_mixer_state(result.stdout, card=card, control=control)


def parse_mixer_state(
    value: str,
    *,
    card: str,
    control: str,
) -> Wm8960MixerState:
    """Compatibility wrapper around the hardware-profile parser."""

    return parse_profile_mixer_state(value, card=card, control=control)


def print_commands(step: int) -> None:
    print(
        "Commands: 0..100 set Volume; "
        f"+/- adjust by {step}%; p short 880 Hz tone; "
        "l reference speech WAV; r refresh; h help; q quit."
    )


def print_state(state: RuntimeMixerState) -> None:
    mixer = state.mixer
    primary = mixer.primary
    raw_range = f"{mixer.raw_min}..{mixer.raw_max}"
    db = f", {primary.db}" if primary.db else ""
    channel_suffix = ""
    if len(mixer.channels) > 1:
        rendered = ", ".join(
            f"{channel.name}={channel.raw_value}/{channel.percent}%"
            for channel in mixer.channels
        )
        channel_suffix = f"; channels: {rendered}"
    relation = (
        "UNAVAILABLE"
        if state.expected_raw is None
        else "MATCH"
        if state.expected_raw == primary.raw_value
        else "MISMATCH"
    )
    playback = state.playback_owner or "idle"
    print()
    print(f"Volume           : {state.runtime_volume}%")
    print(
        f"ALSA {mixer.control:<10}: {primary.percent}% "
        f"(raw {primary.raw_value}, range {raw_range}{db}){channel_suffix}"
    )
    if state.expected_raw is not None:
        print(f"Curve target    : raw {state.expected_raw}")
    print(f"Relationship    : {relation}")
    print(f"Playback        : {playback}")


def record_state(
    history: list[dict[str, Any]],
    action: str,
    state: RuntimeMixerState,
) -> None:
    history.append(
        {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "runtime_volume": state.runtime_volume,
            "expected_raw": state.expected_raw,
            "playback_owner": state.playback_owner,
            "mixer": asdict(state.mixer),
        }
    )


def write_report(
    path: Path,
    endpoint: RuntimeEndpoint,
    history: list[dict[str, Any]],
) -> None:
    destination = path.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "tool": "lafvin-hat-audio-mixer-console",
                "version": 1,
                "endpoint": endpoint.as_uri(),
                "history": history,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
