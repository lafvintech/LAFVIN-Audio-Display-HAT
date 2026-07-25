from __future__ import annotations

import argparse
import asyncio

import pytest

from lafvin_hat.runtime import main as runtime_main
from lafvin_hat.runtime.main import build_parser


def test_runtime_parser_uses_lafvin_hat_as_canonical_physical_backend() -> None:
    parser = build_parser()

    canonical = parser.parse_args(["--backend", "lafvin-hat"])
    driver = parser.parse_args(["--lafvin-hat-driver", "/tmp/driver.py"])

    assert canonical.backend == "lafvin-hat"
    assert driver.lafvin_hat_driver == "/tmp/driver.py"

    with pytest.raises(SystemExit):
        parser.parse_args(["--backend", "whisplay"])


def test_runtime_uses_lafvin_external_driver_environment(
    monkeypatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {}
    provisioned: list[object] = []

    async def fake_run(*_args, **kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setenv("LAFVIN_HAT_DRIVER", "/tmp/lafvin-driver.py")
    monkeypatch.setattr(runtime_main, "run", fake_run)
    monkeypatch.setattr(runtime_main, "configure_runtime_logging", lambda _path: None)
    monkeypatch.setattr(
        "lafvin_hat.runtime.apps.provision.provision_first_party_apps",
        provisioned.append,
    )

    asyncio.run(
        runtime_main.run_from_args(
            argparse.Namespace(
                env_file=None,
                data_dir=str(tmp_path / "data"),
                log_dir=str(tmp_path / "logs"),
                endpoint=None,
                simulator_host="127.0.0.1",
                simulator_port=17880,
                no_simulator_web=False,
                backend="lafvin-hat",
                lafvin_hat_driver=None,
            )
        )
    )

    assert captured["lafvin_hat_driver"] == "/tmp/lafvin-driver.py"
    assert provisioned == [tmp_path / "data"]
