from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from lafvin_hat.sdk.client import RuntimeClientError


def run_async_command(
    parser: argparse.ArgumentParser,
    command: Callable[[], Awaitable[Any]],
) -> Any:
    try:
        return asyncio.run(command())
    except RuntimeClientError as exc:
        parser.exit(1, f"error: {exc.code}: {exc.message}\n")
    except asyncio.TimeoutError:
        parser.exit(
            1,
            "error: RUNTIME_UNAVAILABLE: Runtime connection timed out\n",
        )
    except OSError as exc:
        detail = str(exc) or type(exc).__name__
        parser.exit(
            1,
            f"error: RUNTIME_UNAVAILABLE: Cannot connect to Runtime: "
            f"{detail}\n",
        )
    except ValueError as exc:
        parser.exit(2, f"error: INVALID_ARGUMENT: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "error: INTERRUPTED: Command interrupted\n")
