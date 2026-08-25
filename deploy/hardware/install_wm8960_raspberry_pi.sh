#!/usr/bin/env bash
#
# LAFVIN HAT WM8960 profile installer.
# See hardware/lafvin_hat/wm8960/v4/PROFILE.md for profile maintenance.
# Local changes: resource pinning, profile ownership state, --yes mode,
# temporary extraction, and reboot-aware first-install verification.
# - Preflight checks BEFORE any changes
# - Explicit user confirmation
# - Timestamped backups of touched files
# - Every operation fails fast with a clear summary
# - Applies and verifies the bundled mixer calibration when the card is available
# - Optional: post-run power/brownout warning (non-fatal)
#
# Run directly:
#   sudo bash install_driver.sh
#

set -Eeuo pipefail

# ----------------------------
# Config
# ----------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROFILE_NAME="lafvin-hat-wm8960"
PROFILE_VERSION="4"
PROFILE_LICENSE="GPL-3.0"
PROFILE_ARCHIVE_SHA256="107aa596234ede0b2fb077657bced2043b083051b841093d9b86a469ef771d40"
ZIP_NAME="${PROJECT_ROOT}/hardware/lafvin_hat/wm8960/v4/lafvin-hat-wm8960-v4.zip"
ASSUME_YES=false

for arg in "$@"; do
  case "$arg" in
    --yes|-y)
      ASSUME_YES=true
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

BOOT_CONFIG="/boot/firmware/config.txt"
MODULES_FILE="/etc/modules"

TARGET_ETC_DIR="/etc/wm8960-soundcard"
TARGET_BIN="/usr/bin/wm8960-soundcard"
TARGET_SERVICE="/lib/systemd/system/wm8960-soundcard.service"
ALT_SERVICE="/usr/lib/systemd/system/wm8960-soundcard.service"
WIREPLUMBER_CONFIG_DIR="/etc/wireplumber/wireplumber.conf.d"
WIREPLUMBER_CONFIG_PATH="${WIREPLUMBER_CONFIG_DIR}/51-lafvin-hat-wm8960.conf"
WIREPLUMBER_CONFIG_MARKER="# Managed by LAFVIN HAT WM8960 profile."
HARDWARE_STATE_DIR="/var/lib/lafvin-hat-hardware"
HARDWARE_STATE="${HARDWARE_STATE_DIR}/wm8960-install.env"
PROFILE_STATE="${HARDWARE_STATE_DIR}/lafvin-hat-wm8960-profile.env"
SERVICE_INSTALL_PATH="${TARGET_SERVICE}"
WIREPLUMBER_CONFIG_SHA256=""

ACTION_MODULE_I2C_DEV="unknown"
ACTION_MODULE_CODEC="unknown"
ACTION_MODULE_CARD="unknown"
ACTION_I2C_PARAM="unknown"
ACTION_I2S_PARAM="unknown"
ACTION_I2S_OVERLAY="not_required"
ACTION_WM8960_OVERLAY="unknown"
I2S_MMAP_MIGRATION="not_checked"
RPI_MODEL=""

PREVIOUS_PROFILE_VERSION=""
PREVIOUS_BACKUP_DIR=""
PREVIOUS_ACTION_MODULE_I2C_DEV="unknown"
PREVIOUS_ACTION_MODULE_CODEC="unknown"
PREVIOUS_ACTION_MODULE_CARD="unknown"
PREVIOUS_ACTION_I2C_PARAM="unknown"
PREVIOUS_ACTION_I2S_PARAM="unknown"
PREVIOUS_ACTION_I2S_OVERLAY="unknown"
PREVIOUS_ACTION_WM8960_OVERLAY="unknown"
OWNERSHIP_BACKUP_DIR=""

REQUIRED_PKGS=(
  python3
  python3-venv
  python3-dev
  alsa-utils
  i2c-tools
  libgpiod-dev
  libasound2-plugins
  ffmpeg
  unzip
  raspi-config
  python3-libgpiod
  python3-spidev
)

