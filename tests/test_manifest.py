from pathlib import Path

import pytest

from lafvin_hat.runtime.apps import ManifestError, load_manifest


ROOT = Path(__file__).resolve().parents[1]


def test_load_raw_frame_game_manifest() -> None:
    manifest = load_manifest(ROOT / "apps" / "one_button_jump")

    assert manifest.app_id == "dev.lafvin.jump"
    assert manifest.ui_mode == "raw_frame"
    assert "display.raw_frame" in manifest.permissions


def test_load_video_player_manifest() -> None:
    manifest = load_manifest(ROOT / "apps" / "video_player")

    assert manifest.app_id == "dev.lafvin.video-player"
    assert manifest.ui_mode == "raw_frame"
    assert "display.raw_frame" in manifest.permissions
    assert "button" in manifest.permissions


def test_load_system_status_manifest() -> None:
    manifest = load_manifest(ROOT / "apps" / "system_status")

    assert manifest.app_id == "dev.lafvin.system-status"
    assert manifest.ui_mode == "raw_frame"
    assert "display.raw_frame" in manifest.permissions
    assert "button" in manifest.permissions


def test_load_system_volume_manifest() -> None:
    manifest = load_manifest(ROOT / "apps" / "system_volume")

    assert manifest.app_id == "dev.lafvin.system-volume"
    assert manifest.ui_mode == "raw_frame"
    assert "display.raw_frame" in manifest.permissions
    assert "button" in manifest.permissions
    assert "speaker" in manifest.permissions


@pytest.mark.parametrize(
    ("directory", "app_id"),
    [
        ("chatbot", "dev.lafvin.chatbot"),
        ("translator", "dev.lafvin.translator"),
    ],
)
def test_load_m5_ai_app_manifests(
    directory: str,
    app_id: str,
) -> None:
    manifest = load_manifest(ROOT / "apps" / directory)

    assert manifest.app_id == app_id
    assert manifest.ui_mode == "raw_frame"
    assert "display.raw_frame" in manifest.permissions
    assert {
        "button",
        "microphone",
        "speaker",
        "network",
        "ai",
    } <= manifest.permissions


def test_manifest_directory_requires_manifest_yaml(tmp_path: Path) -> None:
    with pytest.raises(ManifestError):
        load_manifest(tmp_path)
