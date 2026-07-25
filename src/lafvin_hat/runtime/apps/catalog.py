from __future__ import annotations

import argparse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from lafvin_hat.schemas import load_app_catalog_schema

from .manifest import ManifestError, load_manifest


class AppCatalogError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FirstPartyApp:
    app_id: str
    name: str
    source: str
    provisioning: str
    home_order: int
    implementation: str


def default_project_root() -> Path:
    """Return the checkout that owns the first-party application catalog."""

    configured_root = os.getenv("LAFVIN_PROJECT_ROOT")
    if configured_root:
        return Path(configured_root).expanduser().resolve()
    # catalog.py -> apps -> runtime -> lafvin_hat -> src -> checkout root
    return Path(__file__).resolve().parents[4]


def load_first_party_app_catalog(
    project_root: Path | None = None,
) -> tuple[FirstPartyApp, ...]:
    root = project_root.resolve() if project_root else default_project_root()
    return load_app_catalog(root / "apps" / "catalog.yaml", project_root=root)


def bundled_app_sources(
    apps: Sequence[FirstPartyApp],
    *,
    project_root: Path,
) -> tuple[Path, ...]:
    root = project_root.resolve()
    return tuple(
        (root / app.source).resolve()
        for app in apps
        if app.provisioning == "bundled"
    )


def load_app_catalog(
    path: Path,
    *,
    project_root: Path | None = None,
) -> tuple[FirstPartyApp, ...]:
    catalog_path = path.resolve()
    root = project_root.resolve() if project_root else catalog_path.parent.parent

    try:
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AppCatalogError(f"Failed to read app catalog: {exc}") from exc

    if not isinstance(raw, dict):
        raise AppCatalogError("App catalog root must be an object")

    try:
        jsonschema.validate(raw, load_app_catalog_schema())
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path)
        prefix = f"{location}: " if location else ""
        raise AppCatalogError(f"{prefix}{exc.message}") from exc

    apps = tuple(_parse_entry(item) for item in raw["apps"])
    _validate_unique((app.app_id for app in apps), "application id")
    _validate_unique((app.home_order for app in apps), "Home order")
    _validate_sources(apps, root)
    return tuple(sorted(apps, key=lambda app: app.home_order))


def _parse_entry(raw: dict[str, Any]) -> FirstPartyApp:
    return FirstPartyApp(
        app_id=raw["id"],
        name=raw["name"],
        source=raw["source"],
        provisioning=raw["provisioning"],
        home_order=raw["home_order"],
        implementation=raw["implementation"],
    )


def _validate_unique(values: Iterable[object], label: str) -> None:
    seen: set[object] = set()
    for value in values:
        if value in seen:
            raise AppCatalogError(f"Duplicate {label}: {value}")
        seen.add(value)


def _validate_sources(apps: tuple[FirstPartyApp, ...], root: Path) -> None:
    for app in apps:
        source_path = root / app.source
        if app.provisioning == "runtime-hosted":
            if app.implementation != "runtime-system":
                raise AppCatalogError(
                    f"Runtime-hosted app must use runtime-system: {app.app_id}"
                )
            if not source_path.is_file():
                raise AppCatalogError(
                    f"Runtime-hosted source not found: {app.source}"
                )
            continue

        if app.implementation == "runtime-system":
            raise AppCatalogError(
                f"Bundled app cannot use runtime-system: {app.app_id}"
            )
        try:
            manifest = load_manifest(source_path)
        except ManifestError as exc:
            raise AppCatalogError(
                f"Invalid bundled source {app.source}: {exc}"
            ) from exc
        if manifest.app_id != app.app_id:
            raise AppCatalogError(
                f"Catalog id {app.app_id} does not match manifest id "
                f"{manifest.app_id}"
            )
        if manifest.name != app.name:
            raise AppCatalogError(
                f"Catalog name {app.name!r} does not match manifest name "
                f"{manifest.name!r}"
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the first-party LAFVIN HAT app catalog."
    )
    parser.add_argument(
        "catalog",
        nargs="?",
        type=Path,
        default=Path("apps/catalog.yaml"),
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        apps = load_app_catalog(args.catalog, project_root=args.project_root)
    except AppCatalogError as exc:
        print(f"error: {exc}")
        return 1

    print(f"Validated {len(apps)} first-party applications:")
    for app in apps:
        print(
            f"  {app.home_order}: {app.app_id} "
            f"[{app.provisioning}/{app.implementation}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
