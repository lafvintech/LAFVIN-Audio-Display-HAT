from __future__ import annotations

import argparse
import asyncio
import os
import signal
from pathlib import Path

from .config import (
    default_data_dir,
    default_log_dir,
    default_runtime_endpoint,
    load_env_file,
    parse_endpoint,
)
from .logging import configure_runtime_logging


def add_arguments(
    parser: argparse.ArgumentParser,
    *,
    endpoint_default: object | None = None,
) -> None:
    """Add the supported Runtime options to an existing parser."""

    parser.add_argument(
        "--env-file",
        help=(
            "Load local configuration from a NAME=VALUE file. "
            "Existing environment variables take precedence."
        ),
    )
    parser.add_argument(
        "--endpoint",
        default=endpoint_default,
        help="Runtime endpoint, for example unix:///path/runtime.sock or tcp://127.0.0.1:8765",
    )
    parser.add_argument(
        "--data-dir",
        help="Runtime-managed application data directory",
    )
    parser.add_argument(
        "--log-dir",
        help="Runtime and application log directory",
    )
    parser.add_argument(
        "--backend",
        choices=["simulator", "lafvin-hat"],
        default="simulator",
    )
    parser.add_argument("--simulator-host", default="127.0.0.1")
    parser.add_argument("--simulator-port", type=int, default=17880)
    parser.add_argument("--no-simulator-web", action="store_true")
    parser.add_argument(
        "--lafvin-hat-driver",
        dest="lafvin_hat_driver",
        help="Path to a LAFVIN HAT board development override",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LAFVIN HAT Device Runtime")
    add_arguments(parser)
    return parser


async def run(
    endpoint_value: str | None = None,
    *,
    simulator_host: str = "127.0.0.1",
    simulator_port: int = 17880,
    simulator_web_enabled: bool = True,
    backend_name: str = "simulator",
    lafvin_hat_driver: str | None = None,
    data_dir: str | Path | None = None,
    log_dir: str | Path | None = None,
) -> None:
    from .backends import LafvinHatBackend, SimulatorBackend
    from .ipc.server import RuntimeServer

    endpoint = (
        parse_endpoint(endpoint_value)
        if endpoint_value
        else default_runtime_endpoint()
    )
    if backend_name == "lafvin-hat":
        backend = LafvinHatBackend(
            Path(lafvin_hat_driver) if lafvin_hat_driver else None
        )
    else:
        backend = SimulatorBackend(
            host=simulator_host,
            port=simulator_port,
            web_enabled=simulator_web_enabled,
        )
    server = RuntimeServer(
        endpoint,
        backend=backend,
        data_dir=Path(data_dir) if data_dir else default_data_dir(),
        log_dir=Path(log_dir) if log_dir else default_log_dir(),
    )
    await server.start()

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, shutdown.set)
        except (NotImplementedError, RuntimeError):
            pass

    print(f"[Runtime] Listening on {server.bound_endpoint.as_uri()}")
    if isinstance(backend, SimulatorBackend) and simulator_web_enabled:
        print(
            "[Simulator] Open "
            f"http://{simulator_host}:{backend.bound_port}"
        )
    try:
        await shutdown.wait()
    finally:
        await server.close()


async def run_from_args(args: argparse.Namespace) -> None:
    if args.env_file:
        load_env_file(args.env_file)
    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    log_dir = Path(args.log_dir) if args.log_dir else default_log_dir()
    configure_runtime_logging(log_dir)
    from .apps.provision import provision_first_party_apps

    await asyncio.to_thread(provision_first_party_apps, data_dir)
    lafvin_hat_driver = (
        args.lafvin_hat_driver
        or os.getenv("LAFVIN_HAT_DRIVER")
    )
    await run(
        getattr(args, "endpoint", None),
        simulator_host=args.simulator_host,
        simulator_port=args.simulator_port,
        simulator_web_enabled=not args.no_simulator_web,
        backend_name=args.backend,
        lafvin_hat_driver=lafvin_hat_driver,
        data_dir=data_dir,
        log_dir=log_dir,
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(run_from_args(args))
    except KeyboardInterrupt:
        pass
