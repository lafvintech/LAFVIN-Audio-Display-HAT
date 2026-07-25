from __future__ import annotations

from typing import Any

from .client import RuntimeClient


class UIClient:
    def __init__(
        self,
        client: RuntimeClient,
        app_id: str,
        session_token: str,
    ) -> None:
        self._client = client
        self._session = {
            "app_id": app_id,
            "session_token": session_token,
        }

    async def set_view(self, view: dict[str, Any]) -> dict[str, Any]:
        return await self._client.request(
            "ui.set_view",
            {**self._session, "view": view},
        )

    async def patch_view(
        self,
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._client.request(
            "ui.patch_view",
            {**self._session, "operations": operations},
        )

    async def clear(self) -> dict[str, Any]:
        return await self._client.request("ui.clear", self._session)
