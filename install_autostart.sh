#!/usr/bin/env bash
set -eu

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="bedford-range-feedbackscreen.service"
SERVICE_SOURCE="$SCRIPT_DIR/$SERVICE_NAME"
SERVICE_TARGET="/etc/systemd/system/$SERVICE_NAME"

if [[ ! -f "$SERVICE_SOURCE" ]]; then
    printf 'Missing service file: %s\n' "$SERVICE_SOURCE" >&2
    exit 1
fi

sudo install -m 0644 "$SERVICE_SOURCE" "$SERVICE_TARGET"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

printf 'Installed and started %s\n' "$SERVICE_NAME"
printf 'Check status with: sudo systemctl status %s\n' "$SERVICE_NAME"