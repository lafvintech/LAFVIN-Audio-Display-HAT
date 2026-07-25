from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from ..ipc.protocol import PROTOCOL_VERSION


@dataclass(eq=False, slots=True)
class EventSubscription:
    queue: asyncio.Queue[dict[str, Any]]
    event_names: frozenset[str] = field(default_factory=frozenset)
    app_id: str | None = None

    def accepts(self, event_name: str, app_id: str | None) -> bool:
        if self.event_names and event_name not in self.event_names:
            return False
        if self.app_id is not None and self.app_id != app_id:
            return False
        return True


class EventBus:
    def __init__(self, *, queue_size: int = 128) -> None:
        self._subscriptions: set[EventSubscription] = set()
        self._queue_size = queue_size

    def subscribe(
        self,
        *,
        event_names: set[str] | None = None,
        app_id: str | None = None,
    ) -> EventSubscription:
        subscription = EventSubscription(
            queue=asyncio.Queue(maxsize=self._queue_size),
            event_names=frozenset(event_names or ()),
            app_id=app_id,
        )
        self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: EventSubscription) -> None:
        self._subscriptions.discard(subscription)

    async def emit(
        self,
        event_name: str,
        payload: dict[str, Any] | None = None,
        *,
        app_id: str | None = None,
    ) -> dict[str, Any]:
        event = {
            "version": PROTOCOL_VERSION,
            "type": "event",
            "event": event_name,
            "timestamp_ms": int(time.time() * 1000),
            "payload": payload or {},
        }
        for subscription in tuple(self._subscriptions):
            if not subscription.accepts(event_name, app_id):
                continue
            if subscription.queue.full():
                try:
                    subscription.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            subscription.queue.put_nowait(event)
        return event

