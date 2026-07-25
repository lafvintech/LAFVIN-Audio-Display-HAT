"""LAFVIN HAT WM8960 audio profile.

This module owns board-specific ALSA naming and command construction.  The
Runtime audio service continues to own sessions, interruption, and permissions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


PROFILE_NAME = "lafvin-hat-wm8960"
PROFILE_VERSION = "2"
PROFILE_LICENSE = "GPL-3.0"
ARCHIVE_SHA256 = "8f2aaea499200843ecc4dc506bec615cab5c1f527d1e72501d2157c28369c80e"

# LAFVIN product volume is deliberately not the ALSA percentage.  The points
# were measured against the supported WM8960 Speaker control, whose
# raw range is 0..127.  Values between anchors are linearly interpolated.
VOLUME_CURVE: tuple[tuple[int, int], ...] = (
    (0, 51),
    (10, 102),
    (20, 104),
    (30, 107),
    (40, 109),
    (50, 112),
    (60, 114),
    (70, 117),
    (80, 119),
    (90, 124),
    (100, 127),
)
_CURVE_RAW_MIN = 0
_CURVE_RAW_MAX = 127
_LIMITS_PATTERN = re.compile(
    r"Limits:\s+Playback\s+(-?\d+)\s*-\s*(-?\d+)",
    flags=re.IGNORECASE,
)
_CHANNEL_PATTERN = re.compile(
    r"^\s*(Front Left|Front Right|Mono):\s+Playback\s+(-?\d+)"
    r"\s+\[(\d+)%\](?:\s+\[([^\]]+)\])?",
    flags=re.IGNORECASE | re.MULTILINE,
)


class Wm8960ProfileError(RuntimeError):
    """The LAFVIN HAT WM8960 profile is unavailable or incomplete."""


@dataclass(frozen=True, slots=True)
class Wm8960MixerChannel:
    """One parsed ALSA playback channel from the supported Speaker control."""

    name: str
    raw_value: int
    percent: int
    db: str | None


@dataclass(frozen=True, slots=True)
class Wm8960MixerState:
    """Readback state for the supported WM8960 Speaker mixer control."""

    card: str
    control: str
    raw_min: int
    raw_max: int
    channels: tuple[Wm8960MixerChannel, ...]

    @property
    def primary(self) -> Wm8960MixerChannel:
        return self.channels[0]


def find_alsa_card(value: str, needle: str) -> str | None:
    """Return the first ALSA card index whose full description matches needle."""

    current_card: str | None = None
    current_lines: list[str] = []

    def match_current() -> str | None:
        if (
            current_card is not None
            and needle.lower() in " ".join(current_lines).lower()
        ):
            return current_card
        return None

    for line in value.splitlines():
        match = re.match(r"^\s*(\d+)\s+\[", line)
        if match:
            found = match_current()
            if found is not None:
                return found
            current_card = match.group(1)
            current_lines = [line]
        elif current_card is not None:
            current_lines.append(line)
    return match_current()


def parse_mixer_state(
    value: str,
    *,
    card: str,
    control: str,
) -> Wm8960MixerState:
    """Parse ``amixer sget`` output for the supported playback control."""

    limits = _LIMITS_PATTERN.search(value)
    if limits is None:
        raise Wm8960ProfileError(
            f"Could not read raw playback limits for {control!r} on card {card!r}"
        )
    raw_min = int(limits.group(1))
    raw_max = int(limits.group(2))
    if raw_max <= raw_min:
        raise Wm8960ProfileError(
            f"Invalid playback limits for {control!r}: {raw_min}..{raw_max}"
        )
    channels = tuple(
        Wm8960MixerChannel(
            name=match.group(1),
            raw_value=int(match.group(2)),
            percent=int(match.group(3)),
            db=match.group(4),
        )
        for match in _CHANNEL_PATTERN.finditer(value)
    )
    if not channels:
        raise Wm8960ProfileError(
            f"Could not parse playback value for {control!r} on card {card!r}"
        )
    return Wm8960MixerState(
        card=card,
        control=control,
        raw_min=raw_min,
        raw_max=raw_max,
        channels=channels,
    )


@dataclass(frozen=True, slots=True)
class Wm8960AudioProfile:
    """The supported Raspberry Pi LAFVIN HAT WM8960 ALSA contract."""

    name: str = PROFILE_NAME
    version: str = PROFILE_VERSION
    license: str = PROFILE_LICENSE
    archive_sha256: str = ARCHIVE_SHA256
    card_match: str = "wm8960"
    mixer_control: str = "Speaker"
    recording_sample_format: str = "S32_LE"
    recording_rate_hz: int = 16000
    recording_channels: int = 2
    volume_curve: tuple[tuple[int, int], ...] = VOLUME_CURVE

    @property
    def recording_format(self) -> str:
        return (
            f"{self.recording_sample_format}/{self.recording_rate_hz}Hz/"
            f"{self.recording_channels}ch"
        )

    @property
    def recovery_command(self) -> str:
        return "sudo bash install_driver.sh --check"

    def find_card(self, cards_path: Path = Path("/proc/asound/cards")) -> str:
        try:
            cards = cards_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise Wm8960ProfileError(
                "Cannot inspect ALSA cards for the LAFVIN HAT WM8960 profile. "
                f"Run '{self.recovery_command}'."
            ) from exc
        card = find_alsa_card(cards, self.card_match)
        if card is None:
            raise Wm8960ProfileError(
                "LAFVIN HAT WM8960 ALSA sound card was not found. "
                f"Run '{self.recovery_command}', then install the profile "
                "with 'sudo bash install_driver.sh' and reboot if needed."
            )
        return card

    @staticmethod
    def capture_device(card: str) -> str:
        return f"hw:{card},0"

    @staticmethod
    def playback_device(card: str) -> str:
        return f"plughw:{card},0"

    def recording_command(
        self,
        device: str,
        path: Path,
        *,
        max_duration_sec: int,
    ) -> tuple[str, ...]:
        return (
            "arecord",
            "-D",
            device,
            "-f",
            self.recording_sample_format,
            "-r",
            str(self.recording_rate_hz),
            "-c",
            str(self.recording_channels),
            "-t",
            "wav",
            "-d",
            str(max_duration_sec),
            str(path),
        )

    def volume_command(
        self,
        card: str,
        value: int,
        *,
        raw_min: int = _CURVE_RAW_MIN,
        raw_max: int = _CURVE_RAW_MAX,
    ) -> tuple[str, ...]:
        raw_value = self.logical_volume_to_raw(
            value,
            raw_min=raw_min,
            raw_max=raw_max,
        )
        return (
            "amixer",
            "-c",
            card,
            "sset",
            self.mixer_control,
            str(raw_value),
        )

    def volume_read_command(self, card: str) -> tuple[str, ...]:
        return (
            "amixer",
            "-c",
            card,
            "sget",
            self.mixer_control,
        )

    def parse_mixer_state(
        self,
        value: str,
        *,
        card: str,
    ) -> Wm8960MixerState:
        return parse_mixer_state(
            value,
            card=card,
            control=self.mixer_control,
        )

    def logical_volume_to_raw(
        self,
        value: int,
        *,
        raw_min: int = _CURVE_RAW_MIN,
        raw_max: int = _CURVE_RAW_MAX,
    ) -> int:
        """Map a LAFVIN 0..100 level to the device's raw mixer range."""

        base_value = _interpolate_curve(
            self.volume_curve,
            max(0, min(100, int(value))),
        )
        return _scale_raw_value(base_value, raw_min=raw_min, raw_max=raw_max)

    def raw_to_logical_volume(
        self,
        value: int,
        *,
        raw_min: int,
        raw_max: int,
    ) -> int:
        """Map a readback raw mixer value to a LAFVIN 0..100 level."""

        base_value = _unscale_raw_value(
            value,
            raw_min=raw_min,
            raw_max=raw_max,
        )
        return _interpolate_curve_inverse(self.volume_curve, base_value)

    def snapshot(
        self,
        *,
        card: str | None,
        capture_device: str | None,
        playback_device: str | None,
    ) -> dict[str, str | None]:
        return {
            "name": self.name,
            "version": self.version,
            "license": self.license,
            "resource_sha256": self.archive_sha256,
            "card": card,
            "capture_device": capture_device,
            "playback_device": playback_device,
            "recording_format": self.recording_format,
            "mixer_control": self.mixer_control,
            "volume_curve": "lafvin-wm8960-v1",
        }


