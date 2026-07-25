#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave
from array import array
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def main() -> int:
    args = _parser().parse_args()
    if _service_is_active("lafvin-hat.service") and not args.force:
        print(
            "lafvin-hat.service is active and owns the hardware.\n"
            "Stop it first with: sudo systemctl stop lafvin-hat\n"
            "Use --force only when you know no Runtime is using the device."
        )
        return 2

    card = args.card or _find_wm8960_card()
    if card is None:
        print("WM8960 was not found in /proc/asound/cards.")
        print("Run: bash tools/hardware_check.sh")
        return 2

    from lafvin_hat.hardware import LafvinHatBoard

    results: dict[str, bool] = {}
    board: LafvinHatBoard | None = None
    try:
        board = LafvinHatBoard()
        results["display"] = _test_display(board)
        results["led"] = _test_led(board)
        results["button"] = _test_button(board, args.button_timeout)
        results["speaker"] = _test_speaker(card)
        results["microphone"] = _test_microphone(card, args.record_seconds)
    except Exception as exc:
        print(f"Hardware test aborted: {type(exc).__name__}: {exc}")
        return 1
    finally:
        if board is not None:
            board.led.set(0, 0, 0)
            board.cleanup()

    print("\nHardware test summary")
    print("=====================")
    for name, passed in results.items():
        print(f"{name:12}: {'PASS' if passed else 'FAIL'}")
    return 0 if all(results.values()) else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive LAFVIN HAT hardware acceptance test"
    )
    parser.add_argument(
        "--card",
        help="ALSA card index or name; defaults to WM8960 auto-detection",
    )
    parser.add_argument(
        "--record-seconds",
        type=int,
        default=3,
        help="Microphone recording duration (default: 3)",
    )
    parser.add_argument(
        "--button-timeout",
        type=int,
        default=20,
        help="Seconds to wait for button press and release (default: 20)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even when lafvin-hat.service appears active",
    )
    return parser


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


def _find_wm8960_card() -> str | None:
    try:
        value = Path("/proc/asound/cards").read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None
    return _parse_wm8960_card(value)


def _parse_wm8960_card(value: str) -> str | None:
    match = re.search(
        r"^\s*(\d+)\s+\[[^\]]*wm8960[^\]]*\]",
        value,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if match is not None:
        return match.group(1)
    for line in value.splitlines():
        if "wm8960" not in line.lower():
            continue
        index = re.match(r"\s*(\d+)", line)
        if index is not None:
            return index.group(1)
    return None


def _confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _test_display(board: LafvinHatBoard) -> bool:
    print("\nDisplay test: red, green, and blue frames will be shown.")
    board.backlight.set(100)
    for color in (0xF800, 0x07E0, 0x001F):
        board.display.fill_rgb565(color)
        time.sleep(0.7)
    board.display.fill_rgb565(0x0000)
    return _confirm("Were all three colors stable and correct?")


def _test_led(board: LafvinHatBoard) -> bool:
    print("\nLED test: red, green, and blue will be shown.")
    for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255)):
        board.led.set(*color)
        time.sleep(0.7)
    board.led.set(0, 0, 0)
    return _confirm("Did the RGB LED show all three colors?")


def _test_button(board: LafvinHatBoard, timeout: int) -> bool:
    pressed = threading.Event()
    released = threading.Event()
    board.button.bind(pressed.set, released.set)
    print(f"\nButton test: press and release the button within {timeout}s.")
    if not pressed.wait(timeout):
        print("Button press was not detected.")
        return False
    if not released.wait(timeout):
        print("Button release was not detected.")
        return False
    print("Button press and release detected.")
    return True


def _test_speaker(card: str) -> bool:
    print("\nSpeaker test: playing a short confirmation tone.")
    with tempfile.TemporaryDirectory(prefix="lafvin-hat-test-") as temp:
        tone = Path(temp) / "tone.wav"
        _write_tone(tone)
        result = subprocess.run(
            ["aplay", "-D", f"plughw:{card},0", str(tone)],
            check=False,
        )
    if result.returncode != 0:
        print(f"aplay exited with code {result.returncode}.")
        return False
    return _confirm("Did you hear the confirmation tone?")


def _test_microphone(card: str, seconds: int) -> bool:
    print(f"\nMicrophone test: recording for {seconds} seconds.")
    input("Press Enter, then speak into the microphone...")
    with tempfile.TemporaryDirectory(prefix="lafvin-hat-test-") as temp:
        recording = Path(temp) / "recording.wav"
        record = subprocess.run(
            [
                "arecord",
                "-D",
                f"hw:{card},0",
                "-f",
                "S32_LE",
                "-r",
                "16000",
                "-c",
                "2",
                "-t",
                "wav",
                "-d",
                str(max(1, seconds)),
                str(recording),
            ],
            check=False,
        )
        if record.returncode != 0 or not recording.is_file():
            print(f"arecord exited with code {record.returncode}.")
            return False
        print("Playing the microphone recording.")
        playback = subprocess.run(
            ["aplay", "-D", f"plughw:{card},0", str(recording)],
            check=False,
        )
    if playback.returncode != 0:
        print(f"aplay exited with code {playback.returncode}.")
        return False
    return _confirm("Could you clearly hear the recorded voice?")


def _write_tone(path: Path) -> None:
    sample_rate = 16000
    duration = 0.5
    samples = array(
        "h",
        (
            int(10000 * math.sin(2 * math.pi * 660 * index / sample_rate))
            for index in range(int(sample_rate * duration))
        ),
    )
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(samples.tobytes())


if __name__ == "__main__":
    raise SystemExit(main())
