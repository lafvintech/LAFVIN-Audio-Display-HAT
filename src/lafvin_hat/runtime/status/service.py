from __future__ import annotations

import os
import platform
import shutil
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


_PROVIDER_API_KEYS = {
    "claude": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "fish": "FISH_AUDIO_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai-compatible": "LAFVIN_OPENAI_COMPATIBLE_LLM_API_KEY",
}

_LLM_ENDPOINTS = {
    "claude": ("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
    "deepseek": ("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    "kimi": ("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
    "openai": ("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "openai-compatible": (
        "LAFVIN_OPENAI_COMPATIBLE_LLM_BASE_URL",
        "",
    ),
}

_PROVIDER_MODELS = {
    ("ASR", "fish"): ("FISH_AUDIO_ASR_MODEL", "transcribe-1"),
    ("ASR", "openai"): ("OPENAI_ASR_MODEL", "whisper-1"),
    ("LLM", "claude"): ("ANTHROPIC_LLM_MODEL", None),
    ("LLM", "deepseek"): ("DEEPSEEK_LLM_MODEL", None),
    ("LLM", "kimi"): ("MOONSHOT_LLM_MODEL", None),
    ("LLM", "openai"): ("OPENAI_LLM_MODEL", "gpt-4o-mini"),
    ("LLM", "openai-compatible"): (
        "LAFVIN_OPENAI_COMPATIBLE_LLM_MODEL",
        None,
    ),
    ("TTS", "fish"): ("FISH_AUDIO_TTS_MODEL", "s2.1-pro"),
    ("TTS", "minimax"): ("MINIMAX_TTS_MODEL", "speech-2.8-turbo"),
    ("TTS", "openai"): ("OPENAI_TTS_MODEL", "tts-1"),
}

_TTS_VOICES = {
    "fish": ("FISH_AUDIO_TTS_VOICE", None),
    "minimax": ("MINIMAX_TTS_VOICE", "male-qn-qingse"),
    "openai": ("OPENAI_TTS_VOICE", "alloy"),
}


class SystemStatusService:
    def __init__(
        self,
        app_manager: Any,
        audio_service: Any,
        backend: Any,
        *,
        runtime_version: str,
        uptime_ms_provider: Callable[[], int] | None = None,
    ) -> None:
        self._app_manager = app_manager
        self._audio_service = audio_service
        self._backend = backend
        self._runtime_version = runtime_version
        self._uptime_ms_provider = uptime_ms_provider or (lambda: 0)

    async def snapshot(self, *, uptime_ms: int | None = None) -> dict[str, Any]:
        if uptime_ms is None:
            uptime_ms = self._uptime_ms_provider()
        backend = self._backend.state_snapshot()
        audio = self._audio_service.snapshot()
        apps = self._app_manager.list_apps()
        running = self._app_manager.running_app_ids()
        volume = await self._audio_service.get_system_volume()
        return {
            "runtime": {
                "version": self._runtime_version,
                "uptime_ms": uptime_ms,
                "python": platform.python_version(),
            },
            "device": {
                "model": _device_model(),
                "backend": backend.get("backend", self._backend.name),
                "hardware_profile": backend.get("hardware_profile"),
                "hostname": socket.gethostname(),
                "temperature_c": _temperature_c(),
            },
            "display": {
                "width": backend.get("display", {}).get(
                    "width",
                    getattr(self._backend, "display_width", None),
                ),
                "height": backend.get("display", {}).get(
                    "height",
                    getattr(self._backend, "display_height", None),
                ),
                "backlight": backend.get("backlight"),
            },
            "network": _network_state(backend),
            "battery": backend.get("battery"),
            "audio": {
                **audio,
                "volume": volume,
            },
            "ai": _ai_state(),
            "apps": {
                "installed_count": len(apps),
                "running_count": len(running),
                "foreground_app_id": self._app_manager.foreground_app_id,
            },
            "storage": _storage_state(self._app_manager.data_dir),
        }


def _device_model() -> str:
    model_path = Path("/proc/device-tree/model")
    try:
        value = model_path.read_text(encoding="utf-8").strip("\x00\n ")
    except OSError:
        value = ""
    return value or platform.machine() or "unknown"


def _temperature_c() -> float | None:
    temperature_path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        raw = temperature_path.read_text(encoding="utf-8").strip()
        return round(int(raw) / 1000, 1)
    except (OSError, ValueError):
        return None


def _network_state(backend: dict[str, Any]) -> dict[str, Any]:
    state = backend.get("network")
    if isinstance(state, dict):
        online = state.get("online")
    else:
        online = None
    return {
        "online": online,
        "ip_address": _primary_ip_address(),
    }


def _primary_ip_address() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return None
    finally:
        sock.close()


def _ai_state() -> dict[str, Any]:
    asr_provider = os.getenv("LAFVIN_ASR_PROVIDER") or "fake"
    llm_provider = os.getenv("LAFVIN_LLM_PROVIDER") or "fake"
    tts_provider = os.getenv("LAFVIN_TTS_PROVIDER") or "fake"
    providers = (asr_provider, llm_provider, tts_provider)
    selection = providers[0] if len(set(providers)) == 1 else "mixed"
    base_url = _llm_base_url(llm_provider)
    base_url_host = (urlsplit(base_url).netloc or None) if base_url else None
    return {
        "configured": all(
            _provider_is_configured(capability, provider)
            for capability, provider in zip(
                ("ASR", "LLM", "TTS"),
                providers,
                strict=True,
            )
        ),
        "provider": selection,
        "asr_provider": asr_provider,
        "llm_provider": llm_provider,
        "tts_provider": tts_provider,
        "base_url_host": base_url_host,
        "asr_model": _provider_model("ASR", asr_provider),
        "llm_model": _provider_model("LLM", llm_provider),
        "tts_model": _provider_model("TTS", tts_provider),
        "tts_voice": _tts_voice(tts_provider),
    }


def _provider_is_configured(capability: str, provider: str) -> bool:
    normalized = provider.strip().lower()
    if normalized == "fake":
        return True
    if normalized == "openai-compatible" and capability != "LLM":
        return False
    key_name = _PROVIDER_API_KEYS.get(normalized)
    if key_name is None or not os.getenv(key_name):
        return False
    if normalized == "openai-compatible":
        if not os.getenv("LAFVIN_OPENAI_COMPATIBLE_LLM_BASE_URL"):
            return False
    model_setting = _PROVIDER_MODELS.get((capability, normalized))
    if model_setting is not None:
        variable, default = model_setting
        if not (os.getenv(variable) or default):
            return False
    return True


def _llm_base_url(provider: str) -> str:
    variable_and_default = _LLM_ENDPOINTS.get(provider.strip().lower())
    if variable_and_default is None:
        return ""
    variable, default = variable_and_default
    return os.getenv(variable) or default


def _provider_model(capability: str, provider: str) -> str | None:
    setting = _PROVIDER_MODELS.get((capability, provider.strip().lower()))
    if setting is None:
        return None
    variable, default = setting
    return os.getenv(variable) or default


def _tts_voice(provider: str) -> str | None:
    setting = _TTS_VOICES.get(provider.strip().lower())
    if setting is None:
        return None
    variable, default = setting
    return os.getenv(variable) or default


def _storage_state(data_dir: Path) -> dict[str, Any]:
    path = data_dir
    while not path.exists() and path.parent != path:
        path = path.parent
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return {
            "data_dir": str(data_dir),
            "used_bytes": None,
            "total_bytes": None,
        }
    return {
        "data_dir": str(data_dir),
        "used_bytes": usage.used,
        "total_bytes": usage.total,
    }
