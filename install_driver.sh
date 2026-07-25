#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

detect_platform() {
  local model=""
  if [[ -r /proc/device-tree/model ]]; then
    model="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || true)"
  fi

  if [[ "${model}" == *"Raspberry Pi"* ]]; then
    echo "raspberry_pi"
    return 0
  fi
  return 1
}

platform="$(detect_platform || true)"
case "${platform}" in
  raspberry_pi)
    case "${1:-}" in
      --check|--status)
        shift
        exec bash \
          "${SCRIPT_DIR}/deploy/hardware/check_wm8960_raspberry_pi.sh" \
          "$@"
        ;;
    esac
    exec bash \
      "${SCRIPT_DIR}/deploy/hardware/install_wm8960_raspberry_pi.sh" \
      "$@"
    ;;
  *)
    echo "Unsupported or unknown hardware platform." >&2
    echo "M6.5 currently supports Raspberry Pi only." >&2
    exit 1
    ;;
esac