def _interpolate_curve(
    points: tuple[tuple[int, int], ...],
    value: int,
) -> int:
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]
    for index in range(len(points) - 1):
        lower_level, lower_raw = points[index]
        upper_level, upper_raw = points[index + 1]
        if lower_level <= value <= upper_level:
            ratio = (value - lower_level) / float(upper_level - lower_level)
            return int(round(lower_raw + (upper_raw - lower_raw) * ratio))
    raise AssertionError("volume curve must cover 0..100")


def _interpolate_curve_inverse(
    points: tuple[tuple[int, int], ...],
    value: int,
) -> int:
    if value <= points[0][1]:
        return points[0][0]
    if value >= points[-1][1]:
        return points[-1][0]
    for index in range(len(points) - 1):
        lower_level, lower_raw = points[index]
        upper_level, upper_raw = points[index + 1]
        if lower_raw <= value <= upper_raw:
            ratio = (value - lower_raw) / float(upper_raw - lower_raw)
            return int(round(lower_level + (upper_level - lower_level) * ratio))
    raise AssertionError("volume curve raw values must be increasing")


def _scale_raw_value(value: int, *, raw_min: int, raw_max: int) -> int:
    if raw_max <= raw_min:
        raise Wm8960ProfileError(
            f"Invalid playback limits for volume curve: {raw_min}..{raw_max}"
        )
    ratio = (value - _CURVE_RAW_MIN) / float(_CURVE_RAW_MAX - _CURVE_RAW_MIN)
    target = raw_min + ratio * (raw_max - raw_min)
    return max(raw_min, min(raw_max, int(round(target))))


def _unscale_raw_value(value: int, *, raw_min: int, raw_max: int) -> int:
    if raw_max <= raw_min:
        raise Wm8960ProfileError(
            f"Invalid playback limits for volume curve: {raw_min}..{raw_max}"
        )
    clamped = max(raw_min, min(raw_max, int(value)))
    ratio = (clamped - raw_min) / float(raw_max - raw_min)
    return int(round(_CURVE_RAW_MIN + ratio * (_CURVE_RAW_MAX - _CURVE_RAW_MIN)))