# ----------------------------
# State tracking for summary
# ----------------------------
declare -A STEP
STEP[preflight]="not started"
STEP[apt_update]="not started"
STEP[pkgs_install]="not started"
STEP[enable_interfaces]="not started"
STEP[unzip]="not started"
STEP[modules]="not started"
STEP[boot_config]="not started"
STEP[install_files]="not started"
STEP[service]="not started"
STEP[profile_state]="not started"
STEP[done]="not started"

BACKUP_DIR=""
EXTRACT_DIR=""

# ----------------------------
# Helpers
# ----------------------------
log()  { echo "[*] $*"; }
ok()   { echo "[+] $*"; }
warn() { echo "[!] $*" >&2; }
die()  { echo "[X] $*" >&2; exit 1; }

read_rpi_model() {
  [[ -r /proc/device-tree/model ]] || return 1
  tr -d '\0' </proc/device-tree/model
}

is_supported_pi() {
  local model="$1"
  [[ "$model" == *"Raspberry Pi Zero 2 W"* \
    || "$model" == *"Raspberry Pi 3 Model B Plus"* \
    || "$model" == *"Raspberry Pi 4 Model B"* \
    || "$model" == *"Raspberry Pi 5"* ]]
}

need_root() {
  [[ "${EUID:-$(id -u)}" -eq 0 ]] || die "This script must be run as root (use sudo)."
}

have_cmd() { command -v "$1" >/dev/null 2>&1; }
pkg_missing() { ! dpkg -s "$1" >/dev/null 2>&1; }

backup_file() {
  local f="$1"
  [[ -e "$f" ]] || return 0
  cp -a "$f" "$BACKUP_DIR/" || die "Failed to backup: $f"
}

ensure_line_in_file() {
  local file="$1"
  local line="$2"
  local result_var="${3:-}"
  local action="existing"
  if ! grep -qxF "$line" "$file"; then
    echo "$line" >> "$file"
    action="added"
  fi
  [[ -n "$result_var" ]] && printf -v "$result_var" '%s' "$action"
}

safe_uncomment_or_append() {
  local file="$1"
  local line="$2"
  local result_var="${3:-}"
  local commented="#$line"
  local action="existing"

  if grep -qxF "$line" "$file"; then
    action="existing"
  elif grep -qxF "$commented" "$file"; then
    # replace exact commented line with the line
    sed -i "s|^$(printf '%s' "$commented" | sed 's/[^^]/[&]/g; s/\^/\\^/g')$|$line|" "$file"
    action="uncommented"
  else
    echo "$line" >> "$file"
    action="added"
  fi
  [[ -n "$result_var" ]] && printf -v "$result_var" '%s' "$action"
}

load_previous_profile_state() {
  [[ -f "$PROFILE_STATE" ]] || return 0
  [[ "$(stat -c '%U' "$PROFILE_STATE")" == root ]] || \
    die "Refusing profile state not owned by root: $PROFILE_STATE"
  # The state is generated by this installer. Only root-owned state is sourced;
  # its identity fields are validated immediately afterward.
  # shellcheck disable=SC1090
  source "$PROFILE_STATE"
  [[ "${LAFVIN_WM8960_PROFILE_STATE_VERSION:-}" == 1 ]] || \
    die "Unsupported existing WM8960 profile-state version."
  [[ "${LAFVIN_WM8960_PROFILE_NAME:-}" == "$PROFILE_NAME" ]] || \
    die "Existing profile state does not describe $PROFILE_NAME."

  PREVIOUS_PROFILE_VERSION="${LAFVIN_WM8960_PROFILE_VERSION:-unknown}"
  PREVIOUS_BACKUP_DIR="${LAFVIN_WM8960_BACKUP_DIR:-}"
  PREVIOUS_ACTION_MODULE_I2C_DEV="${LAFVIN_ACTION_MODULE_I2C_DEV:-unknown}"
  PREVIOUS_ACTION_MODULE_CODEC="${LAFVIN_ACTION_MODULE_CODEC:-unknown}"
  PREVIOUS_ACTION_MODULE_CARD="${LAFVIN_ACTION_MODULE_CARD:-unknown}"
  PREVIOUS_ACTION_I2C_PARAM="${LAFVIN_ACTION_I2C_PARAM:-unknown}"
  PREVIOUS_ACTION_I2S_PARAM="${LAFVIN_ACTION_I2S_PARAM:-unknown}"
  PREVIOUS_ACTION_I2S_OVERLAY="${LAFVIN_ACTION_I2S_OVERLAY:-unknown}"
  PREVIOUS_ACTION_WM8960_OVERLAY="${LAFVIN_ACTION_WM8960_OVERLAY:-unknown}"
  log "Detected existing $PROFILE_NAME profile v$PREVIOUS_PROFILE_VERSION."
}

