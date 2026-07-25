from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from lafvin_hat._cli_apps import (
    follow_app_logs,
    run_development_app,
)
from lafvin_hat._cli import run_async_command
from lafvin_hat.runtime import main as runtime_main
from lafvin_hat.runtime.config import default_runtime_endpoint, parse_endpoint
from lafvin_hat.sdk.client import RuntimeClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LAFVIN HAT management CLI")
    parser.add_argument("--endpoint")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("info")

    runtime = commands.add_parser("runtime")
    runtime_commands = runtime.add_subparsers(
        dest="runtime_command",
        required=True,
    )
    runtime_start = runtime_commands.add_parser("start")
    runtime_main.add_arguments(
        runtime_start,
        endpoint_default=argparse.SUPPRESS,
    )

    simulator = commands.add_parser("sim")
    simulator_commands = simulator.add_subparsers(
        dest="sim_command",
        required=True,
    )
    sim_button = simulator_commands.add_parser("button")
    sim_button.add_argument("state", choices=["pressed", "released"])

    app = commands.add_parser("app")
    app_commands = app.add_subparsers(dest="app_command", required=True)
    app_commands.add_parser("list")

    install = app_commands.add_parser("install")
    install.add_argument("source_path")
    install.add_argument("--dev", action="store_true")

    run_app = app_commands.add_parser("run")
    run_app.add_argument("source_path")
    run_app.add_argument("--follow", "-f", action="store_true")
    run_app.add_argument("--lines", type=int, default=100)
    run_app.add_argument("--interval", type=float, default=1.0)

    for name in ("start", "stop", "uninstall"):
        command = app_commands.add_parser(name)
        command.add_argument("app_id")

    logs = commands.add_parser("logs")
    logs.add_argument("app_id")
    logs.add_argument("--lines", type=int, default=100)
    logs.add_argument("--follow", "-f", action="store_true")
    logs.add_argument("--interval", type=float, default=1.0)
    return parser


async def run(args: argparse.Namespace) -> dict[str, Any] | None:
    endpoint = (
        parse_endpoint(args.endpoint)
        if args.endpoint
        else default_runtime_endpoint()
    )
    client = RuntimeClient(endpoint)
    if args.command == "status":
        return await client.request("runtime.status")
    if args.command == "info":
        return await client.request("runtime.info")
    if args.command == "sim":
        return await client.request(
            "simulator.button.set",
            {"pressed": args.state == "pressed"},
        )
    if args.command == "logs":
        if args.follow:
            await follow_app_logs(
                client,
                args.app_id,
                lines=args.lines,
                interval=args.interval,
            )
            return None
        return await client.request(
            "app.logs",
            {"app_id": args.app_id, "lines": args.lines},
        )
    if args.app_command == "list":
        return await client.request("app.list")
    if args.app_command == "install":
        return await client.request(
            "app.install",
            {
                "source_path": str(Path(args.source_path).resolve()),
                "development": args.dev,
            },
        )
    if args.app_command == "run":
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
        return result
    method = {
        "start": "app.launch",
        "stop": "app.stop",
        "uninstall": "app.uninstall",
    }[args.app_command]
    return await client.request(method, {"app_id": args.app_id})


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "runtime":
        try:
            asyncio.run(runtime_main.run_from_args(args))
        except KeyboardInterrupt:
            pass
        return
    result = run_async_command(parser, lambda: run(args))
    if result is not None:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
