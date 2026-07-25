"""Runtime IPC implementation."""

from typing import TYPE_CHECKING

from .protocol import PROTOCOL_VERSION, ProtocolError, Request

if TYPE_CHECKING:
    from .server import RuntimeServer

__all__ = ["PROTOCOL_VERSION", "ProtocolError", "Request", "RuntimeServer"]


def __getattr__(name: str) -> object:
    """Avoid importing the Runtime Server for protocol-only consumers."""

    if name == "RuntimeServer":
        from .server import RuntimeServer

        return RuntimeServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
