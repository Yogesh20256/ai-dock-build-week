#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/ai-dock"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/ai-dock"

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v hyprctl >/dev/null || { echo "AI Dock's desktop layer currently requires Hyprland" >&2; exit 1; }

python3 -m venv --system-site-packages "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --keyring-provider skip --upgrade pip
"$ROOT/.venv/bin/pip" install --keyring-provider skip -r "$ROOT/requirements.txt"
"$ROOT/.venv/bin/playwright" install chromium

mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$HOME/.local/share/applications"
if [[ -f "$CONFIG_DIR/mcp_servers.json" ]]; then
  cp -a "$CONFIG_DIR/mcp_servers.json" "$CONFIG_DIR/mcp_servers.json.backup.$(date +%Y%m%d-%H%M%S)"
fi
python3 "$ROOT/make_config.py" "$ROOT" "$CONFIG_DIR/mcp_servers.json"

sed "s|@ROOT@|$ROOT|g" "$ROOT/packaging/ai-dock.desktop.in" > "$HOME/.local/share/applications/ai-dock.desktop"
chmod +x "$ROOT/ai-dock" "$ROOT/install.sh"
echo "Installed. Start with: $ROOT/ai-dock"
