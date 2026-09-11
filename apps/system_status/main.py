from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any

from lafvin_hat.sdk import DeviceApp
from lafvin_hat.ui import Canvas, StatusRow


REFRESH_INTERVAL_SEC = 2.0
PAGE_MONITOR = 0
PAGE_DEVICE_INFO = 1
PAGE_COUNT = 2

CPU_ACCENT = (24, 169, 218)
MEMORY_ACCENT = (149, 204, 55)
TEMPERATURE_ACCENT = (246, 164, 43)
STORAGE_ACCENT = (145, 91, 220)
CARD_FILL = (250, 250, 250)
CARD_OUTLINE = (214, 218, 222)


@dataclass(frozen=True, slots=True)
class MetricCard:
    label: str
    value: str
    progress: float | None
    accent: tuple[int, int, int]


async def main() -> None:
    app = await DeviceApp.connect_from_environment()
    events = None
    event_task: asyncio.Task[dict[str, Any]] | None = None
    try:
        await app.acquire_foreground()
        frame = await app.frames.acquire()
        events = app.subscribe(
            events=["button.single_clicked", "app.exit_requested"]
        )
        event_task = asyncio.create_task(anext(events), name="system-status-event")
        page_index = PAGE_MONITOR
        latest_status: dict[str, Any] | None = None

        try:
            latest_status = await refresh_status(app, frame, page_index)
        except Exception as exc:
            await render_error_frame(frame, exc)

        while True:
            done, _pending = await asyncio.wait(
                {event_task},
                timeout=REFRESH_INTERVAL_SEC,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if event_task not in done:
                try:
                    latest_status = await refresh_status(app, frame, page_index)
                except Exception as exc:
                    await render_error_frame(frame, exc)
                continue

            try:
                event = event_task.result()
            except StopAsyncIteration:
                break
            if event["event"] == "app.exit_requested":
                break

            event_task = asyncio.create_task(
                anext(events),
                name="system-status-event",
            )
            if event["event"] == "button.single_clicked":
                page_index = (page_index + 1) % PAGE_COUNT
                try:
                    if latest_status is None:
                        latest_status = await refresh_status(app, frame, page_index)
                    else:
                        await render_status_frame(frame, latest_status, page_index)
                except Exception as exc:
                    await render_error_frame(frame, exc)
    finally:
        if event_task is not None:
            event_task.cancel()
            await asyncio.gather(event_task, return_exceptions=True)
        if events is not None:
            with contextlib.suppress(Exception):
                await events.aclose()
        await app.close()


async def refresh_status(app: Any, frame: Any, page_index: int) -> dict[str, Any]:
    status = await app.client.request("runtime.status")
    await render_status_frame(frame, status, page_index)
    return status


async def render_status_frame(
    frame: Any,
    runtime_status: dict[str, Any],
    page_index: int = PAGE_MONITOR,
) -> None:
    canvas = Canvas(width=frame.width, height=frame.height)
    if page_index == PAGE_DEVICE_INFO:
        render_device_info_page(canvas, runtime_status)
    else:
        render_monitor_page(canvas, runtime_status)
    await canvas.present(frame)


def render_monitor_page(
    canvas: Canvas,
    runtime_status: dict[str, Any],
) -> Canvas:
    _page_header(canvas, "SYSTEM MONITOR")
    card_width = (canvas.width - 22) // 2
    card_height = 92
    positions = (
        (8, 50),
        (14 + card_width, 50),
        (8, 148),
        (14 + card_width, 148),
    )
    for metric, (x, y) in zip(monitor_metrics(runtime_status), positions, strict=True):
        draw_metric_card(
            canvas,
            metric,
            x=x,
            y=y,
            width=card_width,
            height=card_height,
        )
    canvas.page_indicator(PAGE_MONITOR, PAGE_COUNT, y=262)
    return canvas


def render_device_info_page(
    canvas: Canvas,
    runtime_status: dict[str, Any],
) -> Canvas:
    _page_header(canvas, "DEVICE INFO")
    for index, row in enumerate(device_info_rows(runtime_status)):
        canvas.key_value_row(
            row.label.upper(),
            row.value,
            x=8,
            y=50 + index * 38,
            width=canvas.width - 16,
            height=34,
            label_width=72,
            label_fill=canvas.theme.text,
            value_fill=canvas.theme.text,
        )
    canvas.page_indicator(PAGE_DEVICE_INFO, PAGE_COUNT, y=262)
    return canvas


def draw_metric_card(
    canvas: Canvas,
    metric: MetricCard,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> Canvas:
    canvas.panel(
        x=x,
        y=y,
        width=width,
        height=height,
        fill=CARD_FILL,
        outline=CARD_OUTLINE,
    )
    canvas.draw.text(
        (x + 8, y + 7),
        metric.label,
        fill=canvas.theme.text,
        font=canvas.small_font,
    )
    canvas.draw.line(
        (x + 8, y + 29, x + 38, y + 29),
        fill=metric.accent,
        width=3,
    )
    canvas.draw.text(
        (x + 8, y + 53),
        metric.value,
        fill=canvas.theme.text,
        font=canvas.body_font,
        anchor="lm",
    )
    canvas.progress_ring(
        metric.progress,
        center_x=x + width - 30,
        center_y=y + 57,
        radius=23,
        color=metric.accent,
        width=6,
    )
    return canvas


async def render_error_frame(frame: Any, exc: Exception) -> None:
    await Canvas(
        width=frame.width,
        height=frame.height,
    ).error_page(
        "System Status",
        f"Status unavailable\n{type(exc).__name__}: {exc}",
    ).present(frame)


def monitor_metrics(runtime_status: dict[str, Any]) -> tuple[MetricCard, ...]:
    system = _mapping(runtime_status.get("system"))
    resources = _mapping(system.get("resources"))
    cpu = _mapping(resources.get("cpu"))
    memory = _mapping(resources.get("memory"))
    device = _mapping(system.get("device"))
    storage = _mapping(system.get("storage"))

    cpu_percent = _percentage(cpu.get("usage_percent"))
    memory_percent = _percentage(memory.get("usage_percent"))
    temperature = _number_or_none(device.get("temperature_c"))
    storage_percent = _storage_percentage(storage)
    return (
        MetricCard(
            "CPU",
            _percent_text(cpu_percent),
            _normalized_percent(cpu_percent),
            CPU_ACCENT,
        ),
        MetricCard(
            "MEMORY",
            _percent_text(memory_percent),
            _normalized_percent(memory_percent),
            MEMORY_ACCENT,
        ),
        MetricCard(
            "TEMP °C",
            _temperature_text(temperature),
            min(1.0, max(0.0, temperature / 85.0))
            if temperature is not None
            else None,
            TEMPERATURE_ACCENT,
        ),
        MetricCard(
            "STORAGE",
            _percent_text(storage_percent),
            _normalized_percent(storage_percent),
            STORAGE_ACCENT,
        ),
    )


def device_info_rows(runtime_status: dict[str, Any]) -> list[StatusRow]:
    system = _mapping(runtime_status.get("system"))
    runtime = _mapping(system.get("runtime"))
    device = _mapping(system.get("device"))
    network = _mapping(system.get("network"))
    apps = _mapping(system.get("apps"))
    uptime_ms = runtime.get("uptime_ms", runtime_status.get("uptime_ms", 0))
    return [
        StatusRow("Runtime", _duration(_int_or_zero(uptime_ms))),
        StatusRow("Model", _short_model(device.get("model"))),
        StatusRow("IP", _network_meta(network)),
        StatusRow("Apps", str(apps.get("installed_count", 0))),
        StatusRow("Host", str(device.get("hostname") or "Unknown")),
    ]


def _page_header(canvas: Canvas, title: str) -> None:
    canvas.clear().center_text(title, y=24, size="title").divider(y=43)


def _duration(uptime_ms: int) -> str:
    seconds = max(0, int(uptime_ms / 1000))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h {minutes % 60:02d}m"
    return f"{hours // 24}d {hours % 24:02d}h"


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


def _storage_percentage(storage: dict[str, Any]) -> float | None:
    reported = _percentage(storage.get("usage_percent"))
    if reported is not None:
        return reported
    used = _number_or_none(storage.get("used_bytes"))
    total = _number_or_none(storage.get("total_bytes"))
    if used is None or total is None or total <= 0:
        return None
    return _percentage(used * 100 / total)


def _percent_text(value: float | None) -> str:
    return "--" if value is None else f"{round(value)}%"


def _temperature_text(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _normalized_percent(value: float | None) -> float | None:
    return value / 100 if value is not None else None


def _percentage(value: Any) -> float | None:
    number = _number_or_none(value)
    if number is None:
        return None
    return min(100.0, max(0.0, number))


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    asyncio.run(main())
