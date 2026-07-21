#!/usr/bin/env bash
# AI Dock — Windows/WSLg Installation Script
# This script configures system packages, Playwright, and background systemd services.

set -e

echo "=== AI Dock Windows/WSLg Setup ==="

# 1. Verify WSL
if ! grep -qsi "Microsoft" /proc/version && ! grep -qsi "WSL" /proc/version; then
    echo "[!] Warning: This script is intended to be run inside a WSL (Windows Subsystem for Linux) distribution."
    read -p "Do you want to continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 2. Verify systemd is active
if ! systemctl is-system-running >/dev/null 2>&1 && [ "$(ps -p 1 -o comm=)" != "systemd" ]; then
    echo "[X] Error: systemd is not running as PID 1 in WSL."
    echo "AI Dock requires systemd for its background automation timers."
    echo
    echo "To fix this, edit or create '/etc/wsl.conf' inside WSL and add the following lines:"
    echo "----------------------------"
    echo "[boot]"
    echo "systemd=true"
    echo "----------------------------"
    echo "Then, open a Windows PowerShell window and run:"
    echo "  wsl --shutdown"
    echo "And reopen your WSL terminal to run this script again."
    exit 1
fi

# 3. Install Debian/Ubuntu system packages
echo "[*] Installing system dependencies (GTK 4, WebKitGTK 6.0, Cairo)..."
sudo apt update
sudo apt install -y \
    python3 \
    python3-pip \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-4.0 \
    gir1.2-webkit-6.0 \
    libnotify-bin \
    libcairo2-dev \
    libgirepository1.0-dev \
    build-essential \
    curl

# 4. Install Python dependencies
echo "[*] Installing Playwright Python library..."
pip3 install --user --upgrade playwright

echo "[*] Setting up Playwright browsers..."
python3 -m playwright install chromium

# 5. Create and Register systemd timers
echo "[*] Configuring background scheduler and monitor timers..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config/systemd/user"

# Scheduler Service & Timer
cat <<EOF > "$HOME/.config/systemd/user/ai-dock-scheduler.service"
[Unit]
Description=Run due AI Dock automation recipes

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 ${SCRIPT_DIR}/automation_mcp_server.py --run-due
EOF

cat <<EOF > "$HOME/.config/systemd/user/ai-dock-scheduler.timer"
[Unit]
Description=Check AI Dock scheduled recipes every minute

[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
AccuracySec=10s
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Monitor Service & Timer
cat <<EOF > "$HOME/.config/systemd/user/ai-dock-monitor.service"
[Unit]
Description=Evaluate AI Dock background automation triggers

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 ${SCRIPT_DIR}/monitor_mcp_server.py --check
EOF

cat <<EOF > "$HOME/.config/systemd/user/ai-dock-monitor.timer"
[Unit]
Description=Check AI Dock automation triggers every 30 seconds

[Timer]
OnBootSec=1min
OnUnitActiveSec=30s
AccuracySec=5s
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Enable & start
echo "[*] Enabling systemd user services..."
systemctl --user daemon-reload
systemctl --user enable --now ai-dock-scheduler.timer
systemctl --user enable --now ai-dock-monitor.timer

# 6. Syntax compile check
echo "[*] Verifying compilation of Python source files..."
python3 -m py_compile "${SCRIPT_DIR}"/*.py

echo "==========================================="
echo "[OK] AI Dock installation completed inside WSL!"
echo "To test run the dock from WSL, run:"
echo "  python3 ${SCRIPT_DIR}/ai_dock.py"
echo "==========================================="
