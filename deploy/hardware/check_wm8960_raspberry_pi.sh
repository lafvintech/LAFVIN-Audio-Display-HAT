#!/usr/bin/env bash
set -Eeuo pipefail

PROFILE_NAME="lafvin-hat-wm8960"
PROFILE_VERSION="2"
PROFILE_LICENSE="GPL-3.0"
PROFILE_ARCHIVE_SHA256="8f2aaea499200843ecc4dc506bec615cab5c1f527d1e72501d2157c28369c80e"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ARCHIVE="${PROJECT_ROOT}/hardware/lafvin_hat/wm8960/v2/lafvin-hat-wm8960-v2.zip"
PROFILE_STATE="/var/lib/lafvin-hat-hardware/lafvin-hat-wm8960-profile.env"
TARGET_ETC_DIR="/etc/wm8960-soundcard"
TARGET_BIN="/usr/bin/wm8960-soundcard"
SERVICE_NAME="wm8960-soundcard.service"
WIREPLUMBER_CONFIG="/etc/wireplumber/wireplumber.conf.d/51-lafvin-hat-wm8960.conf"
BUNDLED_FONT="${PROJECT_ROOT}/assets/font/HarmonyOS Sans/HarmonyOS_Sans_SC.ttf"
BOOT_CONFIG="/boot/firmware/config.txt"
MODULES_FILE="/etc/modules"

failures=0
warnings=0

usage() {
  cat <<'EOF'
Usage: sudo bash install_driver.sh --check

Read-only verification for the LAFVIN HAT WM8960 hardware profile.
EOF
}

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

check_exact_line() {
  local file="$1"
  local line="$2"
  local description="$3"
  if [[ -f "$file" ]] && grep -qxF "$line" "$file"; then
    pass "$description"
  else
    fail "$description is missing: $line"
  fi
}

check_file() {
  local path="$1"
  local description="$2"
  if [[ -e "$path" ]]; then
    pass "$description: $path"
  else
    fail "$description is missing: $path"
  fi
}

check_mixer_value() {
  local card="$1"
  local control="$2"
  local expected="$3"
  local description="$4"
  local output observed
  output="$(amixer -c "$card" cget "name=$control" 2>/dev/null || true)"
  observed="$(sed -n 's/^[[:space:]]*: values=//p' <<<"$output" | head -n 1)"
  if [[ "$observed" == "$expected" ]]; then
    pass "$description"
  else
    fail "$description expected $expected; observed ${observed:-unavailable}"
  fi
}

