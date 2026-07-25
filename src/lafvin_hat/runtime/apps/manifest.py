from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from lafvin_hat.schemas import load_manifest_schema


class ManifestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Entrypoint:
    executable: str
    args: tuple[str, ...]
    working_directory: str


@dataclass(frozen=True, slots=True)
class Lifecycle:
    startup_timeout_sec: int
    exit_timeout_sec: int
    restart: str
    max_restarts: int


@dataclass(frozen=True, slots=True)
class AppManifest:
    app_id: str
    name: str
    version: str
    description: str
    entrypoint: Entrypoint
    permissions: frozenset[str]
    ui_mode: str
    lifecycle: Lifecycle
    source_path: Path

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.app_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "permissions": sorted(self.permissions),
            "ui_mode": self.ui_mode,
        }


def load_manifest(path: Path) -> AppManifest:
    manifest_path = path
    if path.is_dir():
        manifest_path = path / "manifest.yaml"
    if not manifest_path.is_file():
        raise ManifestError(f"Manifest not found: {manifest_path}")

    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ManifestError(f"Failed to read manifest: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("Manifest root must be an object")

    try:
        jsonschema.validate(raw, load_manifest_schema())
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path)
        prefix = f"{location}: " if location else ""
        raise ManifestError(f"{prefix}{exc.message}") from exc

    entrypoint = raw["entrypoint"]
    lifecycle = raw["lifecycle"]
    return AppManifest(
        app_id=raw["id"],
        name=raw["name"],
        version=raw["version"],
        description=raw.get("description", ""),
        entrypoint=Entrypoint(
            executable=entrypoint["executable"],
            args=tuple(entrypoint["args"]),
            working_directory=entrypoint.get("working_directory", "."),
        ),
        permissions=frozenset(raw["permissions"]),
        ui_mode=raw["ui"]["mode"],
        lifecycle=Lifecycle(
            startup_timeout_sec=lifecycle["startup_timeout_sec"],
            exit_timeout_sec=lifecycle["exit_timeout_sec"],
            restart=lifecycle["restart"],
            max_restarts=lifecycle["max_restarts"],
        ),
        source_path=manifest_path.parent.resolve(),
    )

