from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from lafvin_hat.runtime.config import (
    RuntimeEndpoint,
    default_runtime_endpoint,
    parse_endpoint,
)

from .client import RuntimeClient, RuntimeClientError
from .audio import AudioClient
from .frames import FrameClient
from .ui import UIClient


@dataclass(slots=True)
class DeviceApp:
    app_id: str
    instance_id: str
    session_token: str
    permissions: frozenset[str]
    client: RuntimeClient
    _foreground: bool = False
    _frame_client: FrameClient | None = None
    _audio_client: AudioClient | None = None

    @classmethod
    async def connect_from_environment(
        cls,
        *,
        timeout: float = 5.0,
    ) -> "DeviceApp":
        endpoint_value = os.getenv("LAFVIN_RUNTIME_ENDPOINT")
        endpoint = (
            parse_endpoint(endpoint_value)
            if endpoint_value
            else default_runtime_endpoint()
        )
        return await cls.connect(
            endpoint=endpoint,
            app_id=_required_env("LAFVIN_APP_ID"),
            instance_id=_required_env("LAFVIN_INSTANCE_ID"),
            launch_token=_required_env("LAFVIN_LAUNCH_TOKEN"),
            timeout=timeout,
        )

    @classmethod
    async def connect(
        cls,
        *,
        endpoint: RuntimeEndpoint,
        app_id: str,
        instance_id: str,
        launch_token: str,
        timeout: float = 5.0,
    ) -> "DeviceApp":
        client = RuntimeClient(endpoint, timeout=timeout)
        result = await client.request(
            "app.register_session",
            {
                "app_id": app_id,
                "instance_id": instance_id,
                "launch_token": launch_token,
            },
        )
        return cls(
            app_id=app_id,
            instance_id=instance_id,
            session_token=result["session_token"],
            permissions=frozenset(result.get("permissions", [])),
            client=client,
        )

    async def acquire_foreground(self) -> dict[str, Any]:
        result = await self.client.request(
            "app.acquire_foreground",
            self._session_params(),
        )
        self._foreground = True
        return result

    async def release_foreground(self) -> None:
        if not self._foreground:
            return
        try:
            await self.client.request(
                "app.release_foreground",
                self._session_params(),
            )
        except RuntimeClientError as exc:
            if exc.code not in {"APP_NOT_FOREGROUND", "INVALID_SESSION"}:
                raise
        finally:
            self._foreground = False

    def subscribe(
        self,
        *,
        events: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        return self.client.subscribe(events=events, app_id=self.app_id)

    async def close(self) -> None:
        if self._audio_client is not None:
            await self._audio_client.close()
        if self._frame_client is not None:
            await self._frame_client.close()
        await self.release_foreground()

    @property
    def ui(self) -> UIClient:
        return UIClient(self.client, self.app_id, self.session_token)

    @property
    def frames(self) -> FrameClient:
        if self._frame_client is None:
            self._frame_client = FrameClient(
                self.client,
                self.app_id,
                self.session_token,
            )
        return self._frame_client

    @property
    def audio(self) -> AudioClient:
        if self._audio_client is None:
            self._audio_client = AudioClient(
                self.client,
                self.app_id,
                self.session_token,
            )
        return self._audio_client

    async def __aenter__(self) -> "DeviceApp":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    def _session_params(self) -> dict[str, str]:
        return {
            "app_id": self.app_id,
            "session_token": self.session_token,
        }


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing Runtime launch environment variable: {name}")
    return value
