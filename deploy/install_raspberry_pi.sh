#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TARGET_USER="${SUDO_USER:-}"
SERVICE_NAME="lafvin-hat.service"
SERVICE_UNIT="/etc/systemd/system/${SERVICE_NAME}"
DEPLOYMENT_DIR="/etc/lafvin-hat"
DEPLOYMENT_METADATA="${DEPLOYMENT_DIR}/deployment.env"
RUNTIME_ENV="${DEPLOYMENT_DIR}/runtime.env"
PROJECT_ENV="${SOURCE_DIR}/.env"
CLI_LINK="/usr/local/bin/lafvin-hat"
LEGACY_CLI_LINK="/usr/local/bin/lafvin"
DATA_DIR="/var/lib/lafvin-hat"
LOG_DIR="/var/log/lafvin-hat"
SERVICE_WAS_ACTIVE=false
INSTALL_COMPLETE=false
SERVICE_REPLACED=false
SERVICE_HAD_EXISTING=false
SERVICE_BACKUP=""
CLI_REPLACED=false
CLI_HAD_EXISTING=false
OLD_CLI_TARGET=""
MANAGED_LEGACY_CLI_LINK=""
IMPORT_PROJECT_ENV=false
IMPORT_PROJECT_ENV_REQUESTED=false
RUNTIME_ENV_REPLACED=false
RUNTIME_ENV_HAD_EXISTING=false
RUNTIME_ENV_BACKUP=""
TEMP_FILES=()

