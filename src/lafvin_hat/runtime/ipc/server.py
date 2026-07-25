from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import platform
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from lafvin_hat import __version__

from ..apps import AppManager
from ..apps.catalog import (
    AppCatalogError,
    default_project_root,
    load_first_party_app_catalog,
)
from ..audio import AudioService, FakeAudioBackend, LinuxAudioBackend
from ..audio.backends import AudioBackend
from ..backends import DeviceBackend, SimulatorBackend
from ..config import RuntimeEndpoint, default_data_dir, default_log_dir
from ..events import EventBus, EventSubscription
from ..frames import FrameService
from ..gestures import GestureService
from ..diagnostics import HardwareTestFlow
from ..shell import ShellService
from ..status import SystemStatusService
from ..system_apps import HardwareTestSystemApp, SystemAppRegistry
from ..ui import UIService
from .protocol import (
    MAX_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    ProtocolError,
    Request,
    decode_message,
    encode_message,
    error_response,
    parse_request,
    success_response,
)


Handler = Callable[[Request], Awaitable[dict[str, Any]]]
logger = logging.getLogger("lafvin_hat.runtime")
_DIAGNOSTIC_REFERENCE_AUDIO = Path("assets/audio/audio_test.wav")


class RuntimeServer:
    def __init__(
        self,
        endpoint: RuntimeEndpoint,
        *,
        backend: DeviceBackend | None = None,
        audio_backend: AudioBackend | None = None,
        data_dir: Path | None = None,
        log_dir: Path | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.backend = backend or SimulatorBackend(web_enabled=False)
        self._temporary_storage: tempfile.TemporaryDirectory[str] | None = None
        if data_dir is None and log_dir is None:
            self._temporary_storage = tempfile.TemporaryDirectory(
                prefix="lafvin-hat-runtime-"
            )
            temporary_root = Path(self._temporary_storage.name)
            data_dir = temporary_root / "data"
            log_dir = temporary_root / "logs"
        self._server: asyncio.AbstractServer | None = None
        self._started_at = 0.0
        self._event_bus = EventBus()
        self._app_manager = AppManager(
            self._event_bus,
            endpoint,
            data_dir=data_dir or default_data_dir(),
            log_dir=log_dir or default_log_dir(),
        )
        self._ui_service = UIService(
            self._app_manager,
            self.backend,
            self._event_bus,
        )
        self._frame_service = FrameService(
            self._app_manager,
            self.backend,
            self._event_bus,
        )
        self._audio_service = AudioService(
            self._app_manager,
            self._event_bus,
            audio_backend
            or (
                LinuxAudioBackend()
                if self.backend.requires_linux_audio
                else FakeAudioBackend()
            ),
        )
        self._system_status_service = SystemStatusService(
            self._app_manager,
            self._audio_service,
            self.backend,
            runtime_version=__version__,
            uptime_ms_provider=self._uptime_ms,
        )
        self._hardware_test_flow = HardwareTestFlow(
            self.backend,
            self._ui_service,
            self._audio_service,
        )
        self._system_apps = SystemAppRegistry(
            [HardwareTestSystemApp(self._hardware_test_flow)]
        )
        try:
            self._first_party_apps = load_first_party_app_catalog()
        except AppCatalogError as exc:
            raise RuntimeError(
                f"Cannot load first-party application catalog: {exc}"
            ) from exc
        self._shell_service = ShellService(
            self._app_manager,
            self._ui_service,
            self._event_bus,
            system_apps=self._system_apps,
            first_party_apps=self._first_party_apps,
        )
        self._gesture_service = GestureService(
            self._app_manager,
            self._event_bus,
            shell_active_provider=self._shell_service.is_system_panel_active,
        )
        self.backend.set_event_sink(self._handle_backend_event)
        self._handlers: dict[str, Handler] = {
            "runtime.ping": self._handle_ping,
            "runtime.info": self._handle_info,
            "runtime.status": self._handle_status,
            "app.install": self._handle_app_install,
            "app.uninstall": self._handle_app_uninstall,
            "app.logs": self._handle_app_logs,
            "app.list": self._handle_app_list,
            "app.launch": self._handle_app_launch,
            "app.register_session": self._handle_app_register_session,
            "app.acquire_foreground": self._handle_app_acquire_foreground,
            "app.release_foreground": self._handle_app_release_foreground,
            "app.stop": self._handle_app_stop,
            "ui.set_view": self._handle_ui_set_view,
            "ui.patch_view": self._handle_ui_patch_view,
            "ui.clear": self._handle_ui_clear,
            "frame.acquire": self._handle_frame_acquire,
            "frame.commit": self._handle_frame_commit,
            "frame.release": self._handle_frame_release,
            "audio.record.start": self._handle_audio_record_start,
            "audio.record.stop": self._handle_audio_record_stop,
            "audio.play": self._handle_audio_play,
            "audio.feedback.play": self._handle_audio_feedback_play,
            "audio.stop": self._handle_audio_stop,
            "audio.volume.get": self._handle_audio_volume_get,
            "audio.volume.set": self._handle_audio_volume_set,
            "diagnostics.audio.volume.set": (
                self._handle_diagnostics_audio_volume_set
            ),
            "diagnostics.audio.tone.play": (
                self._handle_diagnostics_audio_tone_play
            ),
            "diagnostics.audio.reference.play": (
                self._handle_diagnostics_audio_reference_play
            ),
            "device.get_state": self._handle_device_get_state,
            "device.set_led": self._handle_device_set_led,
            "device.set_backlight": self._handle_device_set_backlight,
            "simulator.button.set": self._handle_simulator_button_set,
            "simulator.state.set": self._handle_simulator_state_set,
        }

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def bound_endpoint(self) -> RuntimeEndpoint:
        if self._server is None or self.endpoint.kind != "tcp":
            return self.endpoint
        socket = self._server.sockets[0]
        host, port = socket.getsockname()[:2]
        return RuntimeEndpoint(kind="tcp", host=str(host), port=int(port))

    async def start(self) -> None:
        if self._server is not None:
            return

        if self.endpoint.kind == "unix":
            assert self.endpoint.path is not None
            await self._prepare_unix_socket(self.endpoint.path)
            self._server = await asyncio.start_unix_server(
                self._handle_client,
                path=str(self.endpoint.path),
                limit=MAX_MESSAGE_BYTES + 1,
            )
            with contextlib.suppress(OSError):
                os.chmod(self.endpoint.path, 0o660)
        else:
            self._server = await asyncio.start_server(
                self._handle_client,
                host=self.endpoint.host,
                port=self.endpoint.port,
                limit=MAX_MESSAGE_BYTES + 1,
            )

        self._app_manager.set_runtime_endpoint(self.bound_endpoint)
        try:
            await self._app_manager.start()
            await self.backend.start()
            await self._ui_service.start()
            await self._frame_service.start()
            await self._audio_service.start()
            await self._gesture_service.start()
            await self._shell_service.start()
        except Exception:
            await self._shell_service.stop()
            await self._gesture_service.stop()
            await self._audio_service.stop()
            await self._frame_service.stop()
            await self._ui_service.stop()
            await self.backend.stop()
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            raise
        self._started_at = time.monotonic()
        logger.info(
            "Runtime started endpoint=%s backend=%s data_dir=%s log_dir=%s",
            self.bound_endpoint.as_uri(),
            self.backend.name,
            self._app_manager.data_dir,
            self._app_manager.log_dir,
        )

    async def close(self) -> None:
        was_running = self._server is not None
        await self._shell_service.stop()
        await self._gesture_service.stop()
        await self._app_manager.close()
        await self._audio_service.stop()
        await self._frame_service.stop()
        await self._ui_service.stop()
        await self.backend.stop()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        if (
            was_running
            and self.endpoint.kind == "unix"
            and self.endpoint.path is not None
        ):
            with contextlib.suppress(FileNotFoundError):
                self.endpoint.path.unlink()
        if self._temporary_storage is not None:
            self._temporary_storage.cleanup()
            self._temporary_storage = None
        if was_running:
            logger.info("Runtime stopped")

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        await self._server.serve_forever()

    async def _prepare_unix_socket(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            return
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(path)),
                timeout=0.2,
            )
        except (OSError, asyncio.TimeoutError):
            path.unlink()
            return
        writer.close()
        await writer.wait_closed()
        raise RuntimeError(f"Runtime endpoint is already in use: {path}")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        subscription: EventSubscription | None = None
        try:
            while True:
                try:
                    line = await reader.readline()
                except ValueError:
                    response = error_response(
                        None,
                        "INVALID_REQUEST",
                        "Message exceeds the size limit",
                    )
                    writer.write(encode_message(response))
                    await writer.drain()
                    return
                if not line:
                    return
                response, subscription = await self._process_line(line)
                writer.write(encode_message(response))
                await writer.drain()
                if subscription is not None:
                    await self._stream_events(subscription, reader, writer)
                    return
        finally:
            if subscription is not None:
                self._event_bus.unsubscribe(subscription)
            writer.close()
            with contextlib.suppress(ConnectionError, BrokenPipeError):
                await writer.wait_closed()

    async def _process_line(
        self,
        line: bytes,
    ) -> tuple[dict[str, Any], EventSubscription | None]:
        request_id: str | None = None
        try:
            message = decode_message(line.rstrip(b"\r\n"))
            value = message.get("id")
            request_id = value if isinstance(value, str) else None
            request = parse_request(message)
            if request.method == "events.subscribe":
                subscription = self._create_subscription(request)
                return (
                    success_response(
                        request.request_id,
                        {
                            "subscribed": True,
                            "events": sorted(subscription.event_names),
                            "app_id": subscription.app_id,
                        },
                    ),
                    subscription,
                )
            handler = self._handlers.get(request.method)
            if handler is None:
                raise ProtocolError(
                    "METHOD_NOT_FOUND",
                    f"Unknown method: {request.method}",
                    request_id=request.request_id,
                )
            result = await handler(request)
            return success_response(request.request_id, result), None
        except ProtocolError as exc:
            return (
                error_response(
                    exc.request_id or request_id,
                    exc.code,
                    exc.message,
                ),
                None,
            )
        except Exception:
            logger.exception(
                "Unhandled Runtime request failure request_id=%s",
                request_id,
            )
            return (
                error_response(
                    request_id,
                    "INTERNAL_ERROR",
                    "The Runtime failed to process the request",
                ),
                None,
            )

    def _create_subscription(self, request: Request) -> EventSubscription:
        event_names_value = request.params.get("events", [])
        if not isinstance(event_names_value, list) or not all(
            isinstance(value, str) and value
            for value in event_names_value
        ):
            raise ProtocolError(
                "INVALID_REQUEST",
                "events must be an array of non-empty strings",
                request_id=request.request_id,
            )
        app_id_value = request.params.get("app_id")
        if app_id_value is not None and not isinstance(app_id_value, str):
            raise ProtocolError(
                "INVALID_REQUEST",
                "app_id must be a string",
                request_id=request.request_id,
            )
        return self._event_bus.subscribe(
            event_names=set(event_names_value),
            app_id=app_id_value,
        )

    async def _stream_events(
        self,
        subscription: EventSubscription,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        while True:
            event_task = asyncio.create_task(subscription.queue.get())
            disconnect_task = asyncio.create_task(reader.read(1))
            done, pending = await asyncio.wait(
                {event_task, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if disconnect_task in done:
                return
            event = event_task.result()
            writer.write(encode_message(event))
            try:
                await writer.drain()
            except (ConnectionError, BrokenPipeError):
                return

    async def _handle_ping(self, _request: Request) -> dict[str, Any]:
        return {
            "service": "lafvin-hat-runtime",
            "protocol_version": PROTOCOL_VERSION,
        }

    async def _handle_info(self, _request: Request) -> dict[str, Any]:
        return {
            "service": "lafvin-hat-runtime",
            "runtime_version": __version__,
            "protocol_version": PROTOCOL_VERSION,
            "python_version": platform.python_version(),
            "platform": platform.system().lower(),
            "endpoint": self.bound_endpoint.as_uri(),
            "backend": self.backend.name,
        }

    async def _handle_status(self, _request: Request) -> dict[str, Any]:
        uptime_ms = self._uptime_ms()
        return {
            "state": "running",
            "uptime_ms": uptime_ms,
            "foreground_app_id": self._app_manager.foreground_app_id,
            "running_apps": self._app_manager.running_app_ids(),
            "ui": self._ui_service.snapshot(),
            "frame": self._frame_service.snapshot(),
            "audio": self._audio_service.snapshot(),
            "system": await self._system_status_service.snapshot(
                uptime_ms=uptime_ms,
            ),
            "diagnostics": self._hardware_test_flow.snapshot(),
            "system_apps": self._system_apps.snapshot(),
            "gestures": self._gesture_service.snapshot(),
            "shell": self._shell_service.snapshot(),
            "backend": self.backend.state_snapshot(),
            "storage": {
                "data_dir": str(self._app_manager.data_dir),
                "log_dir": str(self._app_manager.log_dir),
            },
        }

    def _uptime_ms(self) -> int:
        return int(max(0.0, time.monotonic() - self._started_at) * 1000)

    async def _handle_app_install(self, request: Request) -> dict[str, Any]:
        source_path = self._required_string(request, "source_path")
        development = request.params.get("development", False)
        if not isinstance(development, bool):
            raise ProtocolError(
                "INVALID_REQUEST",
                "development must be a boolean",
                request_id=request.request_id,
            )
        if development:
            return await self._app_manager.register_development_app(
                Path(source_path)
            )
        return await self._app_manager.install_app(Path(source_path))

    async def _handle_app_uninstall(self, request: Request) -> dict[str, Any]:
        app_id = self._required_string(request, "app_id")
        await self._app_manager.unregister_app(app_id)
        return {"app_id": app_id}

    async def _handle_app_list(self, _request: Request) -> dict[str, Any]:
        return {"apps": self._app_manager.list_apps()}

    async def _handle_app_logs(self, request: Request) -> dict[str, Any]:
        lines = request.params.get("lines", 100)
        if not isinstance(lines, int) or isinstance(lines, bool):
            raise ProtocolError(
                "INVALID_REQUEST",
                "lines must be an integer",
                request_id=request.request_id,
            )
        return await self._app_manager.read_logs(
            self._required_string(request, "app_id"),
            lines=lines,
        )

    async def _handle_app_launch(self, request: Request) -> dict[str, Any]:
        return await self._app_manager.launch(
            self._required_string(request, "app_id")
        )

    async def _handle_app_register_session(
        self,
        request: Request,
    ) -> dict[str, Any]:
        return await self._app_manager.register_session(
            self._required_string(request, "app_id"),
            self._required_string(request, "instance_id"),
            self._required_string(request, "launch_token"),
        )

    async def _handle_app_acquire_foreground(
        self,
        request: Request,
    ) -> dict[str, Any]:
        return await self._app_manager.acquire_foreground(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
        )

    async def _handle_app_release_foreground(
        self,
        request: Request,
    ) -> dict[str, Any]:
        app_id = self._required_string(request, "app_id")
        await self._app_manager.release_foreground(
            app_id,
            self._required_string(request, "session_token"),
        )
        await self._ui_service.clear_for_app(app_id)
        await self._frame_service.invalidate_for_app(app_id)
        await self._audio_service.stop_for_app(app_id)
        return {"app_id": app_id}

    async def _handle_app_stop(self, request: Request) -> dict[str, Any]:
        app_id = self._required_string(request, "app_id")
        await self._app_manager.stop(app_id)
        await self._ui_service.clear_for_app(app_id)
        await self._frame_service.invalidate_for_app(app_id)
        await self._audio_service.stop_for_app(app_id)
        return {"app_id": app_id}

    async def _handle_ui_set_view(self, request: Request) -> dict[str, Any]:
        view = request.params.get("view")
        if not isinstance(view, dict):
            raise ProtocolError(
                "INVALID_REQUEST",
                "view must be an object",
                request_id=request.request_id,
            )
        return await self._ui_service.set_view(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
            view,
        )

    async def _handle_ui_patch_view(
        self,
        request: Request,
    ) -> dict[str, Any]:
        operations = request.params.get("operations")
        if not isinstance(operations, list):
            raise ProtocolError(
                "INVALID_REQUEST",
                "operations must be an array",
                request_id=request.request_id,
            )
        return await self._ui_service.patch_view(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
            operations,
        )

    async def _handle_ui_clear(self, request: Request) -> dict[str, Any]:
        return await self._ui_service.clear(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
        )

    async def _handle_frame_acquire(
        self,
        request: Request,
    ) -> dict[str, Any]:
        return await self._frame_service.acquire(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
        )

    async def _handle_frame_commit(
        self,
        request: Request,
    ) -> dict[str, Any]:
        return await self._frame_service.commit(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
            self._required_string(request, "frame_session"),
            self._required_integer(request, "sequence"),
            request.params.get("dirty_rects"),
            request.params.get("input_timestamp_ms"),
        )

    async def _handle_frame_release(
        self,
        request: Request,
    ) -> dict[str, Any]:
        return await self._frame_service.release(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
            self._required_string(request, "frame_session"),
        )

    async def _handle_audio_record_start(
        self,
        request: Request,
    ) -> dict[str, Any]:
        value = request.params.get("max_duration_sec", 30)
        return await self._audio_service.start_recording(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
            value,
        )

    async def _handle_audio_record_stop(
        self,
        request: Request,
    ) -> dict[str, Any]:
        return await self._audio_service.stop_recording(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
            self._required_string(request, "recording_session"),
        )

    async def _handle_audio_play(self, request: Request) -> dict[str, Any]:
        return await self._audio_service.play_file(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
            self._required_string(request, "path"),
        )

    async def _handle_audio_feedback_play(
        self,
        request: Request,
    ) -> dict[str, Any]:
        return await self._audio_service.play_feedback_tone(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
            kind=self._required_string(request, "kind"),
        )

    async def _handle_audio_stop(self, request: Request) -> dict[str, Any]:
        return await self._audio_service.stop_playback(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
        )

    async def _handle_audio_volume_get(
        self,
        request: Request,
    ) -> dict[str, Any]:
        return await self._audio_service.get_volume(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
        )

    async def _handle_audio_volume_set(
        self,
        request: Request,
    ) -> dict[str, Any]:
        return await self._audio_service.set_volume(
            self._required_string(request, "app_id"),
            self._required_string(request, "session_token"),
            self._required_integer(request, "value"),
        )

    async def _handle_diagnostics_audio_volume_set(
        self,
        request: Request,
    ) -> dict[str, Any]:
        """Set volume through the Runtime for a local diagnostic tool.

        This deliberately does not impersonate an App session. It is an
        operator-facing endpoint used by the mixer console while the Runtime
        remains the owner of the actual ALSA write.
        """

        value = await self._audio_service.set_system_volume(
            self._required_integer(request, "value")
        )
        return {"value": value}

    async def _handle_diagnostics_audio_tone_play(
        self,
        request: Request,
    ) -> dict[str, Any]:
        """Play a controlled Runtime-owned tone for mixer calibration."""

        frequency_hz = self._optional_bounded_integer(
            request,
            "frequency_hz",
            default=880,
            minimum=100,
            maximum=4_000,
        )
        duration_ms = self._optional_bounded_integer(
            request,
            "duration_ms",
            default=700,
            minimum=100,
            maximum=5_000,
        )
        self._require_diagnostic_playback_idle(request)
        result = await self._audio_service.play_system_tone(
            frequency_hz=frequency_hz,
            duration_ms=duration_ms,
        )
        return {
            **result,
            "frequency_hz": frequency_hz,
            "duration_ms": duration_ms,
        }

    async def _handle_diagnostics_audio_reference_play(
        self,
        request: Request,
    ) -> dict[str, Any]:
        """Play the fixed checkout-owned speech reference through Runtime."""

        self._require_diagnostic_playback_idle(request)
        path = default_project_root() / _DIAGNOSTIC_REFERENCE_AUDIO
        if not path.is_file():
            raise ProtocolError(
                "RESOURCE_NOT_FOUND",
                "Diagnostic reference audio is missing: "
                f"{_DIAGNOSTIC_REFERENCE_AUDIO.as_posix()}",
                request_id=request.request_id,
            )
        result = await self._audio_service.play_system_file(path)
        return {
            **result,
            "resource": _DIAGNOSTIC_REFERENCE_AUDIO.as_posix(),
        }

    async def _handle_device_get_state(
        self,
        _request: Request,
    ) -> dict[str, Any]:
        return self.backend.state_snapshot()

    async def _handle_device_set_led(
        self,
        request: Request,
    ) -> dict[str, Any]:
        await self.backend.set_led(
            self._required_integer(request, "r"),
            self._required_integer(request, "g"),
            self._required_integer(request, "b"),
        )
        return self.backend.state_snapshot()

    async def _handle_device_set_backlight(
        self,
        request: Request,
    ) -> dict[str, Any]:
        await self.backend.set_backlight(
            self._required_integer(request, "value")
        )
        return self.backend.state_snapshot()

    async def _handle_simulator_button_set(
        self,
        request: Request,
    ) -> dict[str, Any]:
        backend = self._require_simulator(request)
        pressed = request.params.get("pressed")
        if not isinstance(pressed, bool):
            raise ProtocolError(
                "INVALID_REQUEST",
                "pressed must be a boolean",
                request_id=request.request_id,
            )
        await backend.inject_button(pressed)
        return backend.state_snapshot()

    async def _handle_simulator_state_set(
        self,
        request: Request,
    ) -> dict[str, Any]:
        backend = self._require_simulator(request)
        await backend.set_simulated_state(
            battery_level=request.params.get("battery_level"),
            charging=request.params.get("charging"),
            network_online=request.params.get("network_online"),
        )
        return backend.state_snapshot()

    async def _handle_backend_event(
        self,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        foreground_app_id = self._app_manager.foreground_app_id
        await self._event_bus.emit(
            event_name,
            payload,
            app_id=foreground_app_id,
        )
        await self._gesture_service.handle_raw_event(event_name, payload)

    def _required_string(self, request: Request, name: str) -> str:
        value = request.params.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ProtocolError(
                "INVALID_REQUEST",
                f"{name} must be a non-empty string",
                request_id=request.request_id,
            )
        return value.strip()

    def _required_integer(self, request: Request, name: str) -> int:
        value = request.params.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProtocolError(
                "INVALID_REQUEST",
                f"{name} must be an integer",
                request_id=request.request_id,
            )
        return value

    def _optional_bounded_integer(
        self,
        request: Request,
        name: str,
        *,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        value = request.params.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProtocolError(
                "INVALID_REQUEST",
                f"{name} must be an integer",
                request_id=request.request_id,
            )
        if not minimum <= value <= maximum:
            raise ProtocolError(
                "INVALID_REQUEST",
                f"{name} must be between {minimum} and {maximum}",
                request_id=request.request_id,
            )
        return value

    def _require_diagnostic_playback_idle(self, request: Request) -> None:
        active_playback = self._audio_service.snapshot().get(
            "playing_app_id"
        )
        if active_playback is not None:
            raise ProtocolError(
                "AUDIO_BUSY",
                "Cannot play diagnostic audio while audio playback is active",
                request_id=request.request_id,
            )

    def _require_simulator(self, request: Request) -> SimulatorBackend:
        if not isinstance(self.backend, SimulatorBackend):
            raise ProtocolError(
                "METHOD_NOT_FOUND",
                "Simulator controls are unavailable for this backend",
                request_id=request.request_id,
            )
        return self.backend
