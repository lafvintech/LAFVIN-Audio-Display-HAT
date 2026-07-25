from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Any

from ..backends import DeviceBackend
from ..ui import UIService
from ..ui.views import SystemPage, TextComponent


logger = logging.getLogger("lafvin_hat.runtime.diagnostics")


@dataclass(frozen=True, slots=True)
class HardwareTestTimings:
    color_sec: float = 0.8
    led_sec: float = 0.8
    gesture_timeout_sec: float = 8.0
    mic_wait_timeout_sec: float = 8.0
    mic_duration_sec: int = 3
    feedback_sec: float = 0.25
    summary_poll_sec: float = 0.25


@dataclass(slots=True)
class HardwareTestResult:
    name: str
    ok: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "status": "OK" if self.ok else "FAIL",
            "reason": self.reason,
        }


class HardwareTestFlow:
    def __init__(
        self,
        backend: DeviceBackend,
        ui_service: UIService,
        audio_service: Any,
        *,
        timings: HardwareTestTimings | None = None,
    ) -> None:
        self._backend = backend
        self._ui_service = ui_service
        self._audio_service = audio_service
        self._timings = timings or HardwareTestTimings()
        self._events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._results: list[HardwareTestResult] = []
        self._active = False
        self._phase = "idle"
        self._task: asyncio.Task[None] | None = None

    @property
    def active(self) -> bool:
        return self._active

    def snapshot(self) -> dict[str, Any]:
        return {
            "active": self._active,
            "phase": self._phase,
            "results": [result.to_dict() for result in self._results],
        }

    async def start(self) -> None:
        if self._active:
            return
        self._drain_events()
        self._results = []
        self._phase = "starting"
        self._active = True
        self._task = asyncio.create_task(
            self._run(),
            name="hardware-test-flow",
        )

    async def stop(self) -> None:
        self._active = False
        self._phase = "stopping"
        task = self._task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self._task = None
        with contextlib.suppress(Exception):
            await self._backend.set_led(0, 0, 0)
        self._drain_events()

    async def handle_event(self, event: dict[str, Any]) -> bool:
        if not self._active:
            return False
        name = event.get("event")
        if not isinstance(name, str) or not name.startswith("button."):
            return False
        if self._phase == "summary" and name == "button.triple_clicked":
            await self.stop()
            return True
        await self._events.put(event)
        return True

    async def _run(self) -> None:
        try:
            await self._run_lcd_test()
            await self._run_rgb_test()
            await self._run_button_test()
            await self._run_speaker_test()
            await self._run_mic_test()
            await self._show_summary()
            while self._active:
                await asyncio.sleep(self._timings.summary_poll_sec)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Hardware test flow failed")
            self._record("Runtime", False, str(exc))
            with contextlib.suppress(Exception):
                await self._show_summary()
            while self._active:
                await asyncio.sleep(self._timings.summary_poll_sec)
        finally:
            self._active = False
            self._phase = "idle"
            if self._task is asyncio.current_task():
                self._task = None
            with contextlib.suppress(Exception):
                await self._backend.set_led(0, 0, 0)
            self._drain_events()

    async def _run_lcd_test(self) -> None:
        self._phase = "lcd"
        try:
            # Start with a visible frame so entering diagnostics does not look
            # like the display briefly turned off.
            colors = [
                ("White", (255, 255, 255)),
                ("Black", (0, 0, 0)),
                ("Red", (255, 0, 0)),
                ("Green", (0, 255, 0)),
                ("Blue", (0, 0, 255)),
            ]
            for _label, color in colors:
                await self._present_raw_frame(_solid_frame(
                    self._backend.display_width,
                    self._backend.display_height,
                    color,
                ))
                await asyncio.sleep(self._timings.color_sec)
            await self._present_raw_frame(_border_cross_frame(
                self._backend.display_width,
                self._backend.display_height,
            ))
            await asyncio.sleep(self._timings.color_sec)
            self._record("LCD", True)
        except Exception as exc:
            self._record("LCD", False, str(exc))

    async def _run_rgb_test(self) -> None:
        self._phase = "rgb"
        ok = True
        reason = ""
        for label, color in [
            ("Red", (255, 0, 0)),
            ("Green", (0, 255, 0)),
            ("Blue", (0, 0, 255)),
        ]:
            try:
                # SPI screen updates are slower than LED changes, so paint the
                # prompt first and then switch the LED color.
                await self._show_page("RGB LED", [label])
                await self._backend.set_led(*color)
                await asyncio.sleep(self._timings.led_sec)
            except Exception as exc:
                ok = False
                reason = str(exc)
                break
        with contextlib.suppress(Exception):
            await self._backend.set_led(0, 0, 0)
        self._record("RGB", ok, reason)

    async def _run_button_test(self) -> None:
        self._phase = "button"
        expected = [
            ("button.single_clicked", "Press once"),
            ("button.double_clicked", "Press twice"),
            ("button.triple_clicked", "Press three times"),
        ]
        failures: list[str] = []
        for event_name, prompt in expected:
            await self._show_page("Button Test", [prompt])
            self._drain_events()
            try:
                await self._wait_for_event(
                    event_name,
                    timeout=self._timings.gesture_timeout_sec,
                )
                await self._show_page("Button Test", [prompt, "OK"])
            except TimeoutError:
                failures.append(prompt)
                await self._show_page("Button Test", [prompt, "TIMEOUT"])
            await asyncio.sleep(self._timings.feedback_sec)
        if failures:
            self._record("Button", False, ", ".join(failures))
        else:
            self._record("Button", True)

    async def _run_speaker_test(self) -> None:
        self._phase = "speaker"
        await self._show_page("Speaker Test", ["Playing tone"])
        try:
            await self._audio_service.play_system_tone()
            self._record("Speaker", True)
        except Exception as exc:
            self._record("Speaker", False, str(exc))
            await self._show_page("Speaker Test", ["FAIL", str(exc)[:60]])
            await asyncio.sleep(0.8)

    async def _run_mic_test(self) -> None:
        self._phase = "mic"
        await self._show_page(
            "Mic Test",
            [
                "Hold button to record",
                "Speak up to 3s",
            ],
        )
        self._drain_events()
        recording_session: str | None = None
        try:
            await self._wait_for_event(
                "button.raw_pressed",
                timeout=self._timings.mic_wait_timeout_sec,
            )
            await self._show_page("Mic Test", ["Recording..."])
            recording = await self._audio_service.start_system_recording(
                max_duration_sec=self._timings.mic_duration_sec,
            )
            recording_session = recording["recording_session"]
            with contextlib.suppress(TimeoutError):
                await self._wait_for_event(
                    "button.raw_released",
                    timeout=float(self._timings.mic_duration_sec),
                )
            await self._show_page("Mic Test", ["Playing back..."])
            result = await self._audio_service.stop_system_recording(
                recording_session,
            )
            recording_session = None
            await self._audio_service.play_system_file(result["path"])
            self._record("Mic", True)
        except Exception as exc:
            self._record("Mic", False, str(exc))
            await self._show_page("Mic Test", ["FAIL", str(exc)[:60]])
            await asyncio.sleep(0.8)
        finally:
            if recording_session is not None:
                with contextlib.suppress(Exception):
                    await self._audio_service.stop_system_recording(
                        recording_session,
                    )

    async def _show_summary(self) -> None:
        self._phase = "summary"
        lines = [
            f"{result.name:<8}{'OK' if result.ok else 'FAIL'}"
            for result in self._results
        ]
        lines.append("")
        lines.append("Triple click to Home")
        await self._show_page("Hardware Test", lines)

    async def _show_page(self, title: str, lines: list[str]) -> None:
        await self._ui_service.set_system_view(
            SystemPage(
                title=title,
                components=[
                    TextComponent("\n".join(lines), style="strong"),
                ],
            ).to_view()
        )

    async def _present_raw_frame(self, frame: bytes) -> None:
        await self._backend.present_frame(
            frame,
            width=self._backend.display_width,
            height=self._backend.display_height,
        )
        await self._backend.set_display_mode("raw_frame")

    async def _wait_for_event(
        self,
        event_name: str,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while self._active:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(event_name)
            event = await asyncio.wait_for(
                self._events.get(),
                timeout=remaining,
            )
            if event.get("event") == event_name:
                return event
        raise TimeoutError(event_name)

    def _record(
        self,
        name: str,
        ok: bool,
        reason: str = "",
    ) -> None:
        if not ok and reason:
            logger.warning("Hardware test %s failed: %s", name, reason)
        self._results.append(HardwareTestResult(name, ok, reason))

    def _drain_events(self) -> None:
        while True:
            try:
                self._events.get_nowait()
            except asyncio.QueueEmpty:
                return


def _solid_frame(
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> bytes:
    pixel = _rgb565_be(*color)
    row = pixel * width
    return row * height


def _border_cross_frame(width: int, height: int) -> bytes:
    background = _rgb565_be(0, 0, 0)
    foreground = _rgb565_be(255, 255, 255)
    frame = bytearray(background * width * height)
    middle_x = width // 2
    middle_y = height // 2
    for y in range(height):
        for x in range(width):
            border = x in {0, width - 1} or y in {0, height - 1}
            cross = x == middle_x or y == middle_y
            if border or cross:
                index = (y * width + x) * 2
                frame[index:index + 2] = foreground
    return bytes(frame)


def _rgb565_be(r: int, g: int, b: int) -> bytes:
    value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return value.to_bytes(2, byteorder="big")