usage() {
  cat <<'EOF'
Usage: sudo bash deploy/install_raspberry_pi.sh [--user USER] [--import-project-env]

Register the current Git checkout as the LAFVIN HAT systemd service.
This script does not install or update the hardware driver.

Options:
  --user USER             Run the Runtime as USER.
  --import-project-env    Copy checkout .env to the persistent runtime.env.
                          An existing runtime.env is backed up first.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      [[ $# -ge 2 ]] || { echo "--user requires a value" >&2; exit 2; }
      TARGET_USER="$2"
      shift 2
      ;;
    --import-project-env)
      IMPORT_PROJECT_ENV_REQUESTED=true
      shift
      ;;
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

die() { echo "error: $*" >&2; exit 1; }

cleanup() {
  local path
  for path in "${TEMP_FILES[@]}"; do
    [[ -n "$path" && -e "$path" ]] && rm -f -- "$path"
  done
}

restore_service_on_error() {
  local exit_code=$?
  if [[ "$RUNTIME_ENV_REPLACED" == true ]]; then
    if [[ "$RUNTIME_ENV_HAD_EXISTING" == true \
      && -n "$RUNTIME_ENV_BACKUP" \
      && -f "$RUNTIME_ENV_BACKUP" ]]; then
      install -m 0640 -o root -g "$TARGET_GROUP" \
        "$RUNTIME_ENV_BACKUP" "$RUNTIME_ENV" || true
    else
      rm -f -- "$RUNTIME_ENV"
    fi
  fi
  if [[ "$SERVICE_REPLACED" == true ]]; then
    if [[ "$SERVICE_HAD_EXISTING" == true && -n "$SERVICE_BACKUP" ]]; then
      install -m 0644 "$SERVICE_BACKUP" "$SERVICE_UNIT" || true
    else
      rm -f -- "$SERVICE_UNIT" || true
    fi
    systemctl daemon-reload >/dev/null 2>&1 || true
  fi
  if [[ "$CLI_REPLACED" == true ]]; then
    if [[ "$CLI_HAD_EXISTING" == true ]]; then
      ln -sfn "$OLD_CLI_TARGET" "$CLI_LINK" || true
    else
      rm -f -- "$CLI_LINK" || true
    fi
  fi
  if [[ "$INSTALL_COMPLETE" != true && "$SERVICE_WAS_ACTIVE" == true ]]; then
    echo "Installation failed; attempting to restore the previous service." >&2
    systemctl start "$SERVICE_NAME" >/dev/null 2>&1 || true
  fi
  cleanup
  exit "$exit_code"
}
trap restore_service_on_error ERR
trap cleanup EXIT

[[ -n "$TARGET_USER" && "$TARGET_USER" != root ]] || \
  die "Run via sudo from a normal user, or pass --user USER."
id "$TARGET_USER" >/dev/null 2>&1 || die "Unknown target user: $TARGET_USER"

SOURCE_OWNER="$(stat -c '%U' "$SOURCE_DIR")"
[[ "$SOURCE_OWNER" == "$TARGET_USER" ]] || die \
  "Checkout owner is $SOURCE_OWNER, not target user $TARGET_USER"

TARGET_GROUP="$(id -gn "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[[ -n "$TARGET_HOME" ]] || die "Unable to determine home for $TARGET_USER"

for required in \
  pyproject.toml \
  apps/catalog.yaml \
  deploy/systemd/lafvin-hat.service \
  deploy/render_systemd_service.py; do
  [[ -f "${SOURCE_DIR}/${required}" ]] || die "Missing checkout asset: $required"
done

for group in audio gpio spi; do
  if ! getent group "$group" >/dev/null 2>&1; then
    groupadd --system "$group"
  fi
  usermod -a -G "$group" "$TARGET_USER"
done

run_as_target() {
  runuser -u "$TARGET_USER" -- env HOME="$TARGET_HOME" "$@"
}

validate_project_env() {
  [[ -e "$PROJECT_ENV" || -L "$PROJECT_ENV" ]] || die \
    "Project environment file does not exist: $PROJECT_ENV"
  [[ ! -L "$PROJECT_ENV" && -f "$PROJECT_ENV" ]] || die \
    "Refusing project environment that is not a regular file: $PROJECT_ENV"
  local env_owner
  env_owner="$(stat -c '%U' "$PROJECT_ENV")"
  [[ "$env_owner" == "$TARGET_USER" ]] || die \
    "Project environment owner is $env_owner, not target user $TARGET_USER"
  run_as_target "${VENV_DIR}/bin/python" -c \
    'from lafvin_hat.runtime.config import load_env_file; import sys; load_env_file(sys.argv[1])' \
    "$PROJECT_ENV" || die "Invalid project environment file: $PROJECT_ENV"
}

choose_runtime_environment() {
  if [[ "$IMPORT_PROJECT_ENV_REQUESTED" == true ]]; then
    validate_project_env
    IMPORT_PROJECT_ENV=true
    return
  fi
  if [[ -e "$RUNTIME_ENV" || -L "$RUNTIME_ENV" ]]; then
    [[ ! -L "$RUNTIME_ENV" && -f "$RUNTIME_ENV" ]] || die \
      "Refusing runtime environment that is not a regular file: $RUNTIME_ENV"
    return
  fi
  if [[ ! -e "$PROJECT_ENV" && ! -L "$PROJECT_ENV" ]]; then
    return
  fi
  if [[ ! -t 0 ]]; then
    echo "Found $PROJECT_ENV but no interactive terminal."
    echo "Using the default runtime template; pass --import-project-env to import it."
    return
  fi

  echo
  echo "Found development environment: $PROJECT_ENV"
  echo "It may contain API keys or proxy credentials."
  read -r -p \
    "Copy a snapshot to $RUNTIME_ENV for the deployed Runtime? [y/N] " answer
  if [[ "${answer:-N}" =~ ^[Yy]$ ]]; then
    validate_project_env
    IMPORT_PROJECT_ENV=true
  fi
}

install_runtime_environment() {
  if [[ -e "$RUNTIME_ENV" || -L "$RUNTIME_ENV" ]]; then
    [[ ! -L "$RUNTIME_ENV" && -f "$RUNTIME_ENV" ]] || die \
      "Refusing runtime environment that is not a regular file: $RUNTIME_ENV"
    RUNTIME_ENV_HAD_EXISTING=true
  fi

  if [[ "$IMPORT_PROJECT_ENV" == true ]]; then
    if [[ "$RUNTIME_ENV_HAD_EXISTING" == true ]]; then
      local backup_dir backup_timestamp
      backup_dir="/var/backups/lafvin-hat"
      backup_timestamp="$(date +%Y%m%d-%H%M%S)"
      install -d -m 0700 -o root -g root "$backup_dir"
      RUNTIME_ENV_BACKUP="$(
        mktemp "${backup_dir}/runtime.env-${backup_timestamp}-XXXXXX"
      )"
      cp -a -- "$RUNTIME_ENV" "$RUNTIME_ENV_BACKUP"
      echo "Backed up existing Runtime environment: $RUNTIME_ENV_BACKUP"
    fi
    install -m 0640 -o root -g "$TARGET_GROUP" "$PROJECT_ENV" "$RUNTIME_ENV"
    RUNTIME_ENV_REPLACED=true
    echo "Imported project environment into: $RUNTIME_ENV"
    return
  fi

  if [[ "$RUNTIME_ENV_HAD_EXISTING" == true ]]; then
    chown root:"$TARGET_GROUP" "$RUNTIME_ENV"
    chmod 0640 "$RUNTIME_ENV"
    echo "Preserved existing Runtime environment: $RUNTIME_ENV"
    return
  fi

  install -m 0640 -o root -g "$TARGET_GROUP" \
    "${SOURCE_DIR}/deploy/runtime.env.example" "$RUNTIME_ENV"
  RUNTIME_ENV_REPLACED=true
  echo "Installed default Runtime environment template: $RUNTIME_ENV"
}

VENV_DIR="${SOURCE_DIR}/.venv"
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Creating checkout virtual environment..."
  run_as_target python3 -m venv "$VENV_DIR"
fi

echo "Refreshing checkout Python dependencies..."
run_as_target "${VENV_DIR}/bin/python" -m pip install \
  -e "${SOURCE_DIR}[hardware,ai]"

echo "Validating first-party application catalog..."
run_as_target "${VENV_DIR}/bin/python" \
  -m lafvin_hat.runtime.apps.catalog \
  "${SOURCE_DIR}/apps/catalog.yaml" \
  --project-root "$SOURCE_DIR"

choose_runtime_environment

if [[ -e "$CLI_LINK" && ! -L "$CLI_LINK" ]]; then
  die "Refusing to replace non-symlink: $CLI_LINK"
fi
if [[ -L "$CLI_LINK" ]]; then
  OLD_CLI_TARGET="$(readlink "$CLI_LINK")"
  case "$OLD_CLI_TARGET" in
    "${VENV_DIR}/bin/lafvin-hat"|/opt/lafvin-hat/.venv/bin/lafvin-hat) ;;
    *) die "Refusing to replace unrecognized CLI link: $CLI_LINK -> $OLD_CLI_TARGET" ;;
  esac
  CLI_HAD_EXISTING=true
