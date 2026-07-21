# Installing AI Dock on Windows (via WSLg)

AI Dock is a powerful, system-aware AI orchestration framework built on Linux-native GUI technologies (`PyGObject`, `GTK 4`, and `WebKitGTK 6.0`) and relies on `systemd` user timers for its background schedules. 

To run the complete AI Dock application on Windows with all its features intact, we use **WSLg (Windows Subsystem for Linux GUI)**. This runs the interface natively on your Windows desktop with hardware acceleration.

---

## Prerequisites

1. **Windows 11** (or Windows 10 Build 19044+)
2. **AutoHotkey** (Optional, to bind the `Super+C` hotkey on Windows): [Download AutoHotkey](https://www.autohotkey.com/)

---

## Step 1: Install & Update WSL2

If you do not have WSL installed yet, open a Windows PowerShell (as Administrator) and run:

```powershell
wsl --install
```

If WSL is already installed, ensure it is up-to-date and GUI support (WSLg) is enabled by running:

```powershell
wsl --update
```

Restart your computer if prompted.

---

## Step 2: Enable systemd in WSL

AI Dock uses systemd user timers to run scheduled automation recipes and background checks. Systemd must be enabled inside your WSL Linux distribution.

1. Open your WSL terminal (e.g., Ubuntu).
2. Edit or create the WSL configuration file:
   ```bash
   sudo nano /etc/wsl.conf
   ```
3. Add the following lines to the file:
   ```ini
   [boot]
   systemd=true
   ```
4. Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).
5. Open Windows PowerShell and shutdown WSL to apply changes:
   ```powershell
   wsl --shutdown
   ```
6. Re-open your WSL terminal.

---

## Step 3: Clone & Install AI Dock

1. Navigate to your preferred directory inside WSL and clone the repository, or copy your files over. For example, to keep it in your WSL home directory:
   ```bash
    cd ~
    git clone <your-ai-dock-repo-url> ai-dock
    cd ai-dock
   ```

2. Run the automated installation script:
   ```bash
   ./install_wsl.sh
   ```
   *This script installs Python dependencies, GTK4, WebKitGTK 6.0, Playwright, and registers the background systemd timers.*

---

## Step 4: Link Your Obsidian Vault

If you use Obsidian on Windows and want AI Dock to access the same notes:
1. WSL automatically mounts your Windows drives under `/mnt/`. For example, your Windows user folder is at `/mnt/c/Users/<WindowsUsername>/`.
2. Link your Windows Obsidian Vault into the expected Linux path by running:
   ```bash
   mkdir -p ~/Documents
   ln -s "/mnt/c/Users/<WindowsUsername>/Documents/Obsidian Vault" "$HOME/Documents/Obsidian Vault"
   ```
   *(Be sure to replace `<WindowsUsername>` with your actual Windows account username).*

---

## Step 5: Install Brave Browser in WSL

For Claude/Grok bridge automation and the browser MCP server, AI Dock expects Brave browser to be installed inside WSL:

Run the following commands inside WSL to install the official Brave browser package:
```bash
sudo curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg https://brave-browser-release.gpg.s3.brave.com/brave-browser-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-release.gpg.s3.brave.com/ stable main" | sudo tee /etc/apt/sources.list.d/brave-browser-release.list
sudo apt update
sudo apt install -y brave-browser
```

---

## Step 6: Configure Ollama

If you run Ollama on Windows, WSL can access it automatically!
WSL shares the network loopback with Windows, meaning that local Ollama running on Windows port `11434` will be fully reachable by AI Dock inside WSL at `http://127.0.0.1:11434`. No additional setup is required.

---

## Step 7: Configure Win+C (Super+C) Global Hotkey

On Linux, `Super+C` is bound via your window manager to toggle the dock. On Windows, you can achieve the exact same behavior using AutoHotkey:

1. Copy the [toggle_ai_dock.ahk](toggle_ai_dock.ahk) file from this repository to your Windows host machine.
2. Ensure you have [AutoHotkey](https://www.autohotkey.com/) installed.
3. Right-click `toggle_ai_dock.ahk` and click **Run Script**.
4. Press `Win + C` on your keyboard. The AI Dock window will slide open or hide on your Windows desktop seamlessly!
5. To run this shortcut automatically on Windows startup, press `Win + R`, type `shell:startup`, hit enter, and place a shortcut to `toggle_ai_dock.ahk` inside that folder.

---

## Troubleshooting

- **GUI Apps Don't Launch**: Ensure you have WSLg running by running `wsl --status` in PowerShell and verifying that your WSL version is WSL 2.
- **Systemd Error**: If `systemctl` fails inside WSL, verify that `systemd=true` is present in `/etc/wsl.conf` and you have fully shutdown WSL using `wsl --shutdown` before restarting it.
