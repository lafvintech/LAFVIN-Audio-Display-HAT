from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from pathlib import Path
from typing import Any

from lafvin_hat.ai import (
    ASRProvider,
    Message,
    PipelineStageError,
    SpeechSegment,
    StreamingSpeechPipeline,
    configure_ai_logging,
    providers_from_environment,
)
from lafvin_hat.sdk import DeviceApp, RecordingSession
from lafvin_hat.ui import Canvas, ChatMessage


TITLE = "AI Chatbot"
SYSTEM_PROMPT = os.getenv(
    "LAFVIN_CHATBOT_SYSTEM_PROMPT",
    (
        "You are a concise and helpful assistant for a small portable device. "
        "Respond in plain text without Markdown formatting because your answer "
        "will be spoken aloud."
    ),
)
MAX_HISTORY_MESSAGES = 12
ACTION_TALK = 0
ACTION_BACK = 1
CLICK_INTERVAL_SEC = 0.35
HOLD_THRESHOLD_SEC = 0.45
logger = logging.getLogger("lafvin_hat.app.chatbot")
CONTROL_LABELS = ["Talk", "Back"]
DISPLAY_MAX_FPS = 12
SCROLL_FOCUS_RATIO = 0.65


class ChatbotDisplay:
    def __init__(self, frame: Any) -> None:
        self.frame = frame
        self.selected = ACTION_TALK
        self._state: dict[str, Any] = {
            "kind": "text",
            "text": "Hold the button and speak.",
            "status": "idle",
            "emphasis": "primary",
            "actions": True,
        }
        self._scroll_top = 0.0
        self._answer_revision = 0
        self._scroll_task: asyncio.Task[None] | None = None
        self._scroll_sequence: int | None = None
        self._scroll_started_at: float | None = None
        self._render_event = asyncio.Event()
        self._render_condition = asyncio.Condition()
        self._render_worker: asyncio.Task[None] | None = None
        self._render_requested = 0
        self._render_completed = 0
        self._render_error: tuple[int, Exception] | None = None
        self._last_render_at = 0.0
        self._closed = False

    async def set_selected(self, index: int) -> None:
        self.selected = index
        await self.render()

    async def show_idle(self) -> None:
        await self._stop_speech_sync()
        self._scroll_top = 0.0
        self._state = {
            "kind": "text",
            "text": "Hold the button and speak.",
            "status": "idle",
            "emphasis": "primary",
            "actions": True,
        }
        await self.render()

    async def show_listening(self) -> None:
        await self._stop_speech_sync()
        self._scroll_top = 0.0
        self._state = {
            "kind": "text",
            "text": "Listening... release to send.",
            "status": "listening",
            "emphasis": "primary",
            "actions": True,
        }
        await self.render()

    async def show_status(self, text: str, status: str) -> None:
        await self._stop_speech_sync()
        self._scroll_top = 0.0
        self._state = {
            "kind": "text",
            "text": text,
            "status": status,
            "emphasis": "primary",
            "actions": True,
        }
        await self.render()

    async def show_error(self, error: Exception) -> None:
        await self._stop_speech_sync()
        self._scroll_top = 0.0
        self._state = {
            "kind": "text",
            "text": f"Request failed: {str(error)[:240]}",
            "status": "error",
            "emphasis": "danger",
            "actions": True,
        }
        await self.render()

    async def show_audio_error(self, action: str, error: Exception) -> None:
        await self._stop_speech_sync()
        self._scroll_top = 0.0
        self._state = {
            "kind": "text",
            "text": f"Recording {action} failed: {str(error)[:210]}",
            "status": "error",
            "emphasis": "danger",
            "actions": True,
        }
        await self.render()

    async def show_configuration_error(self, error: Exception) -> None:
        await self._stop_speech_sync()
        self._scroll_top = 0.0
        self._state = {
            "kind": "text",
            "text": f"AI configuration error: {str(error)[:220]}",
            "status": "error",
            "emphasis": "danger",
            "actions": False,
        }
        await self.render()

    async def show_question(self, text: str) -> None:
        await self._stop_speech_sync()
        self._scroll_top = 0.0
        self._answer_revision = 0
        self._state = {
            "kind": "question",
            "text": text,
            "status": "thinking",
            "emphasis": "primary",
            "actions": True,
        }
        await self.render()

    async def show_chat(
        self,
        messages: list[Message],
        *,
        status: str = "answering",
        streaming: bool = True,
    ) -> None:
        await self._stop_speech_sync()
        self._scroll_top = 0.0
        self._state = {
            "kind": "chat",
            "status": status,
            "streaming": streaming,
            "messages": [
                ChatMessage(message.role, message.content)
                for message in messages
            ],
            "actions": True,
        }
        await self.render()

    async def append_answer_text(self, text: str) -> None:
        if not text:
            return
        if self._state.get("kind") != "answer":
            self._scroll_top = 0.0
            self._answer_revision = 0
            self._state = {
                "kind": "answer",
                "text": "",
                "status": "answering",
                "streaming": True,
                "actions": True,
            }
        self._state["text"] = str(self._state.get("text", "")) + text
        self._answer_revision += 1
        await self.render()

    async def append_assistant_text(self, text: str) -> None:
        if self._state.get("kind") != "chat":
            await self.append_answer_text(text)
            return
        messages = self._state.get("messages")
        if not isinstance(messages, list) or not messages:
            return
        assistant = messages[-1]
        if not isinstance(assistant, ChatMessage):
            return
        messages[-1] = ChatMessage(
            assistant.role,
            assistant.text + text,
        )
        await self.render()

    async def finish_chat(self) -> None:
        if self._state.get("kind") == "answer":
            await self.finish_answer()
            return
        if self._state.get("kind") == "chat":
            self._state["status"] = "idle"
            self._state["streaming"] = False
            await self.render()

    async def finish_answer(self) -> None:
        if self._state.get("kind") != "answer":
            return
        self._state["status"] = "idle"
        self._state["streaming"] = False
        await self.render()

    async def start_speech_segment(self, segment: SpeechSegment) -> None:
        await self._stop_speech_sync()
        if self._state.get("kind") != "answer":
            logger.info(
                "stage=display_sync event=disabled reason=answer_not_visible "
                "sequence=%s",
                segment.sequence,
            )
            return
        if segment.duration_ms is None or segment.duration_ms <= 0:
            logger.info(
                "stage=display_sync event=disabled reason=missing_duration "
                "sequence=%s",
                segment.sequence,
            )
            return
        target = self._scroll_target(segment.display_end)
        if target <= self._scroll_top + 0.5:
            logger.info(
                "stage=display_sync event=skipped reason=no_scroll "
                "sequence=%s char_end=%s",
                segment.sequence,
                segment.display_end,
            )
            return
        self._scroll_sequence = segment.sequence
        self._scroll_started_at = time.monotonic()
        logger.info(
            "stage=display_sync event=start sequence=%s char_end=%s "
            "duration_ms=%s start_y=%s target_y=%s",
            segment.sequence,
            segment.display_end,
            segment.duration_ms,
            round(self._scroll_top, 1),
            round(target, 1),
        )
        self._scroll_task = asyncio.create_task(
            self._animate_speech_segment(segment),
            name=f"chatbot-scroll-{segment.sequence}",
        )

    async def finish_speech_segment(
        self,
        segment: SpeechSegment,
        completed: bool,
    ) -> None:
        if self._scroll_sequence != segment.sequence:
            return
        finished_at = time.monotonic()
        task = self._scroll_task
        self._scroll_task = None
        if task is not None and not task.done():
            task.cancel()
        if task is not None and task is not asyncio.current_task():
            await asyncio.gather(task, return_exceptions=True)

        started_at = self._scroll_started_at
        self._scroll_sequence = None
        self._scroll_started_at = None
        if not completed:
            logger.info(
                "stage=display_sync event=cancelled sequence=%s",
                segment.sequence,
            )
            return

        target = self._scroll_target(segment.display_end)
        if target > self._scroll_top + 0.5:
            self._scroll_top = target
            await self.render()
        actual_ms = (
            int((finished_at - started_at) * 1000)
            if started_at is not None
            else None
        )
        drift_ms = (
            actual_ms - segment.duration_ms
            if actual_ms is not None and segment.duration_ms is not None
            else None
        )
        logger.info(
            "stage=display_sync event=done sequence=%s actual_ms=%s drift_ms=%s "
            "target_y=%s",
            segment.sequence,
            actual_ms,
            drift_ms,
            round(self._scroll_top, 1),
        )

    async def close(self) -> None:
        if self._closed:
            return
        await self._stop_speech_sync()
        self._closed = True
        self._render_event.set()
        async with self._render_condition:
            self._render_condition.notify_all()
        worker = self._render_worker
        if worker is not None and worker is not asyncio.current_task():
            await asyncio.gather(worker, return_exceptions=True)
        self._render_worker = None

    async def render(self) -> None:
        if self._closed:
            return
        self._render_requested += 1
        requested = self._render_requested
        if self._render_worker is None or self._render_worker.done():
            self._render_worker = asyncio.create_task(
                self._run_render_worker(),
                name="chatbot-display",
            )
        self._render_event.set()
        async with self._render_condition:
            await self._render_condition.wait_for(
                lambda: self._render_completed >= requested or self._closed
            )
        error = self._render_error
        if error is not None and requested <= error[0]:
            raise error[1]

    async def _run_render_worker(self) -> None:
        interval = 1 / DISPLAY_MAX_FPS
        while not self._closed:
            await self._render_event.wait()
            self._render_event.clear()
            if self._closed:
                break
            if self._render_completed >= self._render_requested:
                continue
            remaining = interval - (time.monotonic() - self._last_render_at)
            if remaining > 0:
                await asyncio.sleep(remaining)
            requested = self._render_requested
            try:
                await self._render_once()
            except Exception as exc:
                self._render_error = (requested, exc)
            else:
                self._render_error = None
            self._last_render_at = time.monotonic()
            async with self._render_condition:
                self._render_completed = max(self._render_completed, requested)
                self._render_condition.notify_all()
            if self._render_requested > self._render_completed:
                self._render_event.set()

    async def _render_once(self) -> None:
        canvas = Canvas(width=self.frame.width, height=self.frame.height)
        actions = CONTROL_LABELS if self._state.get("actions", True) else None
        if self._state.get("kind") == "chat":
            canvas.chat_page(
                TITLE,
                self._state.get("messages", []),
                status=self._state.get("status"),
                streaming=bool(self._state.get("streaming")),
                actions=actions,
                selected=self.selected,
            )
        elif self._state.get("kind") == "answer":
            canvas.scrolling_text_page(
                TITLE,
                str(self._state.get("text", "")),
                scroll_top=self._scroll_top,
                status=self._state.get("status"),
                actions=actions,
                selected=self.selected,
            )
        else:
            canvas.text_page(
                TITLE,
                str(self._state.get("text", "")),
                status=self._state.get("status"),
                actions=actions,
                selected=self.selected,
                emphasis=str(self._state.get("emphasis", "primary")),
            )
        await canvas.present(self.frame)

    async def _animate_speech_segment(self, segment: SpeechSegment) -> None:
        assert segment.duration_ms is not None
        duration_sec = segment.duration_ms / 1000
        started_at = self._scroll_started_at or time.monotonic()
        start_top = self._scroll_top
        revision = -1
        target = start_top
        try:
            while True:
                elapsed = time.monotonic() - started_at
                progress = min(1.0, max(0.0, elapsed / duration_sec))
                if revision != self._answer_revision:
                    revision = self._answer_revision
                    target = max(start_top, self._scroll_target(segment.display_end))
                next_top = start_top + (target - start_top) * progress
                if abs(next_top - self._scroll_top) >= 0.5:
                    self._scroll_top = next_top
                    await self.render()
                if progress >= 1.0:
                    return
                await asyncio.sleep(1 / DISPLAY_MAX_FPS)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "stage=display_sync event=animation_failed sequence=%s",
                segment.sequence,
            )

    def _scroll_target(self, char_end: int) -> float:
        if self._state.get("kind") != "answer":
            return 0.0
        canvas = Canvas(width=self.frame.width, height=self.frame.height)
        text_y = 70 if self._state.get("status") else 58
        content_height = self.frame.height - text_y - (
            58 if self._state.get("actions", True) else 14
        )
        return canvas.text_scroll_target(
            str(self._state.get("text", "")),
            char_end,
            width=self.frame.width - 44,
            height=content_height,
            focus_ratio=SCROLL_FOCUS_RATIO,
        )

    async def _stop_speech_sync(self) -> None:
        task = self._scroll_task
        self._scroll_task = None
        self._scroll_sequence = None
        self._scroll_started_at = None
        if task is not None and not task.done():
            task.cancel()
        if task is not None and task is not asyncio.current_task():
            await asyncio.gather(task, return_exceptions=True)


