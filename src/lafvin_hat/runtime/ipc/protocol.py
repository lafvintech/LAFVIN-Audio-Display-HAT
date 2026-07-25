from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class Request:
    request_id: str
    method: str
    params: dict[str, Any]


class ProtocolError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id


def decode_message(line: bytes) -> dict[str, Any]:
    if len(line) > MAX_MESSAGE_BYTES:
        raise ProtocolError("INVALID_REQUEST", "Message exceeds the size limit")
    try:
        value = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("INVALID_REQUEST", "Message is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ProtocolError("INVALID_REQUEST", "Message must be a JSON object")
    return value


def parse_request(message: dict[str, Any]) -> Request:
    request_id = message.get("id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ProtocolError("INVALID_REQUEST", "Request id must be a non-empty string")

    version = message.get("version")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(
            "UNSUPPORTED_VERSION",
            f"Protocol version {version!r} is not supported",
            request_id=request_id,
        )

    if message.get("type") != "request":
        raise ProtocolError(
            "INVALID_REQUEST",
            "Message type must be 'request'",
            request_id=request_id,
        )

    method = message.get("method")
    if not isinstance(method, str) or not method.strip():
        raise ProtocolError(
            "INVALID_REQUEST",
            "Method must be a non-empty string",
            request_id=request_id,
        )

    params = message.get("params", {})
    if not isinstance(params, dict):
        raise ProtocolError(
            "INVALID_REQUEST",
            "Request params must be an object",
            request_id=request_id,
        )

    return Request(
        request_id=request_id,
        method=method.strip(),
        params=params,
    )


def success_response(request_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "id": request_id,
        "type": "response",
        "ok": True,
        "result": result,
    }


def error_response(
    request_id: str | None,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "id": request_id,
        "type": "response",
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }


def encode_message(message: dict[str, Any]) -> bytes:
    return (
        json.dumps(message, ensure_ascii=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")

