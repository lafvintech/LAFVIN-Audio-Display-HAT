from pathlib import Path

import pytest

from lafvin_hat.hardware.audio import Wm8960AudioProfile, Wm8960ProfileError


def test_wm8960_profile_detects_card_and_builds_commands(tmp_path: Path) -> None:
    cards = tmp_path / "cards"
    cards.write_text(
        """
 0 [vc4hdmi0      ]: vc4-hdmi - vc4-hdmi-0
                      vc4-hdmi-0
 2 [wm8960soundcard]: simple-card - sound
                      wm8960-soundcard
""",
        encoding="utf-8",
    )
    profile = Wm8960AudioProfile()

    card = profile.find_card(cards)

    assert card == "2"
    assert profile.capture_device(card) == "hw:2,0"
    assert profile.playback_device(card) == "plughw:2,0"
    assert profile.recording_format == "S32_LE/16000Hz/2ch"
    assert profile.recording_command(
        "hw:2,0",
        tmp_path / "recording.wav",
        max_duration_sec=3,
    ) == (
        "arecord",
        "-D",
        "hw:2,0",
        "-f",
        "S32_LE",
        "-r",
        "16000",
        "-c",
        "2",
        "-t",
        "wav",
        "-d",
        "3",
        str(tmp_path / "recording.wav"),
    )
    assert profile.volume_command(card, 70) == (
        "amixer",
        "-c",
        "2",
        "sset",
        "Speaker",
        "117",
    )


@pytest.mark.parametrize(
    ("logical_volume", "raw_value"),
    [
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
    ],
)
def test_wm8960_profile_uses_measured_lafvin_volume_curve(
    logical_volume: int,
    raw_value: int,
) -> None:
    profile = Wm8960AudioProfile()

    assert profile.logical_volume_to_raw(logical_volume) == raw_value
    assert (
        profile.raw_to_logical_volume(
            raw_value,
            raw_min=0,
            raw_max=127,
        )
        == logical_volume
    )


def test_wm8960_profile_interpolates_between_lafvin_curve_points() -> None:
    profile = Wm8960AudioProfile()

    assert profile.logical_volume_to_raw(15) == 103
    assert profile.raw_to_logical_volume(103, raw_min=0, raw_max=127) == 15


def test_wm8960_profile_missing_card_has_recovery_command(tmp_path: Path) -> None:
    cards = tmp_path / "cards"
    cards.write_text(" 0 [vc4hdmi0]: vc4-hdmi - vc4-hdmi-0\n", encoding="utf-8")

    with pytest.raises(Wm8960ProfileError, match="install_driver.sh --check"):
        Wm8960AudioProfile().find_card(cards)


def test_wm8960_profile_snapshot_is_runtime_facing() -> None:
    profile = Wm8960AudioProfile()

    assert profile.snapshot(
        card="wm8960soundcard",
        capture_device="hw:wm8960soundcard,0",
        playback_device="plughw:wm8960soundcard,0",
    ) == {
        "name": "lafvin-hat-wm8960",
        "version": "2",
        "license": "GPL-3.0",
        "resource_sha256": "8f2aaea499200843ecc4dc506bec615cab5c1f527d1e72501d2157c28369c80e",
        "card": "wm8960soundcard",
        "capture_device": "hw:wm8960soundcard,0",
        "playback_device": "plughw:wm8960soundcard,0",
        "recording_format": "S32_LE/16000Hz/2ch",
        "mixer_control": "Speaker",
        "volume_curve": "lafvin-wm8960-v1",
    }