find_wm8960_card() {
  awk '
    /^[[:space:]]*[0-9]+[[:space:]]+\[/ { card=$1 }
    /wm8960/ && card != "" { print card; exit }
  ' /proc/asound/cards 2>/dev/null
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || {
  echo "Run profile check as root: sudo bash install_driver.sh --check" >&2
  exit 1
}
[[ -r /proc/device-tree/model ]] || {
  echo "Raspberry Pi model information is unavailable." >&2
  exit 1
}
grep -q "Raspberry Pi" /proc/device-tree/model || {
  echo "The WM8960 profile check supports Raspberry Pi only." >&2
  exit 1
}

echo "LAFVIN HAT $PROFILE_NAME profile v$PROFILE_VERSION check"
echo "========================================================"

if [[ -f "$ARCHIVE" ]] && command -v sha256sum >/dev/null 2>&1; then
  archive_sha256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
  if [[ "$archive_sha256" == "$PROFILE_ARCHIVE_SHA256" ]]; then
    pass "Bundled LAFVIN WM8960 archive checksum"
  else
    fail "Bundled archive checksum differs from profile v$PROFILE_VERSION"
  fi
else
  fail "Bundled LAFVIN WM8960 archive or sha256sum is unavailable"
fi

if [[ -f "$PROFILE_STATE" ]]; then
  if [[ "$(stat -c '%U' "$PROFILE_STATE")" == "root" ]]; then
    # shellcheck disable=SC1090
    source "$PROFILE_STATE"
    if [[ "${LAFVIN_WM8960_PROFILE_STATE_VERSION:-}" == "1" \
      && "${LAFVIN_WM8960_PROFILE_NAME:-}" == "$PROFILE_NAME" \
      && "${LAFVIN_WM8960_PROFILE_VERSION:-}" == "$PROFILE_VERSION" \
      && "${LAFVIN_WM8960_PROFILE_LICENSE:-}" == "$PROFILE_LICENSE" \
      && "${LAFVIN_WM8960_RESOURCE_SHA256:-}" == "$PROFILE_ARCHIVE_SHA256" ]]; then
      pass "Recorded LAFVIN WM8960 profile ownership state"
    else
      ownership_error="WM8960 profile ownership state mismatch: expected"
      ownership_error+=" v$PROFILE_VERSION and $PROFILE_ARCHIVE_SHA256;"
      ownership_error+=" recorded version"
      ownership_error+=" ${LAFVIN_WM8960_PROFILE_VERSION:-missing}, resource"
      ownership_error+=" ${LAFVIN_WM8960_RESOURCE_SHA256:-missing}"
      fail "$ownership_error"
    fi
  else
    fail "WM8960 profile state is not root-owned"
  fi
else
  fail "WM8960 profile ownership state is missing; run sudo bash install_driver.sh"
fi

if [[ ! -f "$BOOT_CONFIG" && -f /boot/config.txt ]]; then
  BOOT_CONFIG="/boot/config.txt"
fi
check_exact_line "$BOOT_CONFIG" "dtparam=i2c_arm=on" "I2C profile setting"
check_exact_line "$BOOT_CONFIG" "dtparam=i2s=on" "I2S profile setting"
check_exact_line "$BOOT_CONFIG" "dtoverlay=i2s-mmap" "I2S mmap overlay"
check_exact_line "$BOOT_CONFIG" "dtoverlay=wm8960-soundcard" "WM8960 overlay"
check_exact_line "$MODULES_FILE" "snd-soc-wm8960-soundcard" "WM8960 card module"

check_file "$TARGET_ETC_DIR/asound.conf" "Profile ALSA configuration"
check_file "$TARGET_ETC_DIR/wm8960_asound.state" "Profile mixer state"
check_file "$TARGET_BIN" "Profile helper"
if [[ -f "$WIREPLUMBER_CONFIG" ]] \
  && grep -qxF '# Managed by LAFVIN HAT WM8960 profile.' "$WIREPLUMBER_CONFIG" \
  && grep -qF 'api.alsa.card.id = "wm8960soundcard"' "$WIREPLUMBER_CONFIG" \
  && grep -qF 'api.alsa.soft-mixer = true' "$WIREPLUMBER_CONFIG"; then
  pass "WM8960 WirePlumber soft-mixer configuration"
else
  fail "WM8960 WirePlumber soft-mixer configuration is missing or invalid: $WIREPLUMBER_CONFIG"
fi
if [[ -f "$WIREPLUMBER_CONFIG" \
  && "${LAFVIN_WM8960_WIREPLUMBER_CONFIG:-}" == "$WIREPLUMBER_CONFIG" \
  && -n "${LAFVIN_WM8960_WIREPLUMBER_CONFIG_SHA256:-}" \
  && "$(sha256sum "$WIREPLUMBER_CONFIG" 2>/dev/null | awk '{print $1}')" \
    == "$LAFVIN_WM8960_WIREPLUMBER_CONFIG_SHA256" ]]; then
  pass "Recorded WirePlumber rule ownership"
else
  fail "WirePlumber rule ownership is missing or differs from installed content"
fi
if [[ -L /var/lib/alsa/asound.state \
  && "$(readlink -f /var/lib/alsa/asound.state)" \
    == "$(readlink -f "$TARGET_ETC_DIR/wm8960_asound.state")" ]]; then
  fail "Mutable ALSA state still points to the fixed profile mixer state"
else
  pass "Mutable ALSA state is separate from the fixed profile"
fi
if [[ -e "/lib/systemd/system/$SERVICE_NAME" \
  || -e "/usr/lib/systemd/system/$SERVICE_NAME" ]]; then
  pass "Profile systemd unit: $SERVICE_NAME"
else
  fail "Profile systemd unit is missing: $SERVICE_NAME"
fi

if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
  pass "Profile service is enabled"
else
  fail "Profile service is not enabled"
fi
if [[ -L "/etc/systemd/system/multi-user.target.wants/$SERVICE_NAME" ]]; then
  pass "Profile service uses multi-user boot ordering"
else
  fail "Profile service is not enabled for multi-user.target"
fi
if [[ -L "/etc/systemd/system/sysinit.target.wants/$SERVICE_NAME" ]]; then
  fail "Legacy sysinit.target service link is still present"
else
  pass "Legacy sysinit.target service link is absent"
fi
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
  pass "Profile service is active"
else
  service_state="$(systemctl show "$SERVICE_NAME" -p ActiveState --value 2>/dev/null || true)"
  service_result="$(systemctl show "$SERVICE_NAME" -p Result --value 2>/dev/null || true)"
  service_error="Profile service is not active: state=${service_state:-unknown},"
  service_error+=" result=${service_result:-unknown}; inspect"
  service_error+=" journalctl -u $SERVICE_NAME and"
  service_error+=" /var/log/wm8960-soundcard.log"
  fail "$service_error"
fi

card="$(find_wm8960_card)"
if [[ -n "$card" ]]; then
  pass "WM8960 ALSA card detected: $card"
else
  fail "WM8960 ALSA card is not registered; run sudo bash install_driver.sh and reboot"
fi

if command -v aplay >/dev/null 2>&1 && aplay -l 2>/dev/null | grep -qi wm8960; then
  pass "WM8960 playback device is visible"
else
  fail "WM8960 playback device is not visible"
fi
if command -v arecord >/dev/null 2>&1 && arecord -l 2>/dev/null | grep -qi wm8960; then
  pass "WM8960 capture device is visible"
else
  fail "WM8960 capture device is not visible"
fi
if [[ -n "$card" ]] && command -v amixer >/dev/null 2>&1 \
  && amixer -c "$card" scontrols 2>/dev/null | grep -Fq "Speaker"; then
  pass "Speaker mixer control is visible"
else
  fail "Speaker mixer control is not visible"
fi
if [[ -n "$card" ]] && command -v amixer >/dev/null 2>&1; then
  check_mixer_value "$card" "Capture Volume" "45,45" \
    "Capture Volume calibration"
  check_mixer_value "$card" "Left Input Boost Mixer LINPUT1 Volume" "2" \
    "Left INPUT1 boost calibration"
  check_mixer_value "$card" "Right Input Boost Mixer RINPUT1 Volume" "2" \
    "Right INPUT1 boost calibration"
  check_mixer_value "$card" "ADC PCM Capture Volume" "195,195" \
    "ADC PCM Capture Volume calibration"
else
  fail "WM8960 capture calibration cannot read ALSA controls"
fi

if [[ -f "$BUNDLED_FONT" ]]; then
  pass "Bundled HarmonyOS Sans SC font is available"
else
  fail "Bundled HarmonyOS Sans SC font is missing: $BUNDLED_FONT"
fi

echo
printf 'Result: %d failure(s), %d warning(s)\n' "$failures" "$warnings"
if [[ "$failures" -ne 0 ]]; then
  exit 1
fi
