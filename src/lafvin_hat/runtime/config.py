from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_TCP_HOST = "127.0.0.1"
DEFAULT_TCP_PORT = 8765


def load_env_file(
    path: str | Path,
    *,
    override: bool = False,
) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.is_file():
        raise FileNotFoundError(f"Environment file not found: {env_path}")

    loaded: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        env_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(
                f"{env_path}:{line_number}: expected NAME=VALUE"
            )
        name, value = line.split("=", 1)
        name = name.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
            raise ValueError(
                f"{env_path}:{line_number}: invalid variable name"
            )
        value = _parse_env_value(value.strip(), env_path, line_number)
        loaded[name] = value
        if override or name not in os.environ:
            os.environ[name] = value
    return loaded


def _parse_env_value(value: str, path: Path, line_number: int) -> str:
    if not value:
        return ""
    if value[0] in {"'", '"'}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise ValueError(
                f"{path}:{line_number}: unterminated quoted value"
            )
        return value[1:-1]
    comment_at = value.find(" #")
    if comment_at >= 0:
        value = value[:comment_at]
    return value.rstrip()


@dataclass(frozen=True, slots=True)
class RuntimeEndpoint:
    kind: str
    path: Path | None = None
    host: str | None = None
    port: int | None = None

    def __post_init__(self) -> None:
        if self.kind == "unix":
            if self.path is None:
                raise ValueError("Unix endpoint requires a path")
            return
        if self.kind == "tcp":
            if not self.host or self.port is None:
                raise ValueError("TCP endpoint requires a host and port")
            if not 0 <= self.port <= 65535:
                raise ValueError("TCP port must be between 0 and 65535")
            return
        raise ValueError(f"Unsupported endpoint kind: {self.kind}")

    def as_uri(self) -> str:
        if self.kind == "unix":
            return f"unix://{self.path}"
        return f"tcp://{self.host}:{self.port}"


def default_runtime_endpoint() -> RuntimeEndpoint:
    configured = os.getenv("LAFVIN_RUNTIME_ENDPOINT")
    if configured:
        return parse_endpoint(configured)

    if os.name == "nt":
        return RuntimeEndpoint(
            kind="tcp",
            host=DEFAULT_TCP_HOST,
            port=DEFAULT_TCP_PORT,
        )

    system_socket = Path("/run/lafvin-hat/runtime.sock")
    if system_socket.exists():
        return RuntimeEndpoint(kind="unix", path=system_socket)

    runtime_root = os.getenv("XDG_RUNTIME_DIR")
    if runtime_root:
        socket_path = Path(runtime_root) / "lafvin-hat" / "runtime.sock"
    else:
        socket_path = Path.home() / ".cache" / "lafvin-hat" / "runtime.sock"
    return RuntimeEndpoint(kind="unix", path=socket_path)


def default_data_dir() -> Path:
    configured = os.getenv("LAFVIN_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        root = os.getenv("LOCALAPPDATA")
        return (
            Path(root) / "lafvin-hat"
            if root
            else Path.home() / "AppData" / "Local" / "lafvin-hat"
        )
    root = os.getenv("XDG_DATA_HOME")
    return (
        Path(root) / "lafvin-hat"
        if root
        else Path.home() / ".local" / "share" / "lafvin-hat"
    )


def default_log_dir() -> Path:
    configured = os.getenv("LAFVIN_LOG_DIR")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        return default_data_dir() / "logs"
    root = os.getenv("XDG_STATE_HOME")
    return (
        Path(root) / "lafvin-hat" / "logs"
        if root
        else Path.home() / ".local" / "state" / "lafvin-hat" / "logs"
    )


def parse_endpoint(value: str) -> RuntimeEndpoint:
    parsed = urlparse(value)
    if parsed.scheme == "unix":
        path_text = parsed.path
        if parsed.netloc:
            path_text = f"//{parsed.netloc}{parsed.path}"
        if not path_text:
            raise ValueError("Unix endpoint URI must contain a path")
        return RuntimeEndpoint(kind="unix", path=Path(path_text))

    if parsed.scheme == "tcp":
        if not parsed.hostname or parsed.port is None:
            raise ValueError("TCP endpoint must use tcp://host:port")
        return RuntimeEndpoint(
            kind="tcp",
            host=parsed.hostname,
            port=parsed.port,
        )

    raise ValueError("Endpoint must start with unix:// or tcp://")