async def main() -> None:
    log_path = configure_ai_logging(
        logger.name,
        default_path=Path(".runtime") / "chatbot.log",
    )
    app = await DeviceApp.connect_from_environment(timeout=120)
    await app.acquire_foreground()
    frame = await app.frames.acquire()
    display = ChatbotDisplay(frame)
    try:
        providers = providers_from_environment(
            fake_transcript="What can this platform do?",
            fake_response=(
                "This portable platform can run voice chat, translation, "
                "and small interactive applications."
            ),
            require_explicit=True,
        )
    except Exception as exc:
        logger.exception("event=configuration_invalid")
        await display.show_configuration_error(exc)
        await _wait_for_exit(app)
        try:
            await display.close()
        finally:
            await app.close()
        return
    pipeline = StreamingSpeechPipeline(providers.llm, providers.tts)
    history: list[Message] = []
    recording: RecordingSession | None = None
    turn_task: asyncio.Task[None] | None = None
    hold_task: asyncio.Task[None] | None = None
    pending_click_task: asyncio.Task[None] | None = None
    pressed = False
    hold_triggered = False
    selected_action = ACTION_TALK
    logger.info(
        "event=app_started log_path=%s asr=%s llm=%s tts=%s",
        log_path,
        type(providers.asr).__name__,
        type(providers.llm).__name__,
        type(providers.tts).__name__,
    )

    async def set_selected_action(index: int) -> None:
        nonlocal selected_action
        selected_action = index
        with contextlib.suppress(Exception):
            await display.set_selected(index)

    async def commit_single_click() -> None:
        nonlocal pending_click_task
        try:
            await asyncio.sleep(CLICK_INTERVAL_SEC)
            await set_selected_action(
                ACTION_BACK if selected_action == ACTION_TALK else ACTION_TALK
            )
        finally:
            pending_click_task = None

    async def handle_short_click() -> bool:
        nonlocal pending_click_task
        if pending_click_task is not None and not pending_click_task.done():
            pending_click_task.cancel()
            await asyncio.gather(pending_click_task, return_exceptions=True)
            pending_click_task = None
            if selected_action == ACTION_BACK:
                logger.info("event=back_confirmed")
                return True
            return False
        pending_click_task = asyncio.create_task(
            commit_single_click(),
            name="chatbot-single-click",
        )
        return False

    async def start_recording_after_hold() -> None:
        nonlocal hold_triggered, recording, turn_task
        await asyncio.sleep(HOLD_THRESHOLD_SEC)
        hold_triggered = True
        if selected_action != ACTION_TALK or recording is not None:
            return
        logger.info("stage=recording event=hold_started")
        if turn_task is not None:
            await _cancel_turn(app, turn_task)
            turn_task = None
        try:
            recording = await app.audio.start_recording(max_duration_sec=30)
        except Exception as exc:
            logger.exception(
                "stage=recording event=start_failed error_type=%s",
                type(exc).__name__,
            )
            await display.show_audio_error("start", exc)
            return
        logger.info("stage=recording event=started")
        await display.show_listening()

    await display.show_idle()

    try:
        async for event in app.subscribe(
            events=[
                "button.raw_pressed",
                "button.raw_released",
                "app.exit_requested",
            ]
        ):
            name = event["event"]
            if name == "app.exit_requested":
                break

            if name == "button.raw_pressed" and not pressed:
                pressed = True
                hold_triggered = False
                if selected_action == ACTION_TALK and recording is None:
                    hold_task = asyncio.create_task(
                        start_recording_after_hold(),
                        name="chatbot-hold-record",
                    )
                continue

            if name == "button.raw_released" and pressed:
                pressed = False
                short_click = False
                if hold_task is not None:
                    if not hold_task.done():
                        if hold_triggered:
                            await asyncio.gather(
                                hold_task,
                                return_exceptions=True,
                            )
                        else:
                            hold_task.cancel()
                            await asyncio.gather(
                                hold_task,
                                return_exceptions=True,
                            )
                            short_click = True
                    else:
                        await asyncio.gather(
                            hold_task,
                            return_exceptions=True,
                        )
                    hold_task = None
                elif recording is None:
                    short_click = True

                if recording is None and short_click:
                    if await handle_short_click():
                        break
                    continue

            if name == "button.raw_released" and recording is not None:
                active_recording = recording
                recording = None
                try:
                    result = await active_recording.stop()
                except Exception as exc:
                    logger.exception(
                        "stage=recording event=stop_failed error_type=%s",
                        type(exc).__name__,
                    )
                    await display.show_audio_error("stop", exc)
                    continue
                logger.info(
                    "stage=recording event=stopped duration_ms=%s "
                    "size_bytes=%s",
                    result.get("duration_ms"),
                    result.get("size_bytes"),
                )
                turn_task = asyncio.create_task(
                    _run_turn(
                        app,
                        pipeline,
                        providers.asr,
                        history,
                        Path(result["path"]),
                        display,
                    ),
                    name="chatbot-turn",
                )
    finally:
        logger.info("event=app_stopping")
        try:
            if hold_task is not None:
                hold_task.cancel()
                await asyncio.gather(hold_task, return_exceptions=True)
            if pending_click_task is not None:
                pending_click_task.cancel()
                await asyncio.gather(pending_click_task, return_exceptions=True)
            if turn_task is not None:
                await _cancel_turn(app, turn_task)
        finally:
            try:
                await providers.aclose()
            except Exception as exc:
                logger.exception(
                    "stage=provider_shutdown event=failed error_type=%s",
                    type(exc).__name__,
                )
            finally:
                try:
                    await display.close()
                finally:
                    await app.close()


