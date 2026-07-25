from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GestureContext(StrEnum):
    HOME = "home"
    SHELL = "shell"
    FOREGROUND = "foreground"


@dataclass(frozen=True, slots=True)
class GestureConfig:
    max_click_duration: float = 0.300
    click_interval: float = 0.150
    max_sequence_duration: float = 1.200


@dataclass(frozen=True, slots=True)
class GestureEvent:
    name: str
    context: GestureContext
    click_count: int


class GestureRecognizer:
    """Recognize click gestures from monotonic press/release timestamps."""

    def __init__(self, config: GestureConfig | None = None) -> None:
        self.config = config or GestureConfig()
        self._context: GestureContext | None = None
        self._pressed_at: float | None = None
        self._click_count = 0
        self._first_click_at: float | None = None
        self._deadline: float | None = None

    @property
    def context(self) -> GestureContext | None:
        return self._context

    @property
    def click_count(self) -> int:
        return self._click_count

    @property
    def pressed(self) -> bool:
        return self._pressed_at is not None

    @property
    def next_deadline(self) -> float | None:
        return self._deadline

    def reset(self, context: GestureContext | None = None) -> None:
        self._context = context
        self._pressed_at = None
        self._click_count = 0
        self._first_click_at = None
        self._deadline = None

    def press(
        self,
        timestamp: float,
        context: GestureContext,
    ) -> list[GestureEvent]:
        events = self._prepare(timestamp, context)
        if self._pressed_at is None:
            self._pressed_at = timestamp
            self._deadline = None
        return events

    def release(
        self,
        timestamp: float,
        context: GestureContext,
    ) -> list[GestureEvent]:
        events = self._prepare(timestamp, context, flush_while_pressed=False)
        if self._pressed_at is None:
            return events

        duration = max(0.0, timestamp - self._pressed_at)
        self._pressed_at = None
        if duration > self.config.max_click_duration:
            self._clear_sequence()
            return events

        if (
            self._first_click_at is not None
            and timestamp - self._first_click_at
            > self.config.max_sequence_duration
        ):
            self._clear_sequence()

        if self._click_count == 0:
            self._first_click_at = timestamp
        self._click_count += 1

        if (
            context is GestureContext.HOME
            and self._click_count == 2
        ):
            events.append(
                GestureEvent(
                    name="button.double_clicked",
                    context=context,
                    click_count=2,
                )
            )
            self._clear_sequence()
            return events

        if (
            context in {GestureContext.SHELL, GestureContext.FOREGROUND}
            and self._click_count == 3
        ):
            events.append(
                GestureEvent(
                    name="button.triple_clicked",
                    context=context,
                    click_count=3,
                )
            )
            self._clear_sequence()
            return events

        interval_deadline = timestamp + self.config.click_interval
        if self._first_click_at is None:
            self._deadline = interval_deadline
        else:
            self._deadline = min(
                interval_deadline,
                self._first_click_at + self.config.max_sequence_duration,
            )
        return events

    def advance(self, timestamp: float) -> list[GestureEvent]:
        if (
            self._deadline is None
            or timestamp < self._deadline
            or self._pressed_at is not None
        ):
            return []

        events: list[GestureEvent] = []
        if self._context in {
            GestureContext.HOME,
            GestureContext.SHELL,
            GestureContext.FOREGROUND,
        }:
            if self._click_count == 2 and self._context in {
                GestureContext.SHELL,
                GestureContext.FOREGROUND,
            }:
                events.append(
                    GestureEvent(
                        name="button.double_clicked",
                        context=GestureContext.SHELL,
                        click_count=2,
                    )
                )
            elif self._click_count == 1:
                events.append(
                    GestureEvent(
                        name="button.single_clicked",
                        context=self._context,
                        click_count=1,
                    )
                )
        self._clear_sequence()
        return events

    def _prepare(
        self,
        timestamp: float,
        context: GestureContext,
        *,
        flush_while_pressed: bool = True,
    ) -> list[GestureEvent]:
        if self._context is not context:
            self.reset(context)
            return []
        if not flush_while_pressed and self._pressed_at is not None:
            return []
        return self.advance(timestamp)

    def _clear_sequence(self) -> None:
        self._click_count = 0
        self._first_click_at = None
        self._deadline = None
