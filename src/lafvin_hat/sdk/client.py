from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from lafvin_hat.runtime.config import RuntimeEndpoint
from lafvin_hat.runtime.ipc.protocol import (
    PROTOCOL_VERSION,
    decode_message,
    encode_message,
)


class RuntimeClientError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RuntimeClient:
    def __init__(
        self,
        endpoint: RuntimeEndpoint,
        *,
        timeout: float = 5.0,
    ) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reader, writer = await asyncio.wait_for(
            self._connect(),
            timeout=self.timeout,
        )
        request_id = uuid.uuid4().hex
        request = {
            "version": PROTOCOL_VERSION,
            "id": request_id,
            "type": "request",
            "method": method,
            "params": params or {},
        }

        try:
            writer.write(encode_message(request))
            await asyncio.wait_for(writer.drain(), timeout=self.timeout)
            line = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
            if not line:
                raise RuntimeClientError(
                    "CONNECTION_CLOSED",
                    "Runtime closed the connection without a response",
                )
            response = json.loads(line.decode("utf-8"))
        finally:
            writer.close()
            await writer.wait_closed()

        if response.get("id") != request_id:
            raise RuntimeClientError(
                "INVALID_RESPONSE",
                "Runtime response id does not match the request",
            )
        if not response.get("ok"):
            error = response.get("error") or {}
            raise RuntimeClientError(
                str(error.get("code") or "UNKNOWN_ERROR"),
                str(error.get("message") or "Runtime request failed"),
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeClientError(
                "INVALID_RESPONSE",
                "Runtime result must be an object",
            )
        return result

    async def ping(self) -> dict[str, Any]:
        return await self.request("runtime.ping")

    async def subscribe(
        self,
        *,
        events: list[str] | None = None,
        app_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        reader, writer = await asyncio.wait_for(
            self._connect(),
            timeout=self.timeout,
        )
        request_id = uuid.uuid4().hex
        params: dict[str, Any] = {"events": events or []}
        if app_id is not None:
            params["app_id"] = app_id
        writer.write(
            encode_message(
                {
                    "version": PROTOCOL_VERSION,
                    "id": request_id,
                    "type": "request",
                    "method": "events.subscribe",
                    "params": params,
                }
            )
        )
        try:
            await asyncio.wait_for(writer.drain(), timeout=self.timeout)
            ack_line = await asyncio.wait_for(
                reader.readline(),
                timeout=self.timeout,
            )
            if not ack_line:
                raise RuntimeClientError(
                    "CONNECTION_CLOSED",
                    "Runtime closed the event stream before acknowledgement",
                )
            ack = decode_message(ack_line.rstrip(b"\r\n"))
            if ack.get("id") != request_id or not ack.get("ok"):
                error = ack.get("error") or {}
                raise RuntimeClientError(
                    str(error.get("code") or "INVALID_RESPONSE"),
                    str(error.get("message") or "Event subscription failed"),
                )
            while True:
                line = await reader.readline()
                if not line:
                    return
                event = decode_message(line.rstrip(b"\r\n"))
                if event.get("type") != "event":
                    raise RuntimeClientError(
                        "INVALID_RESPONSE",
                        "Expected an event message",
                    )
                yield event
        finally:
            writer.close()
            await writer.wait_closed()

    async def _connect(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if self.endpoint.kind == "unix":
            assert self.endpoint.path is not None
            return await asyncio.open_unix_connection(str(self.endpoint.path))
        return await asyncio.open_connection(
            host=self.endpoint.host,
            port=self.endpoint.port,
        )
