from pathlib import Path

import jsonschema
import pytest
import yaml

from lafvin_hat.schemas import load_manifest_schema


ROOT = Path(__file__).resolve().parents[1]
FIRST_PARTY_MANIFESTS = sorted((ROOT / "apps").glob("*/manifest.yaml"))


@pytest.mark.parametrize(
    "manifest_path",
    FIRST_PARTY_MANIFESTS,
    ids=lambda path: path.parent.name,
)
def test_first_party_manifest_matches_v1_schema(manifest_path: Path) -> None:
    manifest = yaml.safe_load(manifest_path.read_text("utf-8"))

    jsonschema.validate(manifest, load_manifest_schema())
