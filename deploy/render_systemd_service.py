from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence


_ACCOUNT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


def systemd_quote(value: str) -> str:
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError("systemd values cannot contain control line breaks")
    escaped = value.replace("%", "%%").replace("\\", "\\\\")
    escaped = escaped.replace('"', '\\"')
    return f'"{escaped}"'


def render_service(
    template: str,
    *,
    user: str,
    group: str,
    source_dir: Path,
    venv_dir: Path,
) -> str:
    for label, value in (("user", user), ("group", group)):
        if not _ACCOUNT_PATTERN.fullmatch(value):
            raise ValueError(f"Invalid systemd {label}: {value!r}")
    source_dir = source_dir.resolve()
    venv_dir = venv_dir.resolve()
    if not source_dir.is_absolute() or not venv_dir.is_absolute():
        raise ValueError("Deployment paths must be absolute")

    replacements = {
        "@@LAFVIN_USER@@": user,
        "@@LAFVIN_GROUP@@": group,
        "@@LAFVIN_PROJECT_ENV@@": systemd_quote(
            f"LAFVIN_PROJECT_ROOT={source_dir}"
        ),
        "@@LAFVIN_RUNTIME@@": systemd_quote(
            str(venv_dir / "bin/lafvin-runtime")
        ),
    }
    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    if "@@LAFVIN_" in rendered:
        raise ValueError("Systemd template contains an unknown LAFVIN token")
    return rendered


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a checkout-backed LAFVIN HAT systemd service."
    )
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--venv-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    rendered = render_service(
        args.template.read_text(encoding="utf-8"),
        user=args.user,
        group=args.group,
        source_dir=args.source_dir,
        venv_dir=args.venv_dir,
    )
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
