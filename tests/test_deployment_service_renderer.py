from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "deploy/render_systemd_service.py"
SPEC = importlib.util.spec_from_file_location(
    "lafvin_render_systemd_service",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def test_render_checkout_backed_systemd_service(tmp_path: Path) -> None:
    source = tmp_path / "LAFVIN HAT%dev"
    venv = source / ".venv"
    template = (
        ROOT / "deploy/systemd/lafvin-hat.service"
    ).read_text(encoding="utf-8")

    rendered = renderer.render_service(
        template,
        user="pi",
        group="pi",
        source_dir=source,
        venv_dir=venv,
    )

    assert "User=pi" in rendered
    assert "Group=pi" in rendered
    assert "WorkingDirectory=" not in rendered
    assert "LAFVIN_PROJECT_ROOT=" in rendered
    assert "ExecStartPre=" not in rendered
    assert renderer.systemd_quote(str(venv.resolve() / "bin/lafvin-runtime")) in rendered
    assert "@@LAFVIN_" not in rendered


def test_render_service_rejects_invalid_account() -> None:
    with pytest.raises(ValueError, match="Invalid systemd user"):
        renderer.render_service(
            "User=@@LAFVIN_USER@@",
            user="bad user",
            group="pi",
            source_dir=ROOT,
            venv_dir=ROOT / ".venv",
        )


def test_render_service_rejects_unknown_template_token() -> None:
    with pytest.raises(ValueError, match="unknown LAFVIN token"):
        renderer.render_service(
            "Value=@@LAFVIN_UNKNOWN@@",
            user="pi",
            group="pi",
            source_dir=ROOT,
            venv_dir=ROOT / ".venv",
        )