async def _run_turn(
    app: DeviceApp,
    pipeline: StreamingSpeechPipeline,
    asr: ASRProvider,
    history: list[Message],
    audio_path: Path,
    display: ChatbotDisplay,
) -> None:
    try:
        turn_started = time.monotonic()
        await display.show_status("Transcribing...", "thinking")
        logger.info(
            "stage=asr event=start path=%s size_bytes=%s",
            audio_path,
            audio_path.stat().st_size if audio_path.is_file() else None,
        )
        asr_started = time.monotonic()
        transcript = (await asr.transcribe(audio_path)).strip()
        logger.info(
            "stage=asr event=done duration_ms=%s chars=%s",
            int((time.monotonic() - asr_started) * 1000),
            len(transcript),
        )
        if not transcript:
            raise RuntimeError("No speech was recognized")

        prompt = [
            Message("system", SYSTEM_PROMPT),
            *history,
            Message("user", transcript),
        ]
        await display.show_question(transcript)

        async def on_text(text: str) -> None:
            await display.append_answer_text(text)

        async def play_audio(path: Path) -> None:
            await app.audio.play_file(path)

        async def on_playback_start(segment: SpeechSegment) -> None:
            await display.start_speech_segment(segment)

        async def on_playback_end(
            segment: SpeechSegment,
            completed: bool,
        ) -> None:
            await display.finish_speech_segment(segment, completed)

        response = await pipeline.run(
            prompt,
            on_text=on_text,
            play_audio=play_audio,
            output_directory=Path(".runtime") / "chatbot-tts",
            text_flush_interval=0.12,
            on_playback_start=on_playback_start,
            on_playback_end=on_playback_end,
        )
        if not response.strip():
            raise RuntimeError("The language model returned an empty response")
        history.extend(
            [
                Message("user", transcript),
                Message("assistant", response),
            ]
        )
        del history[:-MAX_HISTORY_MESSAGES]
        logger.info(
            "event=turn_completed duration_ms=%s response_chars=%s "
            "history_messages=%s",
            int((time.monotonic() - turn_started) * 1000),
            len(response),
            len(history),
        )
        await display.finish_answer()
    except asyncio.CancelledError:
        logger.info("event=turn_cancelled")
        raise
    except Exception as exc:
        stage = exc.stage if isinstance(exc, PipelineStageError) else "chatbot"
        sequence = (
            exc.sequence if isinstance(exc, PipelineStageError) else None
        )
        logger.exception(
            "event=turn_failed stage=%s sequence=%s error_type=%s",
            stage,
            sequence,
            type(exc).__name__,
        )
        await display.show_error(exc)


async def _cancel_turn(
    app: DeviceApp,
    task: asyncio.Task[None],
) -> None:
    if not task.done():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    with contextlib.suppress(Exception):
        await app.audio.stop()


async def _wait_for_exit(app: DeviceApp) -> None:
    async for event in app.subscribe(events=["app.exit_requested"]):
        if event["event"] == "app.exit_requested":
            return


if __name__ == "__main__":
    asyncio.run(main())
