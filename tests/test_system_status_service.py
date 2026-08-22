import asyncio
from pathlib import Path

from lafvin_hat.runtime.status import SystemStatusService


class AppManagerStub:
    foreground_app_id = None

    def __init__(self, root: Path) -> None:
        self.data_dir = root / "data"
        self.log_dir = root / "logs"

    def list_apps(self) -> list[dict]:
        return [{"id": "dev.lafvin.chatbot"}]

    def running_app_ids(self) -> list[str]:
        return ["dev.lafvin.chatbot"]


class AudioServiceStub:
    def snapshot(self) -> dict:
        return {
            "backend": "fake",
            "card": None,
            "recording_app_id": None,
            "playing_app_id": None,
        }

    async def get_system_volume(self) -> int:
        return 70


class BackendStub:
    name = "simulator"
    display_width = 240
    display_height = 280

    def state_snapshot(self) -> dict:
        return {
            "backend": "simulator",
            "display": {"width": 240, "height": 280},
            "backlight": 100,
            "network": {"online": True},
            "battery": {"level": 42, "charging": True},
        }


def test_system_status_collects_non_secret_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def scenario() -> None:
        monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
        monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "openai-compatible")
        monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fake")
        monkeypatch.setenv("LAFVIN_LLM_API_KEY", "sk-secret")
        monkeypatch.setenv("LAFVIN_LLM_BASE_URL", "https://llm.example/v1")
        monkeypatch.setenv("LAFVIN_LLM_MODEL", "gpt-test")
        monkeypatch.setattr(
            "lafvin_hat.runtime.status.service._primary_ip_address",
            lambda: "192.0.2.10",
        )
        service = SystemStatusService(
            AppManagerStub(tmp_path),
            AudioServiceStub(),
            BackendStub(),
            runtime_version="0.1-test",
            uptime_ms_provider=lambda: 1234,
        )

        result = await service.snapshot()

        assert result["runtime"]["uptime_ms"] == 1234
        assert result["display"] == {
            "width": 240,
            "height": 280,
            "backlight": 100,
        }
        assert result["network"]["ip_address"] == "192.0.2.10"
        assert result["audio"]["volume"] == 70
        assert result["apps"]["installed_count"] == 1
        assert result["apps"]["running_count"] == 1
        assert result["storage"]["data_dir"] == str(tmp_path / "data")
        assert isinstance(result["storage"]["used_bytes"], int)
        assert isinstance(result["storage"]["total_bytes"], int)
        assert result["ai"]["configured"] is True
        assert result["ai"]["provider"] == "mixed"
        assert result["ai"]["base_url_host"] == "llm.example"
        assert result["ai"]["llm_model"] == "gpt-test"
        assert "sk-secret" not in repr(result)

    asyncio.run(scenario())
