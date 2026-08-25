#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=false
ASSUME_YES=false
PROFILE_NAME="lafvin-hat-wm8960"
STATE_DIR="/var/lib/lafvin-hat-hardware"
LEGACY_STATE="${STATE_DIR}/wm8960-install.env"
PROFILE_STATE="${STATE_DIR}/lafvin-hat-wm8960-profile.env"
TARGET_ETC_DIR="/etc/wm8960-soundcard"
TARGET_BIN="/usr/bin/wm8960-soundcard"
TARGET_SERVICE="/lib/systemd/system/wm8960-soundcard.service"
ALT_SERVICE="/usr/lib/systemd/system/wm8960-soundcard.service"
SERVICE_PATH="$TARGET_SERVICE"
WIREPLUMBER_CONFIG=""
WIREPLUMBER_CONFIG_SHA256=""
BOOT_CONFIG="/boot/firmware/config.txt"
MODULES_FILE="/etc/modules"
BACKUP_DIR=""
STATE_KIND=""

ACTION_MODULE_I2C_DEV="unknown"
ACTION_MODULE_CODEC="unknown"
ACTION_MODULE_CARD="unknown"
ACTION_I2C_PARAM="unknown"
ACTION_I2S_PARAM="unknown"
ACTION_I2S_OVERLAY="unknown"
ACTION_WM8960_OVERLAY="unknown"

usage() {
  cat <<'EOF'
Usage: sudo bash uninstall_driver.sh [--dry-run] [--yes]

Remove only the recorded LAFVIN HAT WM8960 profile. Runtime
deployment, source, data, logs, packages, fonts, and shared SPI setup remain.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --yes|-y) ASSUME_YES=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

die() { echo "error: $*" >&2; exit 1; }
[[ "${EUID}" -eq 0 ]] || die "Run this uninstaller as root."
[[ -r /proc/device-tree/model ]] || die "Raspberry Pi model information missing."
grep -q "Raspberry Pi" /proc/device-tree/model || \
  die "This uninstaller only supports Raspberry Pi."

[[ -f "$BOOT_CONFIG" ]] || BOOT_CONFIG="/boot/config.txt"

load_profile_state() {
  [[ "$(stat -c '%U' "$PROFILE_STATE")" == root ]] || \
    die "Refusing profile state not owned by root: $PROFILE_STATE"
  # shellcheck disable=SC1090
  source "$PROFILE_STATE"
  [[ "${LAFVIN_WM8960_PROFILE_STATE_VERSION:-}" == 1 ]] || \
    die "Unsupported WM8960 profile-state version."
  [[ "${LAFVIN_WM8960_PROFILE_NAME:-}" == "$PROFILE_NAME" ]] || \
    die "Profile state does not describe $PROFILE_NAME."
  STATE_KIND="profile"
}

load_legacy_state() {
  [[ "$(stat -c '%U' "$LEGACY_STATE")" == root ]] || \
    die "Refusing hardware state not owned by root: $LEGACY_STATE"
  # shellcheck disable=SC1090
  source "$LEGACY_STATE"
  [[ "${LAFVIN_WM8960_STATE_VERSION:-}" == 1 ]] || \
    die "Unsupported legacy WM8960 ownership-state version."
  STATE_KIND="legacy"
}

if [[ -f "$PROFILE_STATE" ]]; then
  load_profile_state
elif [[ -f "$LEGACY_STATE" ]]; then
  load_legacy_state
else
  die "No recorded WM8960 ownership state exists; preserving unknown resources."
fi

