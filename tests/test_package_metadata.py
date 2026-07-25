from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path

from lafvin_hat import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_version_matches_project_metadata() -> None:
    source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    metadata = tomllib.loads(source)

    assert metadata["project"]["name"] == "lafvin-hat"
    assert metadata["project"]["version"] == __version__
    assert metadata["project"]["license"] == {"file": "LICENSE"}
    assert "License :: OSI Approved :: Apache Software License" in metadata[
        "project"
    ]["classifiers"]


def test_root_release_files_are_present() -> None:
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").lstrip("\r\n").startswith(
        "                                 Apache License\n"
    )
    assert "LAFVIN Audio Display HAT" in (ROOT / "NOTICE").read_text(
        encoding="utf-8"
    )


def test_declared_test_media_checksums_match_files() -> None:
    notices = (ROOT / "docs" / "THIRD_PARTY_NOTICES.md").read_text(
        encoding="utf-8"
    )
    media_section = notices.split("## Project-Created Test Media", maxsplit=1)[1]
    row_pattern = re.compile(
        r"^\| `(?P<path>assets/(?:audio|videos)/[^`]+)` \| [^|]+ \| "
        r"`(?P<sha256>[0-9A-F]{64})` \|$",
        re.MULTILINE,
    )
    declared = {
        match.group("path"): match.group("sha256")
        for match in row_pattern.finditer(media_section)
    }

    assert set(declared) == {
        "assets/audio/audio_test.wav",
        "assets/videos/test.mp4",
    }
    for relative_path, expected_sha256 in declared.items():
        actual_sha256 = hashlib.sha256(
            (ROOT / relative_path).read_bytes()
        ).hexdigest()
        assert actual_sha256.upper() == expected_sha256
