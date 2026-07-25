import asyncio
from pathlib import Path
import tomllib

import pytest

from lafvin_hat._cli_apps import new_log_lines
from lafvin_hat import cli
from lafvin_hat.cli import build_parser
from lafvin_hat.sdk import __main__ as sdk_cli
from lafvin_hat.sdk.client import RuntimeClientError


ROOT = Path(__file__).resolve().parents[1]


def test_management_cli_parses_nested_app_commands() -> None:
    parser = build_parser()

    start = parser.parse_args(["app", "start", "dev.lafvin.chatbot"])
    run = parser.parse_args(["app", "run", "apps/chatbot", "--follow"])
    logs = parser.parse_args(["logs", "dev.lafvin.chatbot", "--lines", "20"])

    assert start.command == "app"
    assert start.app_command == "start"
    assert start.app_id == "dev.lafvin.chatbot"
    assert run.command == "app"
    assert run.app_command == "run"
    assert run.source_path == "apps/chatbot"
    assert run.follow is True
    assert logs.command == "logs"
    assert logs.lines == 20


def test_management_cli_parses_runtime_start_with_shared_options() -> None:
    parser = build_parser()

    direct = parser.parse_args(
        [
            "runtime",
            "start",
            "--env-file",
            ".env",
            "--backend",
            "lafvin-hat",
            "--endpoint",
            "tcp://127.0.0.1:8765",
        ]
    )
    inherited_endpoint = parser.parse_args(
        [
            "--endpoint",
            "tcp://127.0.0.1:8765",
            "runtime",
            "start",
        ]
    )
    sim_button = parser.parse_args(["sim", "button", "pressed"])

    assert direct.command == "runtime"
    assert direct.runtime_command == "start"
    assert direct.env_file == ".env"
    assert direct.backend == "lafvin-hat"
    assert direct.endpoint == "tcp://127.0.0.1:8765"
    assert inherited_endpoint.endpoint == "tcp://127.0.0.1:8765"
    assert sim_button.command == "sim"
    assert sim_button.sim_command == "button"
    assert sim_button.state == "pressed"


def test_management_cli_delegates_runtime_start_to_runtime_main(
    monkeypatch,
) -> None:
    captured = {}

    async def start_runtime(args):
        captured["args"] = args

    monkeypatch.setattr(cli.runtime_main, "run_from_args", start_runtime)

    cli.main(["runtime", "start", "--backend", "lafvin-hat"])

    assert captured["args"].backend == "lafvin-hat"


def test_management_cli_routes_simulator_button_to_runtime(
    monkeypatch,
) -> None:
    captured = {}

    class Client:
        def __init__(self, endpoint) -> None:
            captured["endpoint"] = endpoint

        async def request(self, method, payload):
            captured["method"] = method
            captured["payload"] = payload
            return {"ok": True}

    monkeypatch.setattr(cli, "RuntimeClient", Client)
    args = build_parser().parse_args(["sim", "button", "pressed"])

    assert asyncio.run(cli.run(args)) == {"ok": True}
    assert captured["method"] == "simulator.button.set"
    assert captured["payload"] == {"pressed": True}


def test_project_publishes_canonical_and_compatibility_cli_scripts() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = project["project"]["scripts"]

    assert scripts["lafvin-hat"] == "lafvin_hat.cli:main"
    assert scripts["lafvin"] == "lafvin_hat.cli:main"
    assert scripts["lafvin-runtime"] == "lafvin_hat.runtime.main:main"
    assert scripts["lafvin-sdk"] == "lafvin_hat.sdk.__main__:main"


def test_sdk_cli_parses_app_run_and_logs_alias() -> None:
    parser = sdk_cli.build_parser()

    run = parser.parse_args(["app-run", "apps/chatbot", "--follow"])
    logs = parser.parse_args(["logs", "dev.lafvin.chatbot", "-f"])

    assert run.command == "app-run"
    assert run.source_path == "apps/chatbot"
    assert run.follow is True
    assert logs.command == "logs"
    assert logs.follow is True


def test_log_follow_overlap_detects_new_lines() -> None:
    assert new_log_lines(["a", "b"], ["a", "b", "c"]) == ["c"]
    assert new_log_lines(["a", "b"], ["b", "c"]) == ["c"]
    assert new_log_lines(["a"], ["x"]) == ["x"]
    assert new_log_lines([], ["a"]) == ["a"]


def test_management_cli_reports_runtime_error_without_traceback(
    monkeypatch,
    capsys,
) -> None:
    async def fail(_args):
        raise RuntimeClientError("APP_NOT_FOUND", "Unknown application")

    monkeypatch.setattr(cli, "run", fail)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["app", "start", "dev.lafvin.missing"])

    captured = capsys.readouterr()
    assert exit_info.value.code == 1
    assert captured.out == ""
    assert captured.err == "error: APP_NOT_FOUND: Unknown application\n"
    assert "Traceback" not in captured.err


def test_management_cli_reports_connection_error(
    monkeypatch,
    capsys,
) -> None:
    async def fail(_args):
        raise ConnectionRefusedError("Runtime socket is unavailable")

    monkeypatch.setattr(cli, "run", fail)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["status"])

    captured = capsys.readouterr()
    assert exit_info.value.code == 1
    assert "error: RUNTIME_UNAVAILABLE:" in captured.err
    assert "Runtime socket is unavailable" in captured.err
    assert "Traceback" not in captured.err


def test_sdk_cli_uses_same_friendly_error_boundary(
    monkeypatch,
    capsys,
) -> None:
    async def fail(_args):
        raise RuntimeClientError("APP_NOT_RUNNING", "Application is stopped")

    monkeypatch.setattr(sdk_cli, "run", fail)

    with pytest.raises(SystemExit) as exit_info:
        sdk_cli.main(["app-stop", "dev.lafvin.chatbot"])

    captured = capsys.readouterr()
    assert exit_info.value.code == 1
    assert captured.err == (
        "error: APP_NOT_RUNNING: Application is stopped\n"
    )
    assert "Traceback" not in captured.err
