from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lafvin_hat._cli_apps import follow_app_logs, run_development_app
from lafvin_hat._cli import run_async_command
from lafvin_hat.runtime.config import default_runtime_endpoint, parse_endpoint

from .client import RuntimeClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LAFVIN HAT SDK utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("ping", "info", "status", "app-list", "device-state"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--endpoint")

    install_parser = subparsers.add_parser("app-install")
    install_parser.add_argument("source_path")
    install_parser.add_argument(
        "--dev",
        action="store_true",
        help="Register the source directory without copying it",
    )
    install_parser.add_argument("--endpoint")

    start_parser = subparsers.add_parser("app-start")
    start_parser.add_argument("app_id")
    start_parser.add_argument("--endpoint")

    stop_parser = subparsers.add_parser("app-stop")
    stop_parser.add_argument("app_id")
    stop_parser.add_argument("--endpoint")

    uninstall_parser = subparsers.add_parser("app-uninstall")
    uninstall_parser.add_argument("app_id")
    uninstall_parser.add_argument("--endpoint")

    logs_parser = subparsers.add_parser("app-logs")
    logs_parser.add_argument("app_id")
    logs_parser.add_argument("--lines", type=int, default=100)
    logs_parser.add_argument("--follow", "-f", action="store_true")
    logs_parser.add_argument("--interval", type=float, default=1.0)
    logs_parser.add_argument("--endpoint")

    logs_alias_parser = subparsers.add_parser("logs")
    logs_alias_parser.add_argument("app_id")
    logs_alias_parser.add_argument("--lines", type=int, default=100)
    logs_alias_parser.add_argument("--follow", "-f", action="store_true")
    logs_alias_parser.add_argument("--interval", type=float, default=1.0)
    logs_alias_parser.add_argument("--endpoint")

    run_parser = subparsers.add_parser("app-run")
    run_parser.add_argument("source_path")
    run_parser.add_argument("--follow", "-f", action="store_true")
    run_parser.add_argument("--lines", type=int, default=100)
    run_parser.add_argument("--interval", type=float, default=1.0)
    run_parser.add_argument("--endpoint")

    button_parser = subparsers.add_parser("sim-button")
    button_parser.add_argument("state", choices=["pressed", "released"])
    button_parser.add_argument("--endpoint")
    return parser


async def run(args: argparse.Namespace) -> dict[str, Any] | None:
    endpoint = (
        parse_endpoint(args.endpoint)
        if args.endpoint
        else default_runtime_endpoint()
    )
    client = RuntimeClient(endpoint)
    simple_methods = {
        "ping": "runtime.ping",
        "info": "runtime.info",
        "status": "runtime.status",
        "app-list": "app.list",
        "device-state": "device.get_state",
    }
    if args.command in simple_methods:
        result = await client.request(simple_methods[args.command])
    elif args.command == "app-install":
        result = await client.request(
            "app.install",
            {
                "source_path": str(Path(args.source_path).resolve()),
                "development": args.dev,
            },
        )
    elif args.command == "app-start":
        result = await client.request(
            "app.launch",
            {"app_id": args.app_id},
        )
    elif args.command == "app-stop":
        result = await client.request(
            "app.stop",
            {"app_id": args.app_id},
        )
    elif args.command == "app-uninstall":
        result = await client.request(
            "app.uninstall",
            {"app_id": args.app_id},
        )
    elif args.command in {"app-logs", "logs"}:
        if args.follow:
            await follow_app_logs(
                client,
                args.app_id,
                lines=args.lines,
                interval=args.interval,
            )
            return None
        result = await client.request(
            "app.logs",
            {"app_id": args.app_id, "lines": args.lines},
        )
    elif args.command == "app-run":
        result = await run_development_app(client, args.source_path)
        if args.follow:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            await follow_app_logs(
                client,
                result["app_id"],
                lines=args.lines,
                interval=args.interval,
            )
            return None
    elif args.command == "sim-button":
        result = await client.request(
            "simulator.button.set",
            {"pressed": args.state == "pressed"},
        )
    else:
        raise ValueError(f"Unsupported command: {args.command}")
    return result


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = run_async_command(parser, lambda: run(args))
    if result is not None:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
