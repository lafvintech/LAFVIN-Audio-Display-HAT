from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from lafvin_hat.sdk import DeviceApp
from lafvin_hat.ui import Canvas, StatusRow


REFRESH_INTERVAL_SEC = 2.0


async def main() -> None:
    app = await DeviceApp.connect_from_environment()
    await app.acquire_foreground()
    frame = await app.frames.acquire()
    events = app.subscribe(events=["app.exit_requested"])
    exit_task = asyncio.create_task(anext(events))
    try:
        while True:
            try:
                status = await app.client.request("runtime.status")
                await render_status_frame(frame, status)
            except Exception as exc:
                await render_error_frame(frame, exc)

            done, pending = await asyncio.wait(
                {exit_task},
                timeout=REFRESH_INTERVAL_SEC,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if exit_task in done:
                with contextlib.suppress(Exception):
                    exit_task.result()
                break
    finally:
        exit_task.cancel()
        await asyncio.gather(exit_task, return_exceptions=True)
        with contextlib.suppress(Exception):
            await events.aclose()
        await app.close()


async def render_status_frame(frame: Any, runtime_status: dict[str, Any]) -> None:
    await Canvas(
        width=frame.width,
        height=frame.height,
    ).system_status_page(status_rows(runtime_status)).present(frame)


async def render_error_frame(frame: Any, exc: Exception) -> None:
    await Canvas(
        width=frame.width,
        height=frame.height,
    ).error_page(
        "System Status",
        f"Status unavailable\n{type(exc).__name__}: {exc}",
    ).present(frame)


def status_rows(runtime_status: dict[str, Any]) -> list[StatusRow]:
    system = runtime_status.get("system", {})
    runtime = system.get("runtime", {})
    device = system.get("device", {})
    network = system.get("network", {})
    apps = system.get("apps", {})
    storage = system.get("storage", {})
    temperature = device.get("temperature_c")
    uptime_ms = runtime.get("uptime_ms", runtime_status.get("uptime_ms", 0))
    return [
        StatusRow("Runtime", _duration(_int_or_zero(uptime_ms))),
        StatusRow("Model", _short_model(device.get("model"))),
        StatusRow("IP", _network_meta(network)),
        StatusRow("APP", str(apps.get("installed_count", 0))),
        StatusRow(
            "Temp",
            f"{temperature}C" if temperature is not None else "Unknown",
        ),
        StatusRow("Storage", _storage_meta(storage)),
    ]


def _duration(uptime_ms: int) -> str:
    seconds = max(0, int(uptime_ms / 1000))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h"


def _network_meta(network: dict[str, Any]) -> str:
    ip_address = network.get("ip_address")
    if ip_address:
        return str(ip_address)
    return "disconnect"


def _short_model(value: Any) -> str:
    model = str(value or "Unknown")
    model = model.replace("Raspberry Pi", "RPI")
    if " Rev " in model:
        model = model.split(" Rev ", 1)[0]
    return model


def _storage_meta(storage: dict[str, Any]) -> str:
    used = storage.get("used_bytes")
    total = storage.get("total_bytes")
    if not isinstance(used, int) or not isinstance(total, int) or total <= 0:
        return "Unknown"
    return f"{_gib(used)}/{_gib(total)}G"


def _gib(value: int) -> str:
    amount = value / (1024 ** 3)
    if amount >= 10:
        return str(round(amount))
    return f"{amount:.1f}"


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    asyncio.run(main())