fi

if [[ -L "$LEGACY_CLI_LINK" ]]; then
  legacy_cli_target="$(readlink "$LEGACY_CLI_LINK")"
  if [[ "$legacy_cli_target" == "${VENV_DIR}/bin/lafvin" ]]; then
    MANAGED_LEGACY_CLI_LINK="$LEGACY_CLI_LINK"
  fi
fi

if systemctl is-active --quiet "$SERVICE_NAME"; then
  SERVICE_WAS_ACTIVE=true
  systemctl stop "$SERVICE_NAME"
fi

install -d -m 0750 -o "$TARGET_USER" -g "$TARGET_GROUP" \
  "$DATA_DIR" "$DATA_DIR/apps" "$LOG_DIR"
chown -R "$TARGET_USER:$TARGET_GROUP" "$DATA_DIR/apps" "$LOG_DIR"

install -d -m 0750 -o root -g "$TARGET_GROUP" "$DEPLOYMENT_DIR"
install_runtime_environment

metadata_tmp="$(mktemp)"
TEMP_FILES+=("$metadata_tmp")
{
  printf 'LAFVIN_DEPLOYMENT_VERSION=2\n'
  printf 'LAFVIN_SOURCE_DIR=%q\n' "$SOURCE_DIR"
  printf 'LAFVIN_VENV_DIR=%q\n' "$VENV_DIR"
  printf 'LAFVIN_RUNTIME_USER=%q\n' "$TARGET_USER"
  printf 'LAFVIN_RUNTIME_GROUP=%q\n' "$TARGET_GROUP"
  printf 'LAFVIN_SERVICE_UNIT=%q\n' "$SERVICE_UNIT"
  printf 'LAFVIN_CLI_LINK=%q\n' "$CLI_LINK"
  printf 'LAFVIN_LEGACY_CLI_LINK=%q\n' "$MANAGED_LEGACY_CLI_LINK"
  printf 'LAFVIN_INSTALLED_AT=%q\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"$metadata_tmp"

service_tmp="$(mktemp)"
TEMP_FILES+=("$service_tmp")
python3 "${SOURCE_DIR}/deploy/render_systemd_service.py" \
  --template "${SOURCE_DIR}/deploy/systemd/lafvin-hat.service" \
  --output "$service_tmp" \
  --user "$TARGET_USER" \
  --group "$TARGET_GROUP" \
  --source-dir "$SOURCE_DIR" \
  --venv-dir "$VENV_DIR"
if [[ -f "$SERVICE_UNIT" ]]; then
  SERVICE_BACKUP="$(mktemp)"
  TEMP_FILES+=("$SERVICE_BACKUP")
  cp -a "$SERVICE_UNIT" "$SERVICE_BACKUP"
  SERVICE_HAD_EXISTING=true
fi
install -m 0644 "$service_tmp" "$SERVICE_UNIT"
SERVICE_REPLACED=true

ln -sfn "${VENV_DIR}/bin/lafvin-hat" "$CLI_LINK"
CLI_REPLACED=true

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
if [[ "$SERVICE_WAS_ACTIVE" == true ]]; then
  systemctl start "$SERVICE_NAME"
fi
install -m 0640 -o root -g "$TARGET_GROUP" \
  "$metadata_tmp" "$DEPLOYMENT_METADATA"

INSTALL_COMPLETE=true
trap - ERR

echo
echo "Installed checkout-backed LAFVIN HAT service."
echo "  Checkout: $SOURCE_DIR"
echo "  Runtime user: $TARGET_USER"
echo "  Environment: $RUNTIME_ENV"
echo "  Management command: $CLI_LINK"
echo
echo "Start now:"
echo "  sudo systemctl start lafvin-hat"
echo "After git pull, restart the service or reboot to load new code."
if [[ -d /opt/lafvin-hat/.venv ]]; then
  echo "Legacy /opt/lafvin-hat content was detected and preserved."
fi
