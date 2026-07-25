from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from ..apps import AppManager
from ..events import EventBus, EventSubscription
from .recognizer import GestureContext, GestureEvent, GestureRecognizer


class GestureService:
    def __init__(
        self,
        app_manager: AppManager,
        event_bus: EventBus,
        *,
        recognizer: GestureRecognizer | None = None,
        clock: Callable[[], float] = time.monotonic,
        shell_active_provider: Callable[[], bool] | None = None,
    ) -> None:
        self._app_manager = app_manager
        self._event_bus = event_bus
        self._recognizer = recognizer or GestureRecognizer()
        self._clock = clock
        self._shell_active_provider = shell_active_provider
        self._timer_task: asyncio.Task[None] | None = None
        self._subscription: EventSubscription | None = None
        self._event_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._last_event: GestureEvent | None = None

    async def start(self) -> None:
        self._recognizer.reset(self._current_context())
        self._subscription = self._event_bus.subscribe(
            event_names={
                "app.foreground_acquired",
                "app.foreground_revoked",
            }
        )
        self._event_task = asyncio.create_task(
            self._watch_context(),
            name="button-gesture-context",
        )

    async def stop(self) -> None:
        if self._event_task is not None:
            self._event_task.cancel()
            await asyncio.gather(self._event_task, return_exceptions=True)
            self._event_task = None
        if self._subscription is not None:
            self._event_bus.unsubscribe(self._subscription)
            self._subscription = None
        task, self._timer_task = self._timer_task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._recognizer.reset()

    async def handle_raw_event(
        self,
        event_name: str,
        _payload: dict[str, Any],
    ) -> None:
        if event_name not in {
            "button.raw_pressed",
            "button.raw_released",
        }:
            return

        async with self._lock:
            timestamp = self._clock()
            context = self._current_context()
            if event_name == "button.raw_pressed":
                events = self._recognizer.press(timestamp, context)
            else:
                events = self._recognizer.release(timestamp, context)
            self._reschedule_timer_locked()
        await self._emit(events)

    def snapshot(self) -> dict[str, Any]:
        context = self._current_context()
        last_event = self._last_event
        return {
            "context": context.value,
            "pressed": self._recognizer.pressed,
            "pending_clicks": self._recognizer.click_count,
            "last_event": (
                {
                    "name": last_event.name,
                    "context": last_event.context.value,
                    "click_count": last_event.click_count,
                }
                if last_event is not None
                else None
            ),
        }

    def _current_context(self) -> GestureContext:
        if self._app_manager.foreground_app_id is not None:
            return GestureContext.FOREGROUND
        if (
            self._shell_active_provider is not None
            and self._shell_active_provider()
        ):
            return GestureContext.SHELL
        return GestureContext.HOME

    def _reschedule_timer_locked(self) -> None:
        task, self._timer_task = self._timer_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        deadline = self._recognizer.next_deadline
        if deadline is not None:
            self._timer_task = asyncio.create_task(
                self._flush_at(deadline),
                name="button-gesture-timeout",
            )

    async def _flush_at(self, deadline: float) -> None:
        try:
            await asyncio.sleep(max(0.0, deadline - self._clock()))
            async with self._lock:
                events = self._recognizer.advance(self._clock())
                self._timer_task = None
                self._reschedule_timer_locked()
            await self._emit(events)
        except asyncio.CancelledError:
            raise

    async def _emit(self, events: list[GestureEvent]) -> None:
        for event in events:
            self._last_event = event
            await self._event_bus.emit(
                event.name,
                {
                    "context": event.context.value,
                    "click_count": event.click_count,
                },
                app_id=self._app_manager.foreground_app_id,
            )

    async def _watch_context(self) -> None:
        assert self._subscription is not None
        while True:
            await self._subscription.queue.get()
            async with self._lock:
                self._recognizer.reset(self._current_context())
                self._reschedule_timer_locked()
