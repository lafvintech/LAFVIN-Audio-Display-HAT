"""Device Runtime package."""

from typing import TYPE_CHECKING

from .config import RuntimeEndpoint, default_runtime_endpoint, parse_endpoint

if TYPE_CHECKING:
    from .ipc.server import RuntimeServer

__all__ = [
    "RuntimeEndpoint",
    "RuntimeServer",
    "default_runtime_endpoint",
    "parse_endpoint",
]


def __getattr__(name: str) -> object:
    """Load heavyweight Runtime exports only when callers request them."""

    if name == "RuntimeServer":
        from .ipc.server import RuntimeServer

        return RuntimeServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
