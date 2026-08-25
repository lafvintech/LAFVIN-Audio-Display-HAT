#!/usr/bin/env bash
set -u

failures=0
warnings=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

pass() {
  printf '[PASS] %s\n' "$1"
}

fail() {
  printf '[FAIL] %s\n' "$1" >&2
  failures=$((failures + 1))
}

warn() {
  printf '[WARN] %s\n' "$1" >&2
  warnings=$((warnings + 1))
}

check_command() {
  if command -v "$1" >/dev/null 2>&1; then
    pass "Command available: $1"
  else
    fail "Required command is missing: $1"
  fi
}

check_config() {
  local pattern="$1"
  local description="$2"
  if grep -Eq "^[[:space:]]*${pattern}[[:space:]]*$" \
    "${boot_config}" 2>/dev/null; then
    pass "${description}"
  else
    fail "${description} is not configured in ${boot_config}"
  fi
}

echo "LAFVIN HAT hardware check"
echo "========================="

model=""
if [[ -r /proc/device-tree/model ]]; then
  model="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || true)"
fi
if [[ "${model}" == *"Raspberry Pi Zero 2 W"* \
  || "${model}" == *"Raspberry Pi 3 Model B Plus"* \
  || "${model}" == *"Raspberry Pi 4 Model B"* \
  || "${model}" == *"Raspberry Pi 5"* ]]; then
  pass "Supported board: ${model}"
else
  fail "Supported boards are Raspberry Pi Zero 2 W, Pi 3 Model B+, Pi 4 Model B, and Pi 5"
fi

boot_config="/boot/firmware/config.txt"
if [[ ! -f "${boot_config}" && -f /boot/config.txt ]]; then
  boot_config="/boot/config.txt"
fi
if [[ -f "${boot_config}" ]]; then
  pass "Boot configuration found: ${boot_config}"
  check_config "dtparam=spi=on" "SPI boot configuration"
  check_config "dtparam=i2c_arm=on" "I2C boot configuration"
  check_config "dtparam=i2s=on" "I2S boot configuration"
  check_config "dtoverlay=wm8960-soundcard" "WM8960 overlay"
  if grep -qxF "dtoverlay=i2s-mmap" "${boot_config}" 2>/dev/null; then
    warn "Obsolete unowned i2s-mmap entry remains in ${boot_config}"
  else
    pass "Obsolete i2s-mmap overlay is absent"
  fi
else
  fail "Raspberry Pi boot configuration was not found"
fi

if [[ -e /dev/spidev0.0 ]]; then
  pass "SPI device is available: /dev/spidev0.0"
else
  fail "SPI device is unavailable; install the driver and reboot"
fi

if compgen -G "/dev/i2c-*" >/dev/null; then
  pass "I2C device is available"
else
  fail "I2C device is unavailable; install the driver and reboot"
fi

for command in aplay arecord amixer; do
  check_command "${command}"
done

if grep -qi "wm8960" /proc/asound/cards 2>/dev/null; then
  card_line="$(
    grep -i "wm8960" /proc/asound/cards 2>/dev/null \
      | head -n 1 \
      | sed 's/^[[:space:]]*//'
  )"
  pass "WM8960 ALSA card detected: ${card_line}"
else
  fail "WM8960 ALSA card is not registered; a reboot may be pending"
fi

font="${PROJECT_ROOT}/assets/font/HarmonyOS Sans/HarmonyOS_Sans_SC.ttf"
if [[ -f "${font}" ]]; then
  pass "Bundled HarmonyOS Sans SC font is available: ${font}"
else
  fail "Bundled HarmonyOS Sans SC font is missing: ${font}"
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl is-enabled --quiet wm8960-soundcard.service 2>/dev/null; then
    pass "wm8960-soundcard.service is enabled"
  else
    fail "wm8960-soundcard.service is not enabled"
  fi
  if systemctl is-active --quiet wm8960-soundcard.service 2>/dev/null; then
    pass "wm8960-soundcard.service is active"
  else
    warn "wm8960-soundcard.service is not active"
  fi
fi

if command -v vcgencmd >/dev/null 2>&1; then
  throttle="$(vcgencmd get_throttled 2>/dev/null || true)"
  if [[ "${throttle}" == "throttled=0x0" ]]; then
    pass "No Raspberry Pi power or thermal flags are set"
  elif [[ -n "${throttle}" ]]; then
    warn "Raspberry Pi reports power or thermal flags: ${throttle}"
  fi
fi

echo
printf 'Result: %d failure(s), %d warning(s)\n' \
  "${failures}" "${warnings}"
if [[ "${failures}" -ne 0 ]]; then
  exit 1
fi
