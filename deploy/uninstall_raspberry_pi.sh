#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=false
ASSUME_YES=false
SERVICE_NAME="lafvin-hat.service"
DEPLOYMENT_METADATA="/etc/lafvin-hat/deployment.env"

usage() {
  cat <<'EOF'
Usage: sudo bash deploy/uninstall_raspberry_pi.sh [--dry-run] [--yes]

Remove LAFVIN HAT Runtime service integration. The checkout, virtual
environment, Runtime configuration, application data, logs, packages, and
hardware driver are preserved.
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

[[ "${EUID}" -eq 0 ]] || { echo "Run this uninstaller as root." >&2; exit 1; }
[[ -f "$DEPLOYMENT_METADATA" ]] || {
  echo "Deployment metadata not found: $DEPLOYMENT_METADATA" >&2
  echo "Run the deployment installer once before using managed undeploy." >&2
  exit 1
}
[[ "$(stat -c '%U' "$DEPLOYMENT_METADATA")" == root ]] || {
  echo "Refusing metadata not owned by root: $DEPLOYMENT_METADATA" >&2
  exit 1
}

# shellcheck disable=SC1090
source "$DEPLOYMENT_METADATA"
: "${LAFVIN_DEPLOYMENT_VERSION:?Missing deployment version}"
: "${LAFVIN_SOURCE_DIR:?Missing checkout path}"
: "${LAFVIN_VENV_DIR:?Missing virtual environment path}"
: "${LAFVIN_SERVICE_UNIT:?Missing service unit path}"
: "${LAFVIN_CLI_LINK:?Missing CLI link path}"
case "$LAFVIN_DEPLOYMENT_VERSION" in
  1)
    [[ "$LAFVIN_CLI_LINK" == /usr/local/bin/lafvin ]] || {
      echo "Refusing unexpected CLI path: $LAFVIN_CLI_LINK" >&2
      exit 1
    }
    CLI_TARGET="${LAFVIN_VENV_DIR}/bin/lafvin"
    LAFVIN_LEGACY_CLI_LINK=""
    ;;
  2)
    [[ "$LAFVIN_CLI_LINK" == /usr/local/bin/lafvin-hat ]] || {
      echo "Refusing unexpected CLI path: $LAFVIN_CLI_LINK" >&2
      exit 1
    }
    LAFVIN_LEGACY_CLI_LINK="${LAFVIN_LEGACY_CLI_LINK:-}"
    [[ -z "$LAFVIN_LEGACY_CLI_LINK" || "$LAFVIN_LEGACY_CLI_LINK" == /usr/local/bin/lafvin ]] || {
      echo "Refusing unexpected legacy CLI path: $LAFVIN_LEGACY_CLI_LINK" >&2
      exit 1
    }
    CLI_TARGET="${LAFVIN_VENV_DIR}/bin/lafvin-hat"
    ;;
  *)
    echo "Unsupported deployment metadata version." >&2
    exit 1
    ;;
esac
[[ "$LAFVIN_SERVICE_UNIT" == /etc/systemd/system/lafvin-hat.service ]] || {
  echo "Refusing unexpected service path: $LAFVIN_SERVICE_UNIT" >&2
  exit 1
}

echo "LAFVIN HAT Runtime undeploy plan:"
echo "  remove service: $LAFVIN_SERVICE_UNIT"
echo "  remove CLI link when owned: $LAFVIN_CLI_LINK"
if [[ -n "$LAFVIN_LEGACY_CLI_LINK" ]]; then
  echo "  remove legacy CLI link when owned: $LAFVIN_LEGACY_CLI_LINK"
fi
echo "  remove metadata: $DEPLOYMENT_METADATA"
echo "  preserve checkout: $LAFVIN_SOURCE_DIR"
echo "  preserve virtual environment: $LAFVIN_VENV_DIR"
echo "  preserve configuration: /etc/lafvin-hat/runtime.env"
echo "  preserve data: /var/lib/lafvin-hat"
echo "  preserve logs: /var/log/lafvin-hat"
echo "  preserve packages, interfaces, and WM8960 hardware driver"

if [[ "$DRY_RUN" == true ]]; then
  echo "Dry-run complete; no changes made."
  exit 0
fi
if [[ "$ASSUME_YES" != true ]]; then
  read -r -p "Remove Runtime service integration? [y/N] " answer
  [[ "${answer:-N}" =~ ^[Yy]$ ]] || { echo "Cancelled."; exit 1; }
fi

if [[ -f "$LAFVIN_SERVICE_UNIT" ]]; then
  grep -q '^# Managed by LAFVIN HAT checkout deployment\.$' \
    "$LAFVIN_SERVICE_UNIT" || {
      echo "Refusing unrecognized service unit: $LAFVIN_SERVICE_UNIT" >&2
      exit 1
    }
fi

systemctl disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
rm -f -- "$LAFVIN_SERVICE_UNIT"

remove_managed_cli_link() {
  local link_path="$1"
  local expected_target="$2"
  local cli_target

  if [[ -L "$link_path" ]]; then
    cli_target="$(readlink "$link_path")"
    if [[ "$cli_target" == "$expected_target" ]]; then
      rm -f -- "$link_path"
    else
      echo "Preserving changed CLI link: $link_path -> $cli_target" >&2
    fi
  elif [[ -e "$link_path" ]]; then
    echo "Preserving non-symlink CLI path: $link_path" >&2
  fi
}

remove_managed_cli_link "$LAFVIN_CLI_LINK" "$CLI_TARGET"
if [[ -n "$LAFVIN_LEGACY_CLI_LINK" ]]; then
  remove_managed_cli_link \
    "$LAFVIN_LEGACY_CLI_LINK" \
    "${LAFVIN_VENV_DIR}/bin/lafvin"
fi

rm -f -- "$DEPLOYMENT_METADATA"
systemctl daemon-reload

echo "Runtime service integration removed."
echo "Checkout, configuration, data, logs, and hardware were preserved."
