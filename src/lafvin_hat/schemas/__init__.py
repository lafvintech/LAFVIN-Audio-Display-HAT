from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


def load_schema(name: str) -> dict[str, Any]:
    schema_path = files(__package__).joinpath(name)
    return json.loads(schema_path.read_text(encoding="utf-8"))


def load_manifest_schema() -> dict[str, Any]:
    return load_schema("app-manifest-v1.schema.json")


def load_protocol_schema() -> dict[str, Any]:
    return load_schema("protocol-v1.schema.json")


def load_app_catalog_schema() -> dict[str, Any]:
    return load_schema("app-catalog-v1.schema.json")


def load_ui_view_schema() -> dict[str, Any]:
    return load_schema("ui-view-v1.schema.json")