BACKUP_DIR="${LAFVIN_WM8960_BACKUP_DIR:-}"
BOOT_CONFIG="${LAFVIN_WM8960_BOOT_CONFIG:-$BOOT_CONFIG}"
MODULES_FILE="${LAFVIN_WM8960_MODULES_FILE:-$MODULES_FILE}"
TARGET_ETC_DIR="${LAFVIN_WM8960_TARGET_ETC_DIR:-$TARGET_ETC_DIR}"
TARGET_BIN="${LAFVIN_WM8960_TARGET_BIN:-$TARGET_BIN}"
SERVICE_PATH="${LAFVIN_WM8960_SERVICE_PATH:-$SERVICE_PATH}"
WIREPLUMBER_CONFIG="${LAFVIN_WM8960_WIREPLUMBER_CONFIG:-}"
WIREPLUMBER_CONFIG_SHA256="${LAFVIN_WM8960_WIREPLUMBER_CONFIG_SHA256:-}"
ACTION_MODULE_I2C_DEV="${LAFVIN_ACTION_MODULE_I2C_DEV:-unknown}"
ACTION_MODULE_CODEC="${LAFVIN_ACTION_MODULE_CODEC:-unknown}"
ACTION_MODULE_CARD="${LAFVIN_ACTION_MODULE_CARD:-unknown}"
ACTION_I2C_PARAM="${LAFVIN_ACTION_I2C_PARAM:-unknown}"
ACTION_I2S_PARAM="${LAFVIN_ACTION_I2S_PARAM:-unknown}"
ACTION_I2S_OVERLAY="${LAFVIN_ACTION_I2S_OVERLAY:-unknown}"
ACTION_WM8960_OVERLAY="${LAFVIN_ACTION_WM8960_OVERLAY:-unknown}"

echo "LAFVIN HAT $PROFILE_NAME removal plan ($STATE_KIND ownership state):"
echo "  stop/remove service: wm8960-soundcard.service"
echo "  remove recorded helper: $TARGET_BIN"
echo "  remove recorded profile config: $TARGET_ETC_DIR"
if [[ -n "$WIREPLUMBER_CONFIG" ]]; then
  echo "  remove recorded WirePlumber rule when unchanged: $WIREPLUMBER_CONFIG"
fi
echo "  restore/remove only recorded WM8960 module and boot entries"
echo "  restore recorded ALSA backups when available"
echo "  preserve Runtime source, deployment, configuration, Apps, data, and logs"
echo "  preserve apt packages, fonts, and shared SPI setup"

if systemctl is-active --quiet lafvin-hat.service; then
  if [[ "$DRY_RUN" == true ]]; then
    echo "  warning: lafvin-hat.service is active and must be stopped first"
  else
    die "Stop or undeploy lafvin-hat.service before removing its audio profile."
  fi
fi

if [[ "$DRY_RUN" == true ]]; then
  echo "Dry-run complete; no changes made."
  exit 0
fi
if [[ "$ASSUME_YES" != true ]]; then
  read -r -p "Remove the recorded LAFVIN HAT WM8960 profile? [y/N] " answer
  [[ "${answer:-N}" =~ ^[Yy]$ ]] || { echo "Cancelled."; exit 1; }
fi

restore_backup() {
  local name="$1"
  local destination="$2"
  [[ -n "$BACKUP_DIR" ]] || return 0
  case "$BACKUP_DIR" in
    /var/backups/lafvin-hat/lafvin-hat-wm8960-*|/var/backups/lafvin-hat/wm8960-*) ;;
    *) echo "Ignoring unexpected backup directory: $BACKUP_DIR" >&2; return 0 ;;
  esac
  [[ -e "$BACKUP_DIR/$name" ]] || return 0
  if [[ -L "$BACKUP_DIR/$name" ]] && \
    [[ "$(readlink "$BACKUP_DIR/$name")" == *wm8960-soundcard* ]]; then
    echo "Skipping profile-owned backup symlink: $name" >&2
    return 0
  fi
  cp -a -- "$BACKUP_DIR/$name" "$destination"
  echo "Restored backup: $destination"
}

remove_exact_line() {
  local file="$1"
  local line="$2"
  [[ -f "$file" ]] || return 0
  local escaped
  escaped="$(printf '%s' "$line" | sed 's/[][\\.^$*+?{}|()]/\\&/g')"
  sed -i "/^${escaped}$/d" "$file"
}

comment_exact_line() {
  local file="$1"
  local line="$2"
  [[ -f "$file" ]] || return 0
  local escaped
  escaped="$(printf '%s' "$line" | sed 's/[][\\.^$*+?{}|()]/\\&/g')"
  sed -i "s|^${escaped}$|#${line}|" "$file"
}

