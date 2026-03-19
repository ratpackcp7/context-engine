#!/usr/bin/env bash
set -euo pipefail
# Install Context Engine systemd user units
# Run as chris: bash systemd/install.sh

UNIT_DIR="$HOME/.config/systemd/user"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing systemd user units..."
cp "$SCRIPT_DIR/context-engine.service" "$UNIT_DIR/"
cp "$SCRIPT_DIR/context-engine-compile.service" "$UNIT_DIR/"
cp "$SCRIPT_DIR/context-engine-compile.timer" "$UNIT_DIR/"

echo "Reloading systemd..."
systemctl --user daemon-reload

echo "Enabling and starting context-engine.service..."
systemctl --user enable --now context-engine.service

echo "Enabling and starting context-engine-compile.timer..."
systemctl --user enable --now context-engine-compile.timer

echo "Done. Checking status..."
systemctl --user status context-engine.service --no-pager
echo "---"
systemctl --user list-timers --no-pager | grep context
