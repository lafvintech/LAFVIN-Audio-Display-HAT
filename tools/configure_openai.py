#!/usr/bin/env python3
"""Configure the deployed LAFVIN HAT without installing any dependencies.

Defaults match .env.example and src/lafvin_hat/ai/config.py on main at c97f0c2.
This tool writes configuration; it does not make or bill any OpenAI API calls.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Sequence


RUNTIME_ENV = Path("/etc/lafvin-hat/runtime.env")
DEPLOYMENT_METADATA = Path("/etc/lafvin-hat/deployment.env")
SERVICE = "lafvin-hat.service"
DEFAULT_MODELS = {
    "OPENAI_ASR_MODEL": "whisper-1",
    "OPENAI_LLM_MODEL": "gpt-4o-mini",
    "OPENAI_TTS_MODEL": "tts-1",
    "OPENAI_TTS_VOICE": "alloy",
}
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


class SetupError(Exception):
    """An actionable error whose message never contains an API key."""


@dataclass(frozen=True)
class EnvironmentFile:
    path: Path
    original: bytes
    metadata: os.stat_result
    project: bool = False

    @property
    def text(self) -> str:
        try:
            return self.original.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise SetupError(f"Configuration is not valid UTF-8 text: {self.path}") from None


def parse_environment(text: str) -> dict[str, str]:
    """Use the same single-line NAME=VALUE syntax as the product loader."""
    result = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = ASSIGNMENT.match(line)
        if match is None:
            raise SetupError(f"Invalid NAME=VALUE syntax on configuration line {number}.")
        value = line[match.end():].strip()
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise SetupError(f"Unterminated quote on configuration line {number}.")
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        result[match[1]] = value
    return result


def update_environment(text: str, settings: dict[str, str]) -> str:
    """Replace active assignments, remove duplicates, and preserve other lines."""
    parse_environment(text)
    newline = "\r\n" if "\r\n" in text else "\n"
    result = []
    seen = set()
    for line in text.splitlines(keepends=True):
        match = ASSIGNMENT.match(line)
        if match is not None and match[1] in settings:
            name = match[1]
            if name not in seen:
                result.append(f"{name}={settings[name]}{newline}")
                seen.add(name)
        else:
            result.append(line)
    missing = [name for name in settings if name not in seen]
    if missing:
        if result and not result[-1].endswith(("\n", "\r")):
            result.append(newline)
        if result and result[-1].strip():
            result.append(newline)
        result.extend(f"{name}={settings[name]}{newline}" for name in missing)
    updated = "".join(result)
    values = parse_environment(updated)
    if any(values.get(name) != value for name, value in settings.items()):
        raise SetupError("Generated configuration failed validation; no files were written.")
    return updated


def read_environment(path: Path, *, project: bool = False) -> EnvironmentFile:
    path = path.expanduser().absolute()
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise SetupError(f"Configuration must be a regular file, not a symbolic or hard link: {path}")
        snapshot = EnvironmentFile(path, path.read_bytes(), info, project)
    except OSError:
        raise SetupError(f"Cannot read configuration; check the file and its permissions: {path}") from None
    parse_environment(snapshot.text)
    return snapshot


def require_root() -> None:
    if sys.platform != "linux" or not hasattr(os, "geteuid"):
        raise SetupError("Run configuration on the Raspberry Pi's Linux system; use --dry-run elsewhere.")
    if os.geteuid() != 0:
        raise SetupError("Run this tool with sudo python3 configure_openai.py.")


def mask_api_key(key: str) -> str:
    """Show five characters at each end without exposing a short credential."""
    if len(key) <= 10:
        return "*" * len(key)
    return f"{key[:5]}********{key[-5:]}"


def mask_key_entry(key: str) -> str:
    """Keep the prefix visible; reveal the rolling suffix once it cannot overlap."""
    if len(key) <= 10:
        return key[:5] + "*" * max(0, len(key) - 5)
    return mask_api_key(key)


def _read_masked_key() -> str:
    """Read one terminal line with OS echo disabled and a masked live preview."""
    try:
        import termios
    except ImportError:
        raise SetupError("Masked key entry requires a Linux SSH terminal on the Raspberry Pi.") from None

    stream = sys.stderr
    if not sys.stdin.isatty() or not stream.isatty():
        raise SetupError("An interactive terminal is required. Download the script first; do not pipe it into Python.")
    try:
        fd = sys.stdin.fileno()
        original = termios.tcgetattr(fd)
    except (OSError, ValueError, termios.error):
        raise SetupError("Cannot control terminal echo. Run the tool in an interactive SSH terminal.") from None
    modified = original[:]
    modified[6] = original[6][:]
    modified[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON)
    modified[6][termios.VMIN] = 1
    modified[6][termios.VTIME] = 0
    prompt = "Enter your OpenAI API key: "
    key = ""
    escape = None
    try:
        termios.tcsetattr(fd, termios.TCSANOW, modified)
        stream.write(prompt)
        stream.flush()
        while True:
            raw = os.read(fd, 1)
            if not raw or raw == b"\x04":
                raise EOFError
            if raw == b"\x03":
                raise KeyboardInterrupt
            # Ignore terminal sequences (arrows, Home, bracketed-paste markers).
            if escape is not None:
                if escape == b"" and raw in (b"[", b"O"):
                    escape = raw
                elif escape == b"" or b"@" <= raw <= b"~":
                    escape = None
                continue
            if raw == b"\x1b":
                escape = b""
                continue
            if raw in (b"\r", b"\n"):
                return key
            if raw in (b"\x08", b"\x7f"):
                key = key[:-1]
            elif raw == b"\x15":  # Ctrl+U clears the entry.
                key = ""
            elif b" " <= raw <= b"~":
                key += raw.decode("ascii")
            else:
                continue
            stream.write("\r\x1b[2K" + prompt + mask_key_entry(key))
            stream.flush()
    except (OSError, termios.error):
        raise SetupError("Masked key entry failed. Run the tool in an interactive SSH terminal.") from None
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSAFLUSH, original)
        except (OSError, termios.error):
            raise SetupError("Could not restore terminal settings. Reconnect the SSH session before retrying.") from None
        finally:
            stream.write("\n")
            stream.flush()


def read_api_key() -> str:
    key = _read_masked_key().strip()
    if re.fullmatch(r"sk-[A-Za-z0-9_-]{16,}", key) is None:
        raise SetupError("Invalid API key format. Enter a complete OpenAI key without whitespace.")
    return key


def find_project_env() -> Path | None:
    """Read the installer's shell-escaped source path without executing it."""
    try:
        lines = DEPLOYMENT_METADATA.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        lines = []
    source = None
    for line in lines:
        match = ASSIGNMENT.match(line)
        if match is None or match[1] != "LAFVIN_SOURCE_DIR":
            continue
        source = None
        try:
            values = shlex.split(line[match.end():], comments=True, posix=True)
        except ValueError:
            continue
        if len(values) == 1 and Path(values[0]).is_absolute():
            source = Path(values[0]) / ".env"
    if source is not None:
        return source if source.is_file() else None
    # A locally run copy can also reside in the source checkout's tools folder.
    for directory in (Path.cwd(), Path(__file__).absolute().parent.parent):
        if (directory / "pyproject.toml").is_file() and (directory / ".env.example").is_file():
            candidate = directory / ".env"
            if candidate.is_file():
                return candidate.absolute()
    return None