restore_recorded_line() {
  local file="$1"
  local line="$2"
  local action="$3"
  local description="$4"
  case "$action" in
    added)
      remove_exact_line "$file" "$line"
      echo "Removed LAFVIN-added $description: $line"
      ;;
    uncommented)
      comment_exact_line "$file" "$line"
      echo "Restored commented $description: $line"
      ;;
    *)
      echo "Preserved pre-existing $description: $line"
      ;;
  esac
}

remove_wireplumber_config() {
  [[ -n "$WIREPLUMBER_CONFIG" && -e "$WIREPLUMBER_CONFIG" ]] || return 0
  case "$WIREPLUMBER_CONFIG" in
    /etc/wireplumber/wireplumber.conf.d/51-lafvin-hat-wm8960.conf) ;;
    *)
      echo "Preserved unexpected WirePlumber config path: $WIREPLUMBER_CONFIG" >&2
      return 0
      ;;
  esac
  local observed
  observed="$(sha256sum "$WIREPLUMBER_CONFIG" | awk '{print $1}')"
  if [[ -n "$WIREPLUMBER_CONFIG_SHA256" \
    && "$observed" == "$WIREPLUMBER_CONFIG_SHA256" ]]; then
    rm -f -- "$WIREPLUMBER_CONFIG"
    rmdir "$(dirname "$WIREPLUMBER_CONFIG")" >/dev/null 2>&1 || true
    echo "Removed recorded WirePlumber rule: $WIREPLUMBER_CONFIG"
  else
    echo "Preserved modified WirePlumber rule: $WIREPLUMBER_CONFIG" >&2
  fi
}

systemctl disable --now wm8960-soundcard.service >/dev/null 2>&1 || true
rm -f -- "$SERVICE_PATH"
if [[ "$STATE_KIND" == legacy ]]; then
  rm -f -- "$TARGET_SERVICE" "$ALT_SERVICE"
fi
systemctl daemon-reload

if [[ -L /etc/asound.conf ]] && \
  [[ "$(readlink /etc/asound.conf)" == "$TARGET_ETC_DIR/asound.conf" ]]; then
  rm -f /etc/asound.conf
  restore_backup asound.conf /etc/asound.conf
fi
if [[ -L /var/lib/alsa/asound.state ]] && \
  [[ "$(readlink /var/lib/alsa/asound.state)" == \
    "$TARGET_ETC_DIR/wm8960_asound.state" ]]; then
  rm -f /var/lib/alsa/asound.state
  restore_backup asound.state /var/lib/alsa/asound.state
fi

rm -f -- "$TARGET_BIN"
restore_backup wm8960-soundcard "$TARGET_BIN"
rm -rf -- "$TARGET_ETC_DIR"
remove_wireplumber_config

echo "Preserved shared I2C setting: dtparam=i2c_arm=on"
restore_recorded_line "$BOOT_CONFIG" "dtparam=i2s=on" \
  "$ACTION_I2S_PARAM" "I2S setting"
if [[ "$ACTION_I2S_OVERLAY" == "not_required" ]]; then
  echo "Obsolete i2s-mmap overlay was not required by this profile"
else
  restore_recorded_line "$BOOT_CONFIG" "dtoverlay=i2s-mmap" \
    "$ACTION_I2S_OVERLAY" "I2S overlay"
fi
restore_recorded_line "$BOOT_CONFIG" "dtoverlay=wm8960-soundcard" \
  "$ACTION_WM8960_OVERLAY" "WM8960 overlay"
echo "Preserved shared I2C module: i2c-dev"
restore_recorded_line "$MODULES_FILE" "snd-soc-wm8960" \
  "$ACTION_MODULE_CODEC" "WM8960 codec module"
restore_recorded_line "$MODULES_FILE" "snd-soc-wm8960-soundcard" \
  "$ACTION_MODULE_CARD" "WM8960 card module"

rm -f -- "$PROFILE_STATE" "$LEGACY_STATE"
rmdir "$STATE_DIR" >/dev/null 2>&1 || true

echo "LAFVIN HAT WM8960 profile removed. Reboot to unload active modules: sudo reboot"
