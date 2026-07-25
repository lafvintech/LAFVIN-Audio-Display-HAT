from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import shutil
import uuid

from .catalog import (
    bundled_app_sources,
    default_project_root,
    load_app_catalog,
)
from .manifest import AppManifest, ManifestError, load_manifest


@dataclass(slots=True)
class _StagedApp:
    manifest: AppManifest
    staging: Path
    target: Path
    backup: Path
    activated: bool = False


def provision_app(source_path: Path, apps_dir: Path) -> AppManifest:
    return provision_apps((source_path,), apps_dir)[0]


def provision_apps(
    source_paths: Sequence[Path],
    apps_dir: Path,
) -> tuple[AppManifest, ...]:
    source_manifests = tuple(load_manifest(path) for path in source_paths)
    app_ids = [manifest.app_id for manifest in source_manifests]
    if len(app_ids) != len(set(app_ids)):
        raise ManifestError("Provisioning sources contain duplicate app IDs")

    apps_dir.mkdir(parents=True, exist_ok=True)
    staged: list[_StagedApp] = []

    try:
        for source_manifest in source_manifests:
            app_id = source_manifest.app_id
            item = _StagedApp(
                manifest=source_manifest,
                staging=apps_dir / f".{app_id}.{uuid.uuid4().hex}.tmp",
                target=apps_dir / app_id,
                backup=apps_dir / f".{app_id}.{uuid.uuid4().hex}.bak",
            )
            staged.append(item)
            shutil.copytree(
                source_manifest.source_path,
                item.staging,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".runtime",
                    "__pycache__",
                    "*.pyc",
                ),
            )
            staged_manifest = load_manifest(item.staging)
            if staged_manifest.app_id != app_id:
                raise ManifestError("Installed manifest ID changed during copy")

        for item in staged:
            if item.target.exists():
                item.target.replace(item.backup)
            item.staging.replace(item.target)
            item.activated = True
    except Exception:
        for item in reversed(staged):
            if item.activated and item.target.exists():
                shutil.rmtree(item.target)
            if item.backup.exists():
                item.backup.replace(item.target)
            if item.staging.exists():
                shutil.rmtree(item.staging)
        raise

    for item in staged:
        if item.backup.exists():
            shutil.rmtree(item.backup)
    return tuple(load_manifest(item.target) for item in staged)


def provision_catalog(
    catalog_path: Path,
    *,
    project_root: Path,
    apps_dir: Path,
) -> tuple[AppManifest, ...]:
    apps = load_app_catalog(catalog_path, project_root=project_root)
    return provision_apps(
        bundled_app_sources(apps, project_root=project_root),
        apps_dir,
    )


def provision_first_party_apps(
    data_dir: Path,
    *,
    project_root: Path | None = None,
) -> tuple[AppManifest, ...]:
    """Refresh bundled Apps for one Runtime data directory."""

    root = (
        project_root.resolve()
        if project_root is not None
        else default_project_root()
    )
    return provision_catalog(
        root / "apps" / "catalog.yaml",
        project_root=root,
        apps_dir=data_dir.resolve() / "apps",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision trusted applications into a Runtime data directory"
    )
    parser.add_argument("--data-dir", required=True)
    parser.add_argument(
        "--catalog",
        type=Path,
        help="Provision every bundled first-party App from this catalog",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        help="Checkout root used to resolve catalog sources",
    )
    parser.add_argument("source_paths", nargs="*")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    apps_dir = Path(args.data_dir).resolve() / "apps"
    if args.catalog is not None:
        if args.source_paths:
            parser.error("source_paths cannot be used with --catalog")
        project_root = (
            args.project_root.resolve()
            if args.project_root is not None
            else args.catalog.resolve().parent.parent
        )
        manifests = provision_catalog(
            args.catalog,
            project_root=project_root,
            apps_dir=apps_dir,
        )
    else:
        if not args.source_paths:
            parser.error("provide source_paths or --catalog")
        manifests = provision_apps(
            tuple(Path(path) for path in args.source_paths),
            apps_dir,
        )
    for manifest in manifests:
        print(f"Provisioned {manifest.app_id} {manifest.version}")


if __name__ == "__main__":
    main()