def choose_project_env() -> Path | None:
    candidate = find_project_env()
    if candidate is not None:
        print(f"Project environment file: {candidate}")
    else:
        print("No existing project .env was found automatically.")
    print("Syncing also configures manual development/testing runs. Other settings are preserved.")
    while True:
        answer = input("Also update the project's .env? [y/N]: ").strip().lower()
        if answer in {"", "n", "no"}:
            return None
        if answer in {"y", "yes"}:
            break
        print("Please enter y or n.")
    if candidate is not None:
        return candidate
    value = input("Full path to the existing project .env (Enter to skip): ").strip()
    return Path(value) if value else None


def add_project_env(files: list[EnvironmentFile], path: Path) -> None:
    if path.name != ".env":
        raise SetupError("The project file must be named .env; templates such as .env.example are not allowed.")
    project = read_environment(path, project=True)
    if files[0].path == project.path or (
        files[0].metadata.st_dev == project.metadata.st_dev
        and files[0].metadata.st_ino == project.metadata.st_ino
    ):
        raise SetupError("The service configuration and project .env must be separate files.")
    files.append(project)


def _systemctl(*arguments: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["systemctl", *arguments, SERVICE],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SetupError("Cannot run systemctl, or the service operation timed out.") from None


class RuntimeService:
    def __init__(self) -> None:
        loaded = _systemctl("show", "--property=LoadState", "--value")
        if loaded.returncode or loaded.stdout.strip() != "loaded":
            raise SetupError("lafvin-hat.service is not installed. Complete the device deployment first.")
        self.was_active = _systemctl("is-active", "--quiet").returncode == 0

    def restart(self) -> None:
        if _systemctl("restart").returncode:
            raise SetupError("The HAT service failed to restart.")
        # Also catch an immediate exit followed by systemd's automatic restart.
        for attempt in range(3):
            if attempt:
                time.sleep(1)
            if _systemctl("is-active", "--quiet").returncode:
                raise SetupError("The HAT service did not remain active.")

    def restore(self) -> None:
        if self.was_active:
            self.restart()
        elif _systemctl("stop").returncode:
            raise SetupError("Configuration was restored, but the previous service state could not be restored.")


def _write_atomic(snapshot: EnvironmentFile, content: bytes, mode: int) -> None:
    """Set ownership and permissions before making the replacement visible."""
    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix=f".{snapshot.path.name}.", dir=snapshot.path.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as stream:
            if hasattr(os, "fchown"):
                os.fchown(stream.fileno(), snapshot.metadata.st_uid, snapshot.metadata.st_gid)
            if hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, snapshot.path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def configure(
    files: Sequence[EnvironmentFile],
    settings: dict[str, str],
    *,
    service: RuntimeService | None,
) -> None:
    """Hold originals in memory for rollback; do not create backup files."""
    changes = [(item, update_environment(item.text, settings).encode("utf-8")) for item in files]
    changed = []
    service_touched = False
    try:
        for item, content in changes:
            current = read_environment(item.path)
            if (
                current.original != item.original
                or current.metadata.st_ino != item.metadata.st_ino
                or current.metadata.st_dev != item.metadata.st_dev
            ):
                raise SetupError(f"Configuration changed during setup. Run the tool again: {item.path}")
            limit = 0o600 if item.project else 0o640
            mode = stat.S_IMODE(item.metadata.st_mode) & limit
            _write_atomic(item, content, mode)
            changed.append(item)
        if service is not None:
            service_touched = True
            service.restart()
    except (OSError, SetupError, KeyboardInterrupt) as failure:
        if isinstance(failure, SetupError):
            reason = str(failure)
        elif isinstance(failure, KeyboardInterrupt):
            reason = "Operation cancelled."
        else:
            reason = "Could not write configuration. Check paths, permissions, and free disk space."
        restore_failed = False
        for item in reversed(changed):
            try:
                _write_atomic(item, item.original, stat.S_IMODE(item.metadata.st_mode))
            except OSError:
                restore_failed = True
        if service_touched and not restore_failed:
            try:
                service.restore()
            except (OSError, SetupError):
                restore_failed = True
        if restore_failed:
            paths = ", ".join(str(item.path) for item in changed)
            raise SetupError(f"{reason} Recovery was incomplete. Check the service and these files manually: {paths}") from None
        raise SetupError(f"{reason} Modified files and the previous service state were restored.") from None


def _model(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:-]+", value) is None:
        raise argparse.ArgumentTypeError("Model and voice names cannot be empty or contain whitespace or quotes.")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Switch a deployed LAFVIN HAT from demo mode to OpenAI.")
    parser.add_argument("--env-file", type=Path, default=RUNTIME_ENV, help="service configuration file")
    sync = parser.add_mutually_exclusive_group()
    sync.add_argument("--project-env", type=Path, help="also update this existing project .env without asking")
    sync.add_argument("--no-project-sync", action="store_true", help="skip the project .env sync question")
    parser.add_argument("--dry-run", action="store_true", help="preview without reading a key, writing files, or restarting")
    parser.add_argument("--no-restart", action="store_true", help="save configuration without restarting, for debugging")
    parser.add_argument("--asr-model", type=_model, default=DEFAULT_MODELS["OPENAI_ASR_MODEL"])
    parser.add_argument("--llm-model", type=_model, default=DEFAULT_MODELS["OPENAI_LLM_MODEL"])
    parser.add_argument("--tts-model", type=_model, default=DEFAULT_MODELS["OPENAI_TTS_MODEL"])
    parser.add_argument("--voice", type=_model, default=DEFAULT_MODELS["OPENAI_TTS_VOICE"])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.dry_run:
            require_root()
        files = [read_environment(args.env_file)]
        if args.project_env is not None:
            add_project_env(files, args.project_env)
        settings = {
            "LAFVIN_ASR_PROVIDER": "openai",
            "LAFVIN_LLM_PROVIDER": "openai",
            "LAFVIN_TTS_PROVIDER": "openai",
            "OPENAI_API_KEY": "<hidden until entry>",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
            "OPENAI_ASR_MODEL": args.asr_model,
            "OPENAI_LLM_MODEL": args.llm_model,
            "OPENAI_TTS_MODEL": args.tts_model,
            "OPENAI_TTS_VOICE": args.voice,
        }
        print("Configuration files to update:")
        for item in files:
            print(f"  {item.path}")
        for name, value in settings.items():
            print(f"  {name}={value}")
        if args.dry_run:
            if args.project_env is None and not args.no_project_sync:
                print("Project .env sync will be offered after API key entry during a normal run.")
            print("Preview only: no API key was read, no files were written, and no service was changed.")
            return 0
        service = None if args.no_restart else RuntimeService()
        settings["OPENAI_API_KEY"] = read_api_key()
        print(f"API key: {mask_api_key(settings['OPENAI_API_KEY'])}")
        if args.project_env is None and not args.no_project_sync:
            project = choose_project_env()
            if project is not None:
                add_project_env(files, project)
                print(f"Project .env will also be updated: {files[-1].path}")
            else:
                print("Project .env left unchanged.")
        configure(files, settings, service=service)
        if args.no_restart:
            print("Configuration saved. Run sudo systemctl restart lafvin-hat when ready.")
        else:
            print("Configuration saved. The HAT service was restarted and is active.")
        print("Try a real Chatbot conversation to verify the network, API key, and account credit.")
        return 0
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled.", file=sys.stderr)
        return 130
    except (SetupError, OSError) as exc:
        message = str(exc) if isinstance(exc, SetupError) else "File operation failed. Check paths and permissions."
        print(f"Error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
