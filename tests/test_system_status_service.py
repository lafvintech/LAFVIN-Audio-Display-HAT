import asyncio
from pathlib import Path

from lafvin_hat.runtime.status import SystemStatusService
from lafvin_hat.runtime.status import service as status_service


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
        monkeypatch.setenv(
            "LAFVIN_OPENAI_COMPATIBLE_LLM_API_KEY",
            "sk-secret",
        )
        monkeypatch.setenv(
            "LAFVIN_OPENAI_COMPATIBLE_LLM_BASE_URL",
            "https://llm.example/v1",
        )
        monkeypatch.setenv(
            "LAFVIN_OPENAI_COMPATIBLE_LLM_MODEL",
            "gpt-test",
        )
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
        assert set(result["resources"]) == {"cpu", "memory"}
        assert result["storage"]["data_dir"] == str(tmp_path / "data")
        assert isinstance(result["storage"]["used_bytes"], int)
        assert isinstance(result["storage"]["total_bytes"], int)
        assert isinstance(result["storage"]["usage_percent"], float)
        assert result["ai"]["configured"] is True
        assert result["ai"]["provider"] == "mixed"
        assert result["ai"]["base_url_host"] == "llm.example"
        assert result["ai"]["llm_model"] == "gpt-test"
        assert "sk-secret" not in repr(result)

    asyncio.run(scenario())


def test_system_status_reports_only_selected_provider_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def scenario() -> None:
        monkeypatch.setenv("LAFVIN_ASR_PROVIDER", "fake")
        monkeypatch.setenv("LAFVIN_LLM_PROVIDER", "fake")
        monkeypatch.setenv("LAFVIN_TTS_PROVIDER", "fish")
        monkeypatch.setenv("FISH_AUDIO_API_KEY", "fish-secret")
        monkeypatch.setenv("FISH_AUDIO_TTS_MODEL", "fish-model")
        monkeypatch.setenv("FISH_AUDIO_TTS_VOICE", "fish-voice")
        monkeypatch.setenv("MINIMAX_TTS_MODEL", "minimax-model")
        monkeypatch.setenv("MINIMAX_TTS_VOICE", "minimax-voice")
        service = SystemStatusService(
            AppManagerStub(tmp_path),
            AudioServiceStub(),
            BackendStub(),
            runtime_version="0.1-test",
        )

        result = await service.snapshot()

        assert result["ai"]["configured"] is True
        assert result["ai"]["tts_provider"] == "fish"
        assert result["ai"]["tts_model"] == "fish-model"
        assert result["ai"]["tts_voice"] == "fish-voice"
        assert "minimax-model" not in repr(result["ai"])
        assert "fish-secret" not in repr(result)

    asyncio.run(scenario())


def test_cpu_usage_uses_counter_deltas() -> None:
    assert status_service._cpu_usage_percent((100, 200), (130, 300)) == 70.0
    assert status_service._cpu_usage_percent(None, (130, 300)) is None
    assert status_service._cpu_usage_percent((130, 300), (100, 200)) is None


def test_cpu_times_parse_linux_proc_stat(tmp_path: Path) -> None:
    stat = tmp_path / "stat"
    stat.write_text(
        "cpu  10 2 8 70 5 1 3 1 0 0\ncpu0 1 1 1 1\n",
        encoding="utf-8",
    )

    assert status_service._read_cpu_times(stat) == (75, 100)


def test_memory_usage_uses_mem_available(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:       1000 kB\n"
        "MemFree:         100 kB\n"
        "MemAvailable:    400 kB\n"
        "Buffers:          50 kB\n"
        "Cached:          200 kB\n",
        encoding="utf-8",
    )

    assert status_service._memory_state(meminfo) == {
        "used_bytes": 600 * 1024,
        "total_bytes": 1000 * 1024,
        "usage_percent": 60.0,
    }


def test_resource_readers_handle_missing_proc_files(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    assert status_service._read_cpu_times(missing) is None
    assert status_service._memory_state(missing) == {
        "used_bytes": None,
        "total_bytes": None,
        "usage_percent": None,
    }
