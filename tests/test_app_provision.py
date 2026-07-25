import subprocess
import sys
from pathlib import Path
import shutil

import pytest

from lafvin_hat.runtime.apps.manifest import ManifestError
from lafvin_hat.runtime.apps.provision import provision_app, provision_apps


ROOT = Path(__file__).resolve().parents[1]


def test_provision_app_copies_and_upgrades_managed_app(tmp_path: Path) -> None:
    apps_dir = tmp_path / "apps"
    source = ROOT / "apps/chatbot"

    first = provision_app(source, apps_dir)
    installed = apps_dir / first.app_id

    assert first.app_id == "dev.lafvin.chatbot"
    assert (installed / "main.py").is_file()
    (installed / "stale").write_text("old", encoding="utf-8")

    second = provision_app(source, apps_dir)

    assert second.app_id == first.app_id
    assert not (installed / "stale").exists()


def test_batch_provision_validates_all_sources_before_replacing(
    tmp_path: Path,
) -> None:
    apps_dir = tmp_path / "apps"
    first_source = tmp_path / "chatbot"
    invalid_source = tmp_path / "translator"
    shutil.copytree(ROOT / "apps/chatbot", first_source)
    shutil.copytree(ROOT / "apps/translator", invalid_source)

    installed = provision_app(first_source, apps_dir)
    marker = apps_dir / installed.app_id / "old-version-marker"
    marker.write_text("preserve", encoding="utf-8")
    (invalid_source / "manifest.yaml").unlink()

    with pytest.raises(ManifestError, match="Manifest not found"):
        provision_apps((first_source, invalid_source), apps_dir)

    assert marker.read_text(encoding="utf-8") == "preserve"


def test_batch_provision_rejects_duplicate_app_ids(tmp_path: Path) -> None:
    apps_dir = tmp_path / "apps"
    source = ROOT / "apps/chatbot"

    with pytest.raises(ManifestError, match="duplicate app IDs"):
        provision_apps((source, source), apps_dir)


def test_provision_module_runs_without_runpy_warning() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lafvin_hat.runtime.apps.provision",
            "--help",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "RuntimeWarning" not in result.stderr
