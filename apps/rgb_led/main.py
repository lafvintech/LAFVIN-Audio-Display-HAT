from __future__ import annotations

import asyncio
import colorsys
import contextlib
import time
from typing import Any

from lafvin_hat.sdk import DeviceApp


MODE_GRADIENT = "gradient"
MODE_PALETTE = "palette"
LED_OFF = (0, 0, 0)
GRADIENT_PERIOD_SEC = 8.0
GRADIENT_STEP_SEC = 0.04
PALETTE: tuple[tuple[int, int, int], ...] = (
    (255, 0, 0),
    (255, 96, 0),
    (255, 220, 0),
    (0, 220, 40),
    (0, 200, 255),
    (0, 64, 255),
    (180, 0, 255),
    (255, 255, 255),
)


class RgbLamp:
    """Two-mode RGB lamp: continuous gradient, or a static palette color."""

    def __init__(self, *, started_at: float = 0.0) -> None:
        self.mode = MODE_GRADIENT
        self.palette_index = 0
        self.gradient_started_at = started_at

    def color_at(self, now: float) -> tuple[int, int, int]:
        if self.mode == MODE_PALETTE:
            return PALETTE[self.palette_index]
        return gradient_rgb(now - self.gradient_started_at)

    def on_single_click(self, now: float) -> tuple[int, int, int]:
        if self.mode == MODE_GRADIENT:
            self.mode = MODE_PALETTE
        else:
            self.palette_index = (self.palette_index + 1) % len(PALETTE)
        return PALETTE[self.palette_index]

    def on_double_click(self, now: float) -> tuple[int, int, int]:
        self.mode = MODE_GRADIENT
        self.gradient_started_at = now
        return gradient_rgb(0.0)


def rgb_from_hue(
    hue: float,
    *,
    saturation: float = 1.0,
    value: float = 1.0,
) -> tuple[int, int, int]:
    red, green, blue = colorsys.hsv_to_rgb(hue % 1.0, saturation, value)
    return (round(red * 255), round(green * 255), round(blue * 255))


def gradient_rgb(
    elapsed_sec: float,
    *,
    period_sec: float = GRADIENT_PERIOD_SEC,
) -> tuple[int, int, int]:
    if period_sec <= 0:
        raise ValueError("period_sec must be positive")
    return rgb_from_hue((elapsed_sec / period_sec) % 1.0)


async def set_led(app: Any, rgb: tuple[int, int, int]) -> None:
    red, green, blue = rgb
    await app.client.request(
        "device.set_led",
        {
            "app_id": app.app_id,
            "session_token": app.session_token,
            "r": int(red),
            "g": int(green),
            "b": int(blue),
        },
    )


async def clear_screen(frame: Any) -> None:
    frame.clear(0)
    await frame.commit()


async def main() -> None:
    app = await DeviceApp.connect_from_environment()
    await app.acquire_foreground()
    frame = await app.frames.acquire()
    await clear_screen(frame)

    lamp = RgbLamp(started_at=time.monotonic())
    events = app.subscribe(
        events=[
            "button.single_clicked",
            "button.double_clicked",
            "app.exit_requested",
        ]
    )
    next_event = asyncio.create_task(anext(events), name="rgb-led-event")
    try:
        await set_led(app, lamp.color_at(time.monotonic()))
        while True:
            timeout = (
                GRADIENT_STEP_SEC if lamp.mode == MODE_GRADIENT else None
            )
            done, _pending = await asyncio.wait(
                {next_event},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if next_event not in done:
                await set_led(app, lamp.color_at(time.monotonic()))
                continue

            event = next_event.result()
            name = event["event"]
            if name == "app.exit_requested":
                break
            now = time.monotonic()
            if name == "button.single_clicked":
                await set_led(app, lamp.on_single_click(now))
            elif name == "button.double_clicked":
                await set_led(app, lamp.on_double_click(now))
            next_event = asyncio.create_task(
                anext(events),
                name="rgb-led-event",
            )
    finally:
        next_event.cancel()
        await asyncio.gather(next_event, return_exceptions=True)
        with contextlib.suppress(Exception):
            await events.aclose()
        with contextlib.suppress(Exception):
            await set_led(app, LED_OFF)
        await app.close()


if __name__ == "__main__":
    asyncio.run(main())
