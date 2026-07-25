import asyncio
from pathlib import Path

from lafvin_hat.sdk.frames import RawFrameSession


class FakeClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict]] = []

    async def request(self, method: str, params: dict) -> dict:
        self.requests.append((method, params))
        if method == "frame.commit":
            return {"next_sequence": params["sequence"] + 1}
        return {"active": False}


def test_raw_frame_session_writes_commits_and_closes(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        path = tmp_path / "frame.rgb565"
        path.write_bytes(bytes(8))
        client = FakeClient()
        frame = RawFrameSession(
            client,  # type: ignore[arg-type]
            "dev.lafvin.game",
            "session",
            {
                "width": 2,
                "height": 2,
                "stride": 4,
                "pixel_format": "RGB565_BE",
                "frame_session": "frame-session",
                "next_sequence": 1,
                "buffer_path": str(path),
            },
        )

        frame.write(bytes([0xF8, 0x00]) * 4)
        result = await frame.commit()
        assert result["next_sequence"] == 2
        assert frame.next_sequence == 2
        assert path.read_bytes() == bytes([0xF8, 0x00]) * 4

        await frame.close()
        assert frame.closed is True
        assert [method for method, _ in client.requests] == [
            "frame.commit",
            "frame.release",
        ]

    asyncio.run(scenario())
