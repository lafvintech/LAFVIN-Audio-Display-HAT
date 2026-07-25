from __future__ import annotations

import asyncio
from typing import Any

from lafvin_hat.sdk import DeviceApp, RuntimeClientError
from lafvin_hat.ui import Canvas


ACTION_DOWN = 0
ACTION_UP = 1
VOLUME_PREVIEW_DELAY_SEC = 0.5
VOLUME_PREVIEW_KIND = "volume"


async def main() -> None:
    app = await DeviceApp.connect_from_environment()
    await app.acquire_foreground()
    frame = await app.frames.acquire()
    selected = ACTION_UP
    preview_task: asyncio.Task[None] | None = None

    async def refresh() -> None:
        try:
            volume = await app.audio.get_volume()
            await render_volume_frame(frame, volume, selected)
        except Exception as exc:
            await render_error_frame(frame, exc)

    async def set_selected(index: int) -> None:
        nonlocal selected
        selected = index
        await refresh()

    await refresh()
    try:
        async for event in app.subscribe(
            events=[
                "button.single_clicked",
                "button.double_clicked",
                "app.exit_requested",
            ]
        ):
            name = event["event"]
            if name == "app.exit_requested":
                break
            if name == "button.single_clicked":
                await set_selected(
                    ACTION_DOWN if selected == ACTION_UP else ACTION_UP
                )
            elif name == "button.double_clicked":
                try:
                    await apply_selected(app, selected)
                    await refresh()
                    preview_task = await schedule_volume_preview(
                        app,
                        preview_task,
                    )
                except Exception as exc:
                    await render_error_frame(frame, exc)
    finally:
        await cancel_volume_preview(app, preview_task)
        await app.close()


def build_volume_canvas(
    volume: int,
    selected: int = ACTION_UP,
    *,
    width: int = 240,
    height: int = 280,
) -> Canvas:
    return (
        Canvas(width=width, height=height)
        .clear()
        .title("Volume")
        .divider()
        .center_text(f"{volume}%", y=96, size="large")
        .button_row(["-10%", "+10%"], selected=selected, y=176)
    )


async def render_volume_frame(
    frame: Any,
    volume: int,
    selected: int = ACTION_UP,
) -> None:
    await build_volume_canvas(
        volume,
        selected,
        width=frame.width,
        height=frame.height,
    ).present(frame)


async def apply_selected(app: DeviceApp, selected: int) -> int:
    volume = await app.audio.get_volume()
    if selected == ACTION_UP:
        return await app.audio.set_volume(min(100, volume + 10))
    return await app.audio.set_volume(max(0, volume - 10))


async def schedule_volume_preview(
    app: DeviceApp,
    previous_task: asyncio.Task[None] | None,
    *,
    delay_sec: float = VOLUME_PREVIEW_DELAY_SEC,
) -> asyncio.Task[None]:
    """Replace a pending preview so only the final adjustment is heard."""

    await cancel_volume_preview(app, previous_task)
    return asyncio.create_task(
        _play_volume_preview(app, delay_sec=delay_sec),
        name="system-volume-preview",
    )


async def cancel_volume_preview(
    app: DeviceApp,
    task: asyncio.Task[None] | None,
) -> None:
    if task is None:
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    try:
        await app.audio.stop()
    except RuntimeClientError as exc:
        if exc.code != "INVALID_SESSION":
            raise


async def _play_volume_preview(
    app: DeviceApp,
    *,
    delay_sec: float,
) -> None:
    try:
        await asyncio.sleep(delay_sec)
        await app.audio.play_feedback_tone(VOLUME_PREVIEW_KIND)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # A preview failure must not make the volume control itself unusable.
        print(f"[Volume] feedback preview failed: {exc}")


async def render_error_frame(frame: Any, exc: Exception) -> None:
    await Canvas(
        width=frame.width,
        height=frame.height,
    ).error_page(
        "Volume",
        f"Volume unavailable\n{type(exc).__name__}: {exc}",
    ).present(frame)


if __name__ == "__main__":
    asyncio.run(main())
