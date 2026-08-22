from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any


logger = logging.getLogger(__name__)


class HTTPClientLifecycleError(RuntimeError):
    pass


class ReusableHTTPClient:
    """Own one lazily created AsyncClient for a single AI capability."""

    def __init__(
        self,
        *,
        capability: str,
        provider_name: str,
        timeout: float,
        httpx_loader: Callable[[], Any],
    ) -> None:
        self.capability = capability.strip().lower()
        self.provider_name = provider_name.strip()
        self.timeout = timeout
        self._httpx_loader = httpx_loader
        self._client: Any | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    async def get(self) -> Any:
        client = self._client
        if client is not None:
            logger.debug(
                "stage=http_client event=reused capability=%s provider=%s",
                self.capability,
                self.provider_name,
            )
            return client
        async with self._lock:
            if self._closed:
                logger.error(
                    "stage=http_client event=use_after_close capability=%s "
                    "provider=%s",
                    self.capability,
                    self.provider_name,
                )
                raise HTTPClientLifecycleError(
                    f"{self.provider_name} {self.capability.upper()} HTTP "
                    "client has already been closed"
                )
            if self._client is None:
                self._client = self._create_client()
                logger.info(
                    "stage=http_client event=created capability=%s provider=%s",
                    self.capability,
                    self.provider_name,
                )
            return self._client

    async def aclose(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            client = self._client
            self._client = None
        if client is None:
            return
        try:
            await client.aclose()
        except Exception as exc:
            logger.exception(
                "stage=http_client event=close_failed capability=%s "
                "provider=%s error_type=%s",
                self.capability,
                self.provider_name,
                type(exc).__name__,
            )
            raise HTTPClientLifecycleError(
                f"Failed to close {self.provider_name} "
                f"{self.capability.upper()} HTTP client: {exc}"
            ) from exc
        logger.info(
            "stage=http_client event=closed capability=%s provider=%s",
            self.capability,
            self.provider_name,
        )

    def _create_client(self) -> Any:
        try:
            httpx = self._httpx_loader()
            limits = httpx.Limits(
                max_connections=2,
                max_keepalive_connections=1,
                keepalive_expiry=60.0,
            )
            return httpx.AsyncClient(
                timeout=self.timeout,
                limits=limits,
            )
        except Exception as exc:
            logger.exception(
                "stage=http_client event=create_failed capability=%s "
                "provider=%s error_type=%s",
                self.capability,
                self.provider_name,
                type(exc).__name__,
            )
            raise HTTPClientLifecycleError(
                f"Failed to create {self.provider_name} "
                f"{self.capability.upper()} HTTP client: {exc}"
            ) from exc