load_previous_ownership_state() {
  [[ -f "$HARDWARE_STATE" ]] || return 0
  [[ "$(stat -c '%U' "$HARDWARE_STATE")" == root ]] || \
    die "Refusing hardware ownership state not owned by root: $HARDWARE_STATE"
  # This first-install record is not overwritten by profile upgrades, so it is
  # the authoritative source for uninstall ownership and the original backup.
  # shellcheck disable=SC1090
  source "$HARDWARE_STATE"
  [[ "${LAFVIN_WM8960_STATE_VERSION:-}" == 1 ]] || \
    die "Unsupported existing WM8960 hardware-state version."

  PREVIOUS_BACKUP_DIR="${LAFVIN_WM8960_BACKUP_DIR:-$PREVIOUS_BACKUP_DIR}"
  PREVIOUS_ACTION_MODULE_I2C_DEV="${LAFVIN_ACTION_MODULE_I2C_DEV:-unknown}"
  PREVIOUS_ACTION_MODULE_CODEC="${LAFVIN_ACTION_MODULE_CODEC:-unknown}"
  PREVIOUS_ACTION_MODULE_CARD="${LAFVIN_ACTION_MODULE_CARD:-unknown}"
  PREVIOUS_ACTION_I2C_PARAM="${LAFVIN_ACTION_I2C_PARAM:-unknown}"
  PREVIOUS_ACTION_I2S_PARAM="${LAFVIN_ACTION_I2S_PARAM:-unknown}"
  PREVIOUS_ACTION_I2S_OVERLAY="${LAFVIN_ACTION_I2S_OVERLAY:-unknown}"
  PREVIOUS_ACTION_WM8960_OVERLAY="${LAFVIN_ACTION_WM8960_OVERLAY:-unknown}"
  log "Loaded first-install WM8960 ownership state."
}

carry_forward_action() {
  local result_var="$1"
  local previous_action="$2"
  local current_action="${!result_var}"
  if [[ "$current_action" == existing \
    && ("$previous_action" == added || "$previous_action" == uncommented) ]]; then
    printf -v "$result_var" '%s' "$previous_action"
  fi
}

migrate_obsolete_i2s_mmap() {
  local line="dtoverlay=i2s-mmap"
  ACTION_I2S_OVERLAY="not_required"
  if ! grep -qxF "$line" "$BOOT_CONFIG"; then
    I2S_MMAP_MIGRATION="absent"
    return
  fi

  case "$PREVIOUS_ACTION_I2S_OVERLAY" in
    added)
      sed -i '/^dtoverlay=i2s-mmap$/d' "$BOOT_CONFIG"
      I2S_MMAP_MIGRATION="removed_lafvin_added"
      ok "Removed obsolete LAFVIN-added overlay: $line"
      ;;
    uncommented)
      sed -i 's/^dtoverlay=i2s-mmap$/#dtoverlay=i2s-mmap/' "$BOOT_CONFIG"
      I2S_MMAP_MIGRATION="restored_lafvin_uncommented"
      ok "Restored obsolete overlay to its pre-LAFVIN commented state: $line"
      ;;
    *)
      I2S_MMAP_MIGRATION="preserved_unowned"
      warn "Preserving unowned obsolete overlay entry: $line"
      warn "Remove it manually only after confirming another setup does not own it."
      ;;
  esac
}

