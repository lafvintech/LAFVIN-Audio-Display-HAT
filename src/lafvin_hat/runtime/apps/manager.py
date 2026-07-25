from __future__ import annotations

import asyncio
import contextlib
import os
import secrets
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from ..config import RuntimeEndpoint
from ..events import EventBus
from ..ipc.protocol import ProtocolError
from .manifest import AppManifest, ManifestError, load_manifest


@dataclass(slots=True)
class AppRecord:
    manifest: AppManifest
    development: bool = False
    state: str = "installed"
    process: asyncio.subprocess.Process | None = None
    instance_id: str | None = None
    launch_token: str | None = None
    session_token: str | None = None
    monitor_task: asyncio.Task[None] | None = None
    stop_requested: bool = False
    exit_code: int | None = None
    log_path: Path | None = None
    log_handle: BinaryIO | None = None

    def public_state(self, *, foreground: bool) -> dict[str, Any]:
        return {
            **self.manifest.to_public_dict(),
            "state": self.state,
            "instance_id": self.instance_id,
            "pid": self.process.pid if self.process is not None else None,
            "foreground": foreground,
            "exit_code": self.exit_code,
            "development": self.development,
            "log_path": str(self.log_path) if self.log_path else None,
        }


class AppManager:
    def __init__(
        self,
        event_bus: EventBus,
        runtime_endpoint: RuntimeEndpoint,
        *,
        data_dir: Path,
        log_dir: Path,
    ) -> None:
        self._event_bus = event_bus
        self._runtime_endpoint = runtime_endpoint
        self._data_dir = data_dir.resolve()
        self._apps_dir = self._data_dir / "apps"
        self._log_dir = log_dir.resolve()
        self._apps: dict[str, AppRecord] = {}
        self._foreground_app_id: str | None = None
        self._lock = asyncio.Lock()

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    async def start(self) -> None:
        self._apps_dir.mkdir(parents=True, exist_ok=True)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        loaded: dict[str, AppRecord] = {}
        for app_dir in sorted(self._apps_dir.iterdir()):
            if not app_dir.is_dir() or app_dir.name.startswith("."):
                continue
            try:
                manifest = load_manifest(app_dir)
            except ManifestError as exc:
                raise RuntimeError(
                    f"Installed app is invalid at {app_dir}: {exc}"
                ) from exc
            if manifest.app_id in loaded:
                raise RuntimeError(
                    f"Duplicate installed app ID: {manifest.app_id}"
                )
            loaded[manifest.app_id] = AppRecord(
                manifest=manifest,
                log_path=self._log_path_for(manifest.app_id),
            )
        async with self._lock:
            self._apps.update(loaded)

    def set_runtime_endpoint(self, endpoint: RuntimeEndpoint) -> None:
        self._runtime_endpoint = endpoint

    @property
    def foreground_app_id(self) -> str | None:
        return self._foreground_app_id

    def list_apps(self) -> list[dict[str, Any]]:
        return [
            record.public_state(foreground=app_id == self._foreground_app_id)
            for app_id, record in sorted(self._apps.items())
        ]

    def running_app_ids(self) -> list[str]:
        return [
            app_id
            for app_id, record in self._apps.items()
            if record.state in {"starting", "running", "foreground", "stopping"}
        ]

    async def authorize(
        self,
        app_id: str,
        session_token: str,
        *,
        permission: str,
        require_foreground: bool = False,
        ui_mode: str | None = None,
    ) -> Path:
        async with self._lock:
            record = self._require_session(app_id, session_token)
            if permission not in record.manifest.permissions:
                raise ProtocolError(
                    "PERMISSION_DENIED",
                    f"App lacks permission: {permission}",
                )
            if require_foreground and self._foreground_app_id != app_id:
                raise ProtocolError(
                    "APP_NOT_FOREGROUND",
                    f"App does not own foreground: {app_id}",
                )
            if ui_mode is not None and record.manifest.ui_mode != ui_mode:
                raise ProtocolError(
                    "UI_MODE_MISMATCH",
                    f"App UI mode must be {ui_mode}",
                )
            return record.manifest.source_path

    async def register_development_app(self, source_path: Path) -> dict[str, Any]:
        try:
            manifest = load_manifest(source_path)
        except ManifestError as exc:
            raise ProtocolError("INVALID_REQUEST", str(exc)) from exc
        async with self._lock:
            existing = self._apps.get(manifest.app_id)
            if existing and existing.process is not None:
                raise ProtocolError(
                    "APP_ALREADY_RUNNING",
                    f"Cannot replace running app: {manifest.app_id}",
                )
            self._apps[manifest.app_id] = AppRecord(
                manifest=manifest,
                development=True,
                log_path=self._log_path_for(manifest.app_id),
            )
        await self._event_bus.emit(
            "app.installed",
            {"app_id": manifest.app_id, "development": True},
            app_id=manifest.app_id,
        )
        return self._apps[manifest.app_id].public_state(foreground=False)

    async def install_app(self, source_path: Path) -> dict[str, Any]:
        from .provision import provision_app

        try:
            source_manifest = load_manifest(source_path)
        except ManifestError as exc:
            raise ProtocolError("INVALID_REQUEST", str(exc)) from exc
        async with self._lock:
            existing = self._apps.get(source_manifest.app_id)
            if existing and existing.process is not None:
                raise ProtocolError(
                    "APP_ALREADY_RUNNING",
                    f"Cannot replace running app: {source_manifest.app_id}",
                )
            try:
                manifest = await asyncio.to_thread(
                    provision_app,
                    source_path,
                    self._apps_dir,
                )
            except (OSError, ManifestError) as exc:
                raise ProtocolError(
                    "RESOURCE_UNAVAILABLE",
                    f"Failed to install app: {exc}",
                ) from exc

            self._apps[manifest.app_id] = AppRecord(
                manifest=manifest,
                log_path=self._log_path_for(manifest.app_id),
            )

        await self._event_bus.emit(
            "app.installed",
            {"app_id": manifest.app_id, "development": False},
            app_id=manifest.app_id,
        )
        return self._apps[manifest.app_id].public_state(foreground=False)

    async def unregister_app(self, app_id: str) -> None:
        async with self._lock:
            record = self._require_app(app_id)
            if record.process is not None:
                raise ProtocolError(
                    "APP_ALREADY_RUNNING",
                    f"Stop app before uninstalling: {app_id}",
                )
            source_path = record.manifest.source_path
            development = record.development
            del self._apps[app_id]
            if not development and source_path.parent == self._apps_dir:
                try:
                    await asyncio.to_thread(shutil.rmtree, source_path)
                except OSError as exc:
                    self._apps[app_id] = record
                    raise ProtocolError(
                        "RESOURCE_UNAVAILABLE",
                        f"Failed to remove installed app: {exc}",
                    ) from exc
        await self._event_bus.emit(
            "app.uninstalled",
            {"app_id": app_id},
            app_id=app_id,
        )

    async def read_logs(self, app_id: str, *, lines: int = 100) -> dict[str, Any]:
        async with self._lock:
            record = self._require_app(app_id)
            log_path = record.log_path or self._log_path_for(app_id)
        lines = max(1, min(2000, lines))
        if not log_path.is_file():
            content: list[str] = []
        else:
            text = await asyncio.to_thread(
                log_path.read_text,
                encoding="utf-8",
                errors="replace",
            )
            content = text.splitlines()[-lines:]
        return {
            "app_id": app_id,
            "path": str(log_path),
            "lines": content,
        }

    async def launch(self, app_id: str) -> dict[str, Any]:
        async with self._lock:
            record = self._require_app(app_id)
            if record.process is not None and record.process.returncode is None:
                raise ProtocolError(
                    "APP_ALREADY_RUNNING",
                    f"App is already running: {app_id}",
                )

            working_directory = self._resolve_working_directory(record.manifest)
            executable = self._resolve_executable(record.manifest)
            instance_id = uuid.uuid4().hex
            launch_token = secrets.token_urlsafe(32)
            env = os.environ.copy()
            env.update(
                {
                    "LAFVIN_RUNTIME_ENDPOINT": self._runtime_endpoint.as_uri(),
                    "LAFVIN_APP_ID": app_id,
                    "LAFVIN_INSTANCE_ID": instance_id,
                    "LAFVIN_LAUNCH_TOKEN": launch_token,
                    "PYTHONUNBUFFERED": "1",
                }
            )
            self._log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self._log_path_for(app_id)
            log_handle = log_path.open("ab", buffering=0)
            timestamp = datetime.now(timezone.utc).isoformat()
            log_handle.write(
                f"\n[{timestamp}] app launch instance={instance_id}\n".encode()
            )
            try:
                process = await asyncio.create_subprocess_exec(
                    executable,
                    *record.manifest.entrypoint.args,
                    cwd=str(working_directory),
                    env=env,
                    stdout=log_handle,
                    stderr=asyncio.subprocess.STDOUT,
                )
            except OSError as exc:
                log_handle.close()
                raise ProtocolError(
                    "RESOURCE_UNAVAILABLE",
                    f"Failed to launch app {app_id}: {exc}",
                ) from exc

            record.process = process
            record.instance_id = instance_id
            record.launch_token = launch_token
            record.session_token = None
            record.stop_requested = False
            record.exit_code = None
            record.log_path = log_path
            record.log_handle = log_handle
            record.state = "starting"
            record.monitor_task = asyncio.create_task(
                self._monitor_process(app_id, process),
                name=f"app-monitor:{app_id}",
            )

        await self._event_bus.emit(
            "app.started",
            {
                "app_id": app_id,
                "instance_id": instance_id,
                "pid": process.pid,
            },
            app_id=app_id,
        )
        return record.public_state(foreground=False)

    async def register_session(
        self,
        app_id: str,
        instance_id: str,
        launch_token: str,
    ) -> dict[str, Any]:
        async with self._lock:
            record = self._require_app(app_id)
            if (
                record.process is None
                or record.instance_id != instance_id
                or not secrets.compare_digest(record.launch_token or "", launch_token)
            ):
                raise ProtocolError(
                    "INVALID_SESSION",
                    "Launch credentials are invalid",
                )
            session_token = secrets.token_urlsafe(32)
            record.session_token = session_token
            record.launch_token = None
            record.state = "running"
        await self._event_bus.emit(
            "app.session_registered",
            {"app_id": app_id, "instance_id": instance_id},
            app_id=app_id,
        )
        return {
            "app_id": app_id,
            "instance_id": instance_id,
            "session_token": session_token,
            "permissions": sorted(record.manifest.permissions),
        }

    async def acquire_foreground(
        self,
        app_id: str,
        session_token: str,
    ) -> dict[str, Any]:
        async with self._lock:
            record = self._require_session(app_id, session_token)
            if (
                self._foreground_app_id is not None
                and self._foreground_app_id != app_id
            ):
                raise ProtocolError(
                    "FOREGROUND_BUSY",
                    f"Foreground is owned by {self._foreground_app_id}",
                )
            self._foreground_app_id = app_id
            record.state = "foreground"
        await self._event_bus.emit(
            "app.foreground_acquired",
            {"app_id": app_id, "instance_id": record.instance_id},
            app_id=app_id,
        )
        return record.public_state(foreground=True)

    async def release_foreground(
        self,
        app_id: str,
        session_token: str,
        *,
        reason: str = "app_release",
    ) -> None:
        async with self._lock:
            record = self._require_session(app_id, session_token)
            if self._foreground_app_id != app_id:
                raise ProtocolError(
                    "APP_NOT_FOREGROUND",
                    f"App does not own foreground: {app_id}",
                )
            self._foreground_app_id = None
            if not record.stop_requested:
                record.state = "running"
        await self._event_bus.emit(
            "app.foreground_revoked",
            {"app_id": app_id, "reason": reason},
            app_id=app_id,
        )

    async def stop(self, app_id: str) -> None:
        async with self._lock:
            record = self._require_app(app_id)
            process = record.process
            if process is None or process.returncode is not None:
                raise ProtocolError("APP_NOT_RUNNING", f"App is not running: {app_id}")
            record.stop_requested = True
            record.state = "stopping"
            timeout = record.manifest.lifecycle.exit_timeout_sec

        await self._event_bus.emit(
            "app.exit_requested",
            {"app_id": app_id, "reason": "runtime_stop"},
            app_id=app_id,
        )
        try:
            await asyncio.wait_for(
                asyncio.shield(process.wait()),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.terminate()
            try:
                await asyncio.wait_for(
                    asyncio.shield(process.wait()),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def close(self) -> None:
        for app_id in list(self.running_app_ids()):
            with contextlib.suppress(ProtocolError, ProcessLookupError):
                await self.stop(app_id)
        monitor_tasks = [
            record.monitor_task
            for record in self._apps.values()
            if record.monitor_task is not None
        ]
        if monitor_tasks:
            await asyncio.gather(*monitor_tasks, return_exceptions=True)

    async def _monitor_process(
        self,
        app_id: str,
        process: asyncio.subprocess.Process,
    ) -> None:
        return_code = await process.wait()
        async with self._lock:
            record = self._apps.get(app_id)
            if record is None or record.process is not process:
                return
            was_foreground = self._foreground_app_id == app_id
            if was_foreground:
                self._foreground_app_id = None
            stopped_cleanly = record.stop_requested or return_code == 0
            event_name = "app.stopped" if stopped_cleanly else "app.crashed"
            record.state = "stopped" if stopped_cleanly else "crashed"
            record.exit_code = return_code
            record.process = None
            record.instance_id = None
            record.launch_token = None
            record.session_token = None
            log_handle, record.log_handle = record.log_handle, None

        if was_foreground:
            await self._event_bus.emit(
                "app.foreground_revoked",
                {"app_id": app_id, "reason": "process_exit"},
                app_id=app_id,
            )
        await self._event_bus.emit(
            event_name,
            {"app_id": app_id, "exit_code": return_code},
            app_id=app_id,
        )
        if log_handle is not None:
            log_handle.close()

    def _log_path_for(self, app_id: str) -> Path:
        return self._log_dir / f"{app_id}.log"

    def _require_app(self, app_id: str) -> AppRecord:
        record = self._apps.get(app_id)
        if record is None:
            raise ProtocolError("APP_NOT_FOUND", f"Unknown app: {app_id}")
        return record

    def _require_session(self, app_id: str, session_token: str) -> AppRecord:
        record = self._require_app(app_id)
        if (
            not record.session_token
            or not secrets.compare_digest(record.session_token, session_token)
        ):
            raise ProtocolError("INVALID_SESSION", "App session is invalid")
        return record

    def _resolve_working_directory(self, manifest: AppManifest) -> Path:
        app_root = manifest.source_path
        candidate = (app_root / manifest.entrypoint.working_directory).resolve()
        if candidate != app_root and app_root not in candidate.parents:
            raise ProtocolError(
                "INVALID_REQUEST",
                "Entrypoint working directory escapes the app directory",
            )
        if not candidate.is_dir():
            raise ProtocolError(
                "INVALID_REQUEST",
                f"Entrypoint working directory does not exist: {candidate}",
            )
        return candidate

    def _resolve_executable(self, manifest: AppManifest) -> str:
        executable = manifest.entrypoint.executable
        if executable in {"python", "python3"}:
            return sys.executable
        if "/" not in executable and "\\" not in executable:
            return executable
        candidate = (manifest.source_path / executable).resolve()
        if candidate != manifest.source_path and manifest.source_path not in candidate.parents:
            raise ProtocolError(
                "INVALID_REQUEST",
                "Entrypoint executable escapes the app directory",
            )
        return str(candidate)
