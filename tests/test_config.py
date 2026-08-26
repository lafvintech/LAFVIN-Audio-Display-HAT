import os
from pathlib import Path

import pytest

from lafvin_hat.runtime.config import (
    RuntimeEndpoint,
    load_env_file,
    parse_endpoint,
)


def test_parse_tcp_endpoint() -> None:
    endpoint = parse_endpoint("tcp://127.0.0.1:9000")

    assert endpoint == RuntimeEndpoint(kind="tcp", host="127.0.0.1", port=9000)
    assert endpoint.as_uri() == "tcp://127.0.0.1:9000"


def test_parse_unix_endpoint() -> None:
    endpoint = parse_endpoint("unix:///tmp/lafvin/runtime.sock")

    assert endpoint == RuntimeEndpoint(
        kind="unix",
        path=Path("/tmp/lafvin/runtime.sock"),
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://127.0.0.1:9000",
        "tcp://127.0.0.1",
        "unix://",
    ],
)
def test_reject_invalid_endpoint(value: str) -> None:
    with pytest.raises(ValueError):
        parse_endpoint(value)


def test_load_env_file_preserves_existing_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# local AI settings",
                "export LAFVIN_LLM_PROVIDER=openai-compatible",
                'OPENAI_API_KEY="file-secret"',
                "OPENAI_LLM_MODEL=gpt-test # comment",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "shell-secret")

    loaded = load_env_file(env_file)

    assert loaded["OPENAI_API_KEY"] == "file-secret"
    assert os.environ["OPENAI_API_KEY"] == "shell-secret"
    assert os.environ["LAFVIN_LLM_PROVIDER"] == "openai-compatible"
    assert os.environ["OPENAI_LLM_MODEL"] == "gpt-test"


def test_load_env_file_rejects_invalid_lines(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("NOT AN ASSIGNMENT", encoding="utf-8")

    with pytest.raises(ValueError, match="expected NAME=VALUE"):
        load_env_file(env_file)
