from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from lafvin_hat.sdk.client import RuntimeClient


def resolve_source_path(source_path: str) -> str:
    return str(Path(source_path).resolve())


async def install_development_app(
    client: RuntimeClient,
    source_path: str,
) -> dict[str, Any]:
    return await client.request(
        "app.install",
        {
            "source_path": resolve_source_path(source_path),
            "development": True,
        },
    )


async def run_development_app(
    client: RuntimeClient,
    source_path: str,
) -> dict[str, Any]:
    installed = await install_development_app(client, source_path)
    app_id = str(installed["id"])
    launched = await client.request("app.launch", {"app_id": app_id})
    return {
        "app_id": app_id,
        "installed": installed,
        "launched": launched,
    }


def new_log_lines(
    previous: list[str],
    current: list[str],
) -> list[str]:
    if not previous:
        return current
    max_overlap = min(len(previous), len(current))
    for overlap in range(max_overlap, 0, -1):
        if previous[-overlap:] == current[:overlap]:
            return current[overlap:]
    return current


async def follow_app_logs(
    client: RuntimeClient,
    app_id: str,
    *,
    lines: int = 100,
    interval: float = 1.0,
) -> None:
    previous: list[str] = []
    while True:
        result = await client.request(
            "app.logs",
            {"app_id": app_id, "lines": lines},
        )
        current = [
            str(line)
            for line in result.get("lines", [])
        ]
        for line in new_log_lines(previous, current):
            print(line, flush=True)
        previous = current
        await asyncio.sleep(interval)
