from pathlib import Path

import pytest
import yaml

from lafvin_hat.runtime.apps.catalog import (
    AppCatalogError,
    bundled_app_sources,
    load_app_catalog,
)
from lafvin_hat.runtime.apps.provision import (
    provision_catalog,
    provision_first_party_apps,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "apps/catalog.yaml"


def test_first_party_catalog_matches_sources_and_home_order() -> None:
    apps = load_app_catalog(CATALOG, project_root=ROOT)

    assert [app.app_id for app in apps] == [
        "dev.lafvin.hardware-test",
        "dev.lafvin.system-status",
        "dev.lafvin.system-volume",
        "dev.lafvin.chatbot",
        "dev.lafvin.translator",
        "dev.lafvin.jump",
        "dev.lafvin.video-player",
        "dev.lafvin.rgb-led",
    ]
    assert apps[0].provisioning == "runtime-hosted"
    assert all(app.provisioning == "bundled" for app in apps[1:])


def test_catalog_bundled_apps_are_provisioned_from_catalog(tmp_path: Path) -> None:
    apps = load_app_catalog(CATALOG, project_root=ROOT)
    manifests = provision_catalog(
        CATALOG,
        project_root=ROOT,
        apps_dir=tmp_path / "apps",
    )

    assert [manifest.app_id for manifest in manifests] == [
        app.app_id for app in apps if app.provisioning == "bundled"
    ]
    assert all((tmp_path / "apps" / manifest.app_id).is_dir() for manifest in manifests)


def test_runtime_first_party_provisioning_targets_runtime_data_dir(
    tmp_path: Path,
) -> None:
    manifests = provision_first_party_apps(tmp_path, project_root=ROOT)

    assert len(manifests) == 7
    assert all(
        (tmp_path / "apps" / manifest.app_id / "manifest.yaml").is_file()
        for manifest in manifests
    )


def test_catalog_bundled_sources_use_current_game_directory() -> None:
    apps = load_app_catalog(CATALOG, project_root=ROOT)

    assert [
        source.relative_to(ROOT).as_posix()
        for source in bundled_app_sources(apps, project_root=ROOT)
    ] == [
        "apps/system_status",
        "apps/system_volume",
        "apps/chatbot",
        "apps/translator",
        "apps/one_button_jump",
        "apps/video_player",
        "apps/rgb_led",
    ]
    dino_runner = next(app for app in apps if app.app_id == "dev.lafvin.jump")
    assert dino_runner.name == "Dino Runner"
    assert dino_runner.implementation == "toolkit"


def test_catalog_rejects_duplicate_home_order(tmp_path: Path) -> None:
    raw = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    raw["apps"][1]["home_order"] = raw["apps"][0]["home_order"]
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(AppCatalogError, match="Duplicate Home order"):
        load_app_catalog(catalog, project_root=ROOT)


def test_catalog_rejects_manifest_identity_drift(tmp_path: Path) -> None:
    raw = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    raw["apps"][1]["name"] = "Status Drift"
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(AppCatalogError, match="does not match manifest name"):
        load_app_catalog(catalog, project_root=ROOT)
