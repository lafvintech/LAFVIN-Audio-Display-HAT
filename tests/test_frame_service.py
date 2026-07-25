import asyncio
import time
from pathlib import Path

import pytest

from lafvin_hat.runtime.backends import SimulatorBackend
from lafvin_hat.runtime.events import EventBus
from lafvin_hat.runtime.frames import FrameService
from lafvin_hat.runtime.ipc.protocol import ProtocolError


class AuthorizedApp:
    async def authorize(
        self,
        app_id: str,
        session_token: str,
        *,
        permission: str,
        require_foreground: bool = False,
        ui_mode: str | None = None,
    ) -> Path:
        assert app_id == "dev.lafvin.game"
        assert session_token == "session"
        assert permission == "display.raw_frame"
        assert ui_mode == "raw_frame"
        return Path(".")


def test_frame_acquire_commit_sequence_and_invalidation(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        backend = SimulatorBackend(web_enabled=False)
        events = EventBus()
        service = FrameService(
            AuthorizedApp(),  # type: ignore[arg-type]
            backend,
            events,
            buffer_root=tmp_path,
        )
        await backend.start()
        await service.start()
        try:
            acquired = await service.acquire(
                "dev.lafvin.game",
                "session",
            )
            buffer_path = Path(acquired["buffer_path"])
            assert buffer_path.stat().st_size == 240 * 280 * 2
            assert acquired["next_sequence"] == 1
            assert acquired["pixel_format"] == "RGB565_BE"

            buffer_path.write_bytes(bytes([0x12, 0x34]) * (240 * 280))
            committed = await service.commit(
                "dev.lafvin.game",
                "session",
                acquired["frame_session"],
                1,
                [{"x": 10, "y": 10, "width": 20, "height": 20}],
                int(time.time() * 1000),
            )
            assert committed["next_sequence"] == 2
            assert committed["metrics"]["commit_count"] == 1
            assert committed["metrics"]["last_input_latency_ms"] >= 0
            assert backend.state_snapshot()["ui"]["mode"] == "raw_frame"
            assert backend.state_snapshot()["ui"]["frame_sequence"] == 1

            with pytest.raises(ProtocolError) as sequence_error:
                await service.commit(
                    "dev.lafvin.game",
                    "session",
                    acquired["frame_session"],
                    1,
                    None,
                    None,
                )
            assert sequence_error.value.code == "INVALID_FRAME_SEQUENCE"

            await service.release(
                "dev.lafvin.game",
                "session",
                acquired["frame_session"],
            )
            assert service.snapshot()["active"] is False
            assert backend.state_snapshot()["ui"]["mode"] == "raw_frame"
            assert backend.state_snapshot()["ui"]["frame_sequence"] == 1
            with pytest.raises(ProtocolError) as session_error:
                await service.commit(
                    "dev.lafvin.game",
                    "session",
                    acquired["frame_session"],
                    2,
                    None,
                    None,
                )
            assert session_error.value.code == "INVALID_FRAME_SESSION"
        finally:
            await service.stop()
            await backend.stop()

    asyncio.run(scenario())


def test_frame_rejects_dirty_rect_outside_display(tmp_path: Path) -> None:
    async def scenario() -> None:
        backend = SimulatorBackend(web_enabled=False)
        service = FrameService(
            AuthorizedApp(),  # type: ignore[arg-type]
            backend,
            EventBus(),
            buffer_root=tmp_path,
        )
        await service.start()
        try:
            acquired = await service.acquire("dev.lafvin.game", "session")
            with pytest.raises(ProtocolError) as exc_info:
                await service.commit(
                    "dev.lafvin.game",
                    "session",
                    acquired["frame_session"],
                    1,
                    [{"x": 230, "y": 0, "width": 20, "height": 10}],
                    None,
                )
            assert exc_info.value.code == "INVALID_REQUEST"
        finally:
            await service.stop()

    asyncio.run(scenario())