write_hardware_state() {
  if [[ -f "$HARDWARE_STATE" ]]; then
    warn "Preserving existing hardware ownership state: $HARDWARE_STATE"
    return
  fi
  install -d -m 0700 -o root -g root "$HARDWARE_STATE_DIR"
  local state_tmp
  state_tmp="$(mktemp)"
  {
    printf 'LAFVIN_WM8960_STATE_VERSION=1\n'
    printf 'LAFVIN_WM8960_BACKUP_DIR=%q\n' "$OWNERSHIP_BACKUP_DIR"
    printf 'LAFVIN_WM8960_BOOT_CONFIG=%q\n' "$BOOT_CONFIG"
    printf 'LAFVIN_WM8960_MODULES_FILE=%q\n' "$MODULES_FILE"
    printf 'LAFVIN_ACTION_MODULE_I2C_DEV=%q\n' "$ACTION_MODULE_I2C_DEV"
    printf 'LAFVIN_ACTION_MODULE_CODEC=%q\n' "$ACTION_MODULE_CODEC"
    printf 'LAFVIN_ACTION_MODULE_CARD=%q\n' "$ACTION_MODULE_CARD"
    printf 'LAFVIN_ACTION_I2C_PARAM=%q\n' "$ACTION_I2C_PARAM"
    printf 'LAFVIN_ACTION_I2S_PARAM=%q\n' "$ACTION_I2S_PARAM"
    printf 'LAFVIN_ACTION_I2S_OVERLAY=%q\n' "$ACTION_I2S_OVERLAY"
    printf 'LAFVIN_ACTION_WM8960_OVERLAY=%q\n' "$ACTION_WM8960_OVERLAY"
    printf 'LAFVIN_WM8960_INSTALLED_AT=%q\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >"$state_tmp"
  install -m 0600 -o root -g root "$state_tmp" "$HARDWARE_STATE"
  rm -f "$state_tmp"
}

write_profile_state() {
  STEP[profile_state]="running"
  install -d -m 0700 -o root -g root "$HARDWARE_STATE_DIR"
  local state_tmp
  state_tmp="$(mktemp)"
  {
    printf 'LAFVIN_WM8960_PROFILE_STATE_VERSION=1\n'
    printf 'LAFVIN_WM8960_PROFILE_NAME=%q\n' "$PROFILE_NAME"
    printf 'LAFVIN_WM8960_PROFILE_VERSION=%q\n' "$PROFILE_VERSION"
    printf 'LAFVIN_WM8960_PROFILE_LICENSE=%q\n' "$PROFILE_LICENSE"
    printf 'LAFVIN_WM8960_RESOURCE_SHA256=%q\n' "$PROFILE_ARCHIVE_SHA256"
    printf 'LAFVIN_WM8960_BACKUP_DIR=%q\n' "$OWNERSHIP_BACKUP_DIR"
    printf 'LAFVIN_WM8960_RPI_MODEL=%q\n' "$RPI_MODEL"
    printf 'LAFVIN_WM8960_I2S_MMAP_MIGRATION=%q\n' "$I2S_MMAP_MIGRATION"
    printf 'LAFVIN_WM8960_BOOT_CONFIG=%q\n' "$BOOT_CONFIG"
    printf 'LAFVIN_WM8960_MODULES_FILE=%q\n' "$MODULES_FILE"
    printf 'LAFVIN_WM8960_TARGET_ETC_DIR=%q\n' "$TARGET_ETC_DIR"
    printf 'LAFVIN_WM8960_TARGET_BIN=%q\n' "$TARGET_BIN"
    printf 'LAFVIN_WM8960_SERVICE_PATH=%q\n' "$SERVICE_INSTALL_PATH"
    printf 'LAFVIN_WM8960_WIREPLUMBER_CONFIG=%q\n' "$WIREPLUMBER_CONFIG_PATH"
    printf 'LAFVIN_WM8960_WIREPLUMBER_CONFIG_SHA256=%q\n' \
      "$WIREPLUMBER_CONFIG_SHA256"
    printf 'LAFVIN_ACTION_MODULE_I2C_DEV=%q\n' "$ACTION_MODULE_I2C_DEV"
    printf 'LAFVIN_ACTION_MODULE_CODEC=%q\n' "$ACTION_MODULE_CODEC"
    printf 'LAFVIN_ACTION_MODULE_CARD=%q\n' "$ACTION_MODULE_CARD"
    printf 'LAFVIN_ACTION_I2C_PARAM=%q\n' "$ACTION_I2C_PARAM"
    printf 'LAFVIN_ACTION_I2S_PARAM=%q\n' "$ACTION_I2S_PARAM"
    printf 'LAFVIN_ACTION_I2S_OVERLAY=%q\n' "$ACTION_I2S_OVERLAY"
    printf 'LAFVIN_ACTION_WM8960_OVERLAY=%q\n' "$ACTION_WM8960_OVERLAY"
    printf 'LAFVIN_WM8960_PROFILE_INSTALLED_AT=%q\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >"$state_tmp"
  install -m 0600 -o root -g root "$state_tmp" "$PROFILE_STATE"
  rm -f "$state_tmp"
  STEP[profile_state]="ok"
}

enable_spi() {
  log "Attempting to enable SPI via raspi-config..."
  have_cmd raspi-config || die "raspi-config not found. Install it or enable SPI manually."
  raspi-config nonint do_spi 0
}

power_warning() {
  local warned=0

  if have_cmd vcgencmd; then
    local t
    t="$(vcgencmd get_throttled 2>/dev/null || true)"
    if [[ "$t" =~ throttled=0x([0-9a-fA-F]+) ]]; then
      if [[ "${BASH_REMATCH[1]}" != "0" ]]; then
        warn "Power/thermal flags since boot: $t"
        warn "This can indicate undervoltage/brownouts. Consider a stronger PSU/cable."
        warned=1
      fi
    fi
  fi

  if dmesg 2>/dev/null | grep -qiE "under-voltage|undervoltage|brownout|throttl"; then
    warn "Kernel log contains power-related warnings since boot (undervoltage/throttling)."
    warned=1
  fi

  [[ "$warned" -eq 0 ]] && ok "No obvious power warnings detected since boot."
}

print_summary() {
  echo
  echo "================ Summary ================"
  for k in preflight apt_update pkgs_install enable_interfaces unzip modules boot_config install_files service profile_state done; do
    printf "%-16s : %s\n" "$k" "${STEP[$k]}"
  done
  [[ -n "$BACKUP_DIR" ]] && echo "Backups saved in  : $BACKUP_DIR"
  echo "========================================="
}

on_error() {
  STEP[done]="failed"
  warn "Installer failed (line $1)."
  print_summary
  echo
  warn "Nothing was rolled back automatically. Use backups if you need to revert."
  exit 1
}
trap 'on_error $LINENO' ERR

cleanup() {
  if [[ -n "$EXTRACT_DIR" && -d "$EXTRACT_DIR" ]]; then
    rm -rf "$EXTRACT_DIR"
  fi
}
trap cleanup EXIT

# ----------------------------
# Preflight (NO changes)
# ----------------------------
need_root
RPI_MODEL="$(read_rpi_model || true)"
is_supported_pi "$RPI_MODEL" || die \
  "Supported boards are Raspberry Pi Zero 2 W, Pi 3 Model B+, Pi 4 Model B, and Pi 5."
load_previous_profile_state
load_previous_ownership_state

STEP[preflight]="running"

have_cmd apt-get || die "apt-get not found."
have_cmd dpkg    || die "dpkg not found."

if [[ ! -e "$BOOT_CONFIG" && -e /boot/config.txt ]]; then
  BOOT_CONFIG="/boot/config.txt"
fi
[[ -e "$BOOT_CONFIG" ]] || die "Expected boot config not found at: $BOOT_CONFIG"
[[ -w "$BOOT_CONFIG" ]] || die "Boot config is not writable: $BOOT_CONFIG"

OVERLAY_DIR="$(dirname "$BOOT_CONFIG")/overlays"
WM8960_OVERLAY_FILE="${OVERLAY_DIR}/wm8960-soundcard.dtbo"
[[ -f "$WM8960_OVERLAY_FILE" ]] || die \
  "Required Raspberry Pi overlay is missing: $WM8960_OVERLAY_FILE"

[[ -f "$ZIP_NAME" ]] || die "Missing $ZIP_NAME"
have_cmd sha256sum || die "sha256sum is required to verify the WM8960 profile archive."
archive_sha256="$(sha256sum "$ZIP_NAME" | awk '{print $1}')"
[[ "$archive_sha256" == "$PROFILE_ARCHIVE_SHA256" ]] || die \
  "WM8960 profile archive checksum mismatch: expected $PROFILE_ARCHIVE_SHA256, got $archive_sha256"
if [[ -e "$WIREPLUMBER_CONFIG_PATH" ]] \
  && ! grep -qxF "$WIREPLUMBER_CONFIG_MARKER" "$WIREPLUMBER_CONFIG_PATH"; then
  die "Refusing to replace unmanaged WirePlumber config: $WIREPLUMBER_CONFIG_PATH"
fi

missing=()
for p in "${REQUIRED_PKGS[@]}"; do
  if pkg_missing "$p"; then
    missing+=("$p")
  fi
done

echo
echo "This installer will:"
echo "  1) Update APT metadata when required packages are missing"
echo "  2) Ensure SPI, I2C, and I2S are enabled"
echo "  3) Install missing packages (if any): ${missing[*]:-(none)}"
echo "  4) Unzip $ZIP_NAME and install WM8960 config/service"
echo "  5) Edit: $BOOT_CONFIG  (with a timestamped backup)"
echo "  6) Edit: $MODULES_FILE (with a timestamped backup)"
echo "  7) Apply and verify the LAFVIN HAT mixer calibration when available"
echo "  8) Keep WirePlumber from replacing the calibrated capture volume"
echo
if [[ "$ASSUME_YES" != true ]]; then
  read -r -p "Proceed? [y/N] " ans
  ans="${ans:-N}"
  [[ "$ans" =~ ^[Yy]$ ]] || die "Cancelled by user."
fi

STEP[preflight]="ok"

# ----------------------------
# Backups (before any edits)
# ----------------------------
ts="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/var/backups/lafvin-hat/lafvin-hat-wm8960-$ts"
mkdir -p "$BACKUP_DIR"
ok "Backups will be written to: $BACKUP_DIR"

OWNERSHIP_BACKUP_DIR="${PREVIOUS_BACKUP_DIR:-$BACKUP_DIR}"
if [[ -n "$PREVIOUS_BACKUP_DIR" ]]; then
  ok "Preserving original uninstall backup: $OWNERSHIP_BACKUP_DIR"
fi

backup_file "$BOOT_CONFIG"
backup_file "$MODULES_FILE"
backup_file /etc/asound.conf
backup_file /var/lib/alsa/asound.state
backup_file "$TARGET_BIN"
backup_file "$TARGET_SERVICE"
backup_file "$ALT_SERVICE"

# ----------------------------
# Execute steps (fail fast)
# ----------------------------
STEP[apt_update]="running"
if [[ "${#missing[@]}" -gt 0 ]]; then
  apt-get update
  STEP[apt_update]="ok"
else
  STEP[apt_update]="skipped (packages already installed)"
fi

STEP[pkgs_install]="running"
if [[ "${#missing[@]}" -gt 0 ]]; then
  apt-get install -y "${missing[@]}"
fi
STEP[pkgs_install]="ok"

STEP[enable_interfaces]="running"
enable_spi
raspi-config nonint do_i2c 0
STEP[enable_interfaces]="ok"

STEP[unzip]="running"
EXTRACT_DIR="$(mktemp -d)"
unzip -o "$ZIP_NAME" -d "$EXTRACT_DIR"
cd "$EXTRACT_DIR/lafvin-hat-wm8960-v4"
STEP[unzip]="ok"

STEP[modules]="running"
[[ -e "$MODULES_FILE" ]] || touch "$MODULES_FILE"
ensure_line_in_file "$MODULES_FILE" "i2c-dev" ACTION_MODULE_I2C_DEV
carry_forward_action ACTION_MODULE_I2C_DEV "$PREVIOUS_ACTION_MODULE_I2C_DEV"
ensure_line_in_file "$MODULES_FILE" "snd-soc-wm8960" ACTION_MODULE_CODEC
carry_forward_action ACTION_MODULE_CODEC "$PREVIOUS_ACTION_MODULE_CODEC"
ensure_line_in_file \
  "$MODULES_FILE" "snd-soc-wm8960-soundcard" ACTION_MODULE_CARD
carry_forward_action ACTION_MODULE_CARD "$PREVIOUS_ACTION_MODULE_CARD"
STEP[modules]="ok"

STEP[boot_config]="running"
safe_uncomment_or_append \
  "$BOOT_CONFIG" "dtparam=i2c_arm=on" ACTION_I2C_PARAM
carry_forward_action ACTION_I2C_PARAM "$PREVIOUS_ACTION_I2C_PARAM"
safe_uncomment_or_append "$BOOT_CONFIG" "dtparam=i2s=on" ACTION_I2S_PARAM
carry_forward_action ACTION_I2S_PARAM "$PREVIOUS_ACTION_I2S_PARAM"
migrate_obsolete_i2s_mmap
ensure_line_in_file \
  "$BOOT_CONFIG" "dtoverlay=wm8960-soundcard" ACTION_WM8960_OVERLAY
carry_forward_action ACTION_WM8960_OVERLAY "$PREVIOUS_ACTION_WM8960_OVERLAY"
STEP[boot_config]="ok"

STEP[install_files]="running"
mkdir -p "$TARGET_ETC_DIR"
cp -f ./asound.conf "$TARGET_ETC_DIR/"
cp -f ./*.state "$TARGET_ETC_DIR/"
cp -f ./wm8960-soundcard /usr/bin/
install -d -m 0755 "$WIREPLUMBER_CONFIG_DIR"
install -m 0644 ./51-lafvin-hat-wm8960.conf "$WIREPLUMBER_CONFIG_PATH"
WIREPLUMBER_CONFIG_SHA256="$(sha256sum "$WIREPLUMBER_CONFIG_PATH" | awk '{print $1}')"
# Service path varies between distributions; record the managed path.
if [[ -d "$(dirname "$TARGET_SERVICE")" ]]; then
  cp -f ./wm8960-soundcard.service "$TARGET_SERVICE"
  SERVICE_INSTALL_PATH="$TARGET_SERVICE"
else
  cp -f ./wm8960-soundcard.service "$ALT_SERVICE"
  SERVICE_INSTALL_PATH="$ALT_SERVICE"
fi
chmod 0755 /usr/bin/wm8960-soundcard
STEP[install_files]="ok"

STEP[service]="running"
systemctl daemon-reload
# Rebuild enablement links so upgrades from v1 do not retain its early
# sysinit.target ordering.
systemctl reenable wm8960-soundcard.service

if grep -qi "wm8960" /proc/asound/cards 2>/dev/null; then
  systemctl restart wm8960-soundcard.service
  if ! systemctl is-active --quiet wm8960-soundcard.service; then
    warn "wm8960-soundcard.service is not active after restart."
    systemctl status wm8960-soundcard.service --no-pager -l || true
    if [[ -f /var/log/wm8960-soundcard.log ]]; then
      warn "Last 200 lines of /var/log/wm8960-soundcard.log:"
      tail -n 200 /var/log/wm8960-soundcard.log || true
    fi
    die "Service failed to start."
  fi
else
  warn "WM8960 is not registered yet. This is expected before the first reboot."
fi
STEP[service]="ok"

STEP[done]="ok"
write_hardware_state
write_profile_state

# ----------------------------
# Wrap-up
# ----------------------------
print_summary
echo
echo "--------------------------------------------------------------"
echo "Reboot recommended to apply all settings cleanly."
echo "  sudo reboot"
echo "The reboot also reloads the WM8960 WirePlumber soft-mixer rule."
echo "--------------------------------------------------------------"

power_warning
