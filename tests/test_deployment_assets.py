from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _canonical_profile_bytes(path: Path) -> bytes:
    """Compare release-profile text independently of a Windows checkout EOL."""

    return path.read_bytes().replace(b"\r\n", b"\n")


@pytest.mark.parametrize(
    "relative_path",
    [
        "deploy/install_raspberry_pi.sh",
        "deploy/uninstall_raspberry_pi.sh",
        "install_driver.sh",
        "uninstall_driver.sh",
        "deploy/hardware/install_wm8960_raspberry_pi.sh",
        "deploy/hardware/check_wm8960_raspberry_pi.sh",
        "deploy/hardware/uninstall_wm8960_raspberry_pi.sh",
    ],
)
@pytest.mark.skipif(os.name == "nt", reason="Linux bash is required")
def test_deployment_shell_script_syntax(relative_path: str) -> None:
    script = (ROOT / relative_path).read_text(encoding="utf-8")
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable")
    result = subprocess.run(
        [bash, "-n"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr


def test_bundled_wm8960_resources_are_complete() -> None:
    archive = ROOT / "hardware/lafvin_hat/wm8960/v2/lafvin-hat-wm8960-v2.zip"
    profile_source = ROOT / "hardware/lafvin_hat/wm8960/v2/lafvin-hat-wm8960-v2"
    installer = ROOT / "deploy/hardware/install_wm8960_raspberry_pi.sh"
    checker = ROOT / "deploy/hardware/check_wm8960_raspberry_pi.sh"
    profile = ROOT / "hardware/lafvin_hat/wm8960/v2/PROFILE.md"
    license_file = ROOT / "hardware/lafvin_hat/wm8960/v2/COPYING"

    assert archive.is_file()
    assert profile_source.is_dir()
    assert sha256(archive.read_bytes()).hexdigest() == (
        "8f2aaea499200843ecc4dc506bec615cab5c1f527d1e72501d2157c28369c80e"
    )
    with ZipFile(archive) as bundle:
        entries = bundle.infolist()
        names = {entry.filename for entry in entries}
        mixer_state = bundle.read(
            "lafvin-hat-wm8960-v2/wm8960_asound.state"
        ).decode("utf-8")
        wireplumber_rule = bundle.read(
            "lafvin-hat-wm8960-v2/51-lafvin-hat-wm8960.conf"
        ).decode("utf-8")
    assert all("\\" not in entry.orig_filename for entry in entries)
    source_files = sorted(path for path in profile_source.iterdir() if path.is_file())
    assert source_files
    assert {entry.filename for entry in entries if not entry.is_dir()} == {
        f"lafvin-hat-wm8960-v2/{source_file.name}"
        for source_file in source_files
    }
    for source_file in source_files:
        archive_name = f"lafvin-hat-wm8960-v2/{source_file.name}"
        assert archive_name in names
        with ZipFile(archive) as bundle:
            assert bundle.read(archive_name) == _canonical_profile_bytes(
                source_file
            )
    assert "lafvin-hat-wm8960-v2/wm8960-soundcard" in names
    assert "lafvin-hat-wm8960-v2/wm8960-soundcard.service" in names
    assert "lafvin-hat-wm8960-v2/wm8960_asound.state" in names
    assert "lafvin-hat-wm8960-v2/asound.conf" in names
    assert "lafvin-hat-wm8960-v2/51-lafvin-hat-wm8960.conf" in names
    assert "lafvin-hat-wm8960-v2/dkms.conf" not in names
    assert not (profile_source / "dkms.conf").exists()
    assert "value.0 45" in mixer_state
    assert "value.1 45" in mixer_state
    assert mixer_state.count("value 2") >= 2
    assert 'api.alsa.card.id = "wm8960soundcard"' in wireplumber_rule
    assert 'api.alsa.card.name = "wm8960-soundcard"' in wireplumber_rule
    assert 'api.alsa.card.name = "wm8960soundcard"' not in wireplumber_rule
    assert "api.alsa.soft-mixer = true" in wireplumber_rule

    script = installer.read_text(encoding="utf-8")
    assert "hardware/lafvin_hat/wm8960/v2/lafvin-hat-wm8960-v2.zip" in script
    assert 'PROFILE_NAME="lafvin-hat-wm8960"' in script
    assert "PROFILE_ARCHIVE_SHA256" in script
    assert "write_profile_state" in script
    assert "--yes|-y" in script
    assert "patch_wm8960_service_helper" not in script
    assert "continuing anyway" not in script
    assert "systemctl reenable wm8960-soundcard.service" in script
    assert 'WIREPLUMBER_CONFIG_DIR="/etc/wireplumber/wireplumber.conf.d"' in script
    assert "LAFVIN_WM8960_WIREPLUMBER_CONFIG_SHA256" in script
    assert "Refusing to replace unmanaged WirePlumber config" in script
    assert "dkms" not in script.lower()
    assert "python3-pygame" not in script
    assert "python demos" not in script
    helper = (profile_source / "wm8960-soundcard").read_text(encoding="utf-8")
    service = (profile_source / "wm8960-soundcard.service").read_text(
        encoding="utf-8"
    )
    assert 'alsactl -f "$PROFILE_STATE" restore "$CARD"' in helper
    assert "WARNING: alsactl restore returned non-zero" in helper
    assert "apply_calibration" in helper
    assert 'cset "name=$control" "$value"' in helper
    assert 'verify_control "Capture Volume" "$CAPTURE_VOLUME"' in helper
    assert helper.count("verify_calibration") >= 3
    assert 'ln -s "$PROFILE_DIR/asound.conf" /etc/asound.conf' in helper
    assert "ln -s /etc/wm8960-soundcard/wm8960_asound.state" not in helper
    assert "Before=lafvin-hat.service" in service
    assert "WantedBy=multi-user.target" in service
    assert profile.is_file()
    assert "GPL-3.0" in profile.read_text(encoding="utf-8")
    assert "COPYING" in profile.read_text(encoding="utf-8")
    assert license_file.read_text(encoding="utf-8").startswith(
        "                    GNU GENERAL PUBLIC LICENSE\n"
        "                       Version 3, 29 June 2007\n"
    )
    assert "lafvin-hat-wm8960-profile.env" in checker.read_text(
        encoding="utf-8"
    )
    assert "Mutable ALSA state is separate from the fixed profile" in (
        checker.read_text(encoding="utf-8")
    )
    assert "Legacy sysinit.target service link is absent" in checker.read_text(
        encoding="utf-8"
    )
    assert "WM8960 WirePlumber soft-mixer configuration" in checker.read_text(
        encoding="utf-8"
    )
    assert "Recorded WirePlumber rule ownership" in checker.read_text(
        encoding="utf-8"
    )


def test_checkout_installer_and_hardware_entry_points_are_separate() -> None:
    script = (ROOT / "deploy/install_raspberry_pi.sh").read_text(
        encoding="utf-8"
    )
    dispatcher = (ROOT / "install_driver.sh").read_text(encoding="utf-8")
    hardware_installer = (
        ROOT / "deploy/hardware/install_wm8960_raspberry_pi.sh"
    ).read_text(encoding="utf-8")

    assert '"${SOURCE_DIR}/install_driver.sh"' not in script
    assert "SUDO_USER" in script
    assert "--user USER" in script
    assert 'stat -c \'%U\' "$SOURCE_DIR"' in script
    assert 'runuser -u "$TARGET_USER"' in script
    assert '-e "${SOURCE_DIR}[hardware,ai]"' in script
    assert 'DEPLOYMENT_DIR="/etc/lafvin-hat"' in script
    assert 'DEPLOYMENT_METADATA="${DEPLOYMENT_DIR}/deployment.env"' in script
    assert "deploy/render_systemd_service.py" in script
    assert "tar -C" not in script
    assert 'INSTALL_DIR="/opt/lafvin-hat"' not in script
    assert "apt-get install" not in script
    assert "deploy/hardware/install_wm8960_raspberry_pi.sh" in dispatcher
    assert "check_wm8960_raspberry_pi.sh" in dispatcher
    assert "fonts-noto-cjk" not in hardware_installer
    assert "raspi-config nonint do_spi 0" in hardware_installer
    assert "raspi-config nonint do_i2c 0" in hardware_installer
    assert (
        'safe_uncomment_or_append "$BOOT_CONFIG" "dtparam=i2s=on"'
        in hardware_installer
    )
    assert "write_hardware_state" in hardware_installer
    assert "/var/lib/lafvin-hat-hardware" in hardware_installer
    assert 'CLI_LINK="/usr/local/bin/lafvin-hat"' in script
    assert 'LEGACY_CLI_LINK="/usr/local/bin/lafvin"' in script
    assert '"${VENV_DIR}/bin/lafvin-hat"' in script
    assert "LAFVIN_DEPLOYMENT_VERSION=2" in script
    assert "-m lafvin_hat.runtime.apps.provision" not in script
    assert '"${SOURCE_DIR}/apps/chatbot"' not in script
    assert '"${SOURCE_DIR}/apps/one_button_jump"' not in script
    service = (ROOT / "deploy/systemd/lafvin-hat.service").read_text(
        encoding="utf-8"
    )
    assert "After=network-online.target sound.target wm8960-soundcard.service" in service
    assert "Wants=network-online.target wm8960-soundcard.service" in service


def test_runtime_and_driver_uninstallers_preserve_separate_boundaries() -> None:
    runtime = (ROOT / "deploy/uninstall_raspberry_pi.sh").read_text(
        encoding="utf-8"
    )
    dispatcher = (ROOT / "uninstall_driver.sh").read_text(encoding="utf-8")
    driver = (
        ROOT / "deploy/hardware/uninstall_wm8960_raspberry_pi.sh"
    ).read_text(encoding="utf-8")

    assert "--dry-run" in runtime
    assert "--yes" in runtime
    assert "/etc/lafvin-hat/deployment.env" in runtime
    assert "preserve configuration" in runtime
    assert "preserve packages, interfaces, and WM8960 hardware driver" in runtime
    assert "uninstall_driver.sh" not in runtime
    assert "/usr/local/bin/lafvin-hat" in runtime
    assert "LAFVIN_LEGACY_CLI_LINK" in runtime
    assert "remove_managed_cli_link" in runtime
    assert '"${LAFVIN_VENV_DIR}/bin/lafvin-hat"' in runtime
    assert "uninstall_wm8960_raspberry_pi.sh" in dispatcher
    assert "--dry-run" in driver
    assert "lafvin-hat-wm8960-profile.env" in driver
    assert "dtoverlay=wm8960-soundcard" in driver
    assert "snd-soc-wm8960-soundcard" in driver
    assert "preserve apt packages, fonts, and shared SPI setup" in driver
    assert "rm -rf -- \"$TARGET_ETC_DIR\"" in driver
    assert "remove_wireplumber_config" in driver
    assert "Preserved modified WirePlumber rule" in driver
    assert "apt-get remove" not in driver


def test_hardware_acceptance_tools_are_present() -> None:
    check = (ROOT / "tools/hardware_check.sh").read_text(encoding="utf-8")
    interactive = (ROOT / "tools/hardware_test.py").read_text(
        encoding="utf-8"
    )

    assert "/dev/spidev0.0" in check
    assert "wm8960" in check
    assert "HarmonyOS_Sans_SC.ttf" in check
    assert "_test_display" in interactive
    assert "_test_led" in interactive
    assert "_test_button" in interactive
    assert "_test_speaker" in interactive
    assert "_test_microphone" in interactive


def test_systemd_uses_runtime_env_file_parser() -> None:
    service = (ROOT / "deploy/systemd/lafvin-hat.service").read_text(
        encoding="utf-8"
    )
    template = (ROOT / "deploy/runtime.env.example").read_text(
        encoding="utf-8"
    )

    assert "--env-file /etc/lafvin-hat/runtime.env" in service
    assert "--backend lafvin-hat" in service
    assert "User=@@LAFVIN_USER@@" in service
    assert "WorkingDirectory=" not in service
    assert "Environment=@@LAFVIN_PROJECT_ENV@@" in service
    assert "ExecStartPre=" not in service
    assert "@@LAFVIN_APP_CHATBOT@@" not in service
    assert "ExecStart=@@LAFVIN_RUNTIME@@" in service
    assert "EnvironmentFile=" not in service
    assert "LAFVIN_AI_PROVIDER=" not in template
    assert "LAFVIN_ASR_PROVIDER=openai" in template
    assert "LAFVIN_LLM_PROVIDER=openai" in template
    assert "LAFVIN_TTS_PROVIDER=openai" in template
    assert "LAFVIN_ASR_PROVIDER=fake" not in template
    assert "LAFVIN_LLM_PROVIDER=fake" not in template
    assert "LAFVIN_TTS_PROVIDER=fake" not in template
    assert "OPENAI_BASE_URL=" not in template
    assert "LAFVIN_OPENAI_BASE_URL=" not in template
    assert "# LAFVIN_LLM_BASE_URL=" in template
    assert "LAFVIN_ASR_BASE_URL=" not in template
    assert "LAFVIN_TTS_BASE_URL=" not in template
    assert "LAFVIN_ASR_API_KEY=" not in template
    assert "LAFVIN_TTS_API_KEY=" not in template
    assert "# DEEPSEEK_API_KEY=" in template
    assert "# MOONSHOT_API_KEY=" in template
    assert "# ANTHROPIC_API_KEY=" in template
    assert "# MINIMAX_API_KEY=" in template
    assert "# FISH_AUDIO_API_KEY=" in template
    assert "# Fish Audio ASR uses paid API credit" in template
    assert "# LAFVIN_ASR_MODEL=transcribe-1" in template
    assert "# LAFVIN_ASR_LANGUAGE=zh" in template
    assert "KIMI_API_KEY" not in template
    assert "CLAUDE_API_KEY" not in template


def test_development_and_deployment_env_templates_match() -> None:
    development = (ROOT / ".env.example").read_text(encoding="utf-8")
    deployment = (ROOT / "deploy/runtime.env.example").read_text(
        encoding="utf-8"
    )

    assert development == deployment
