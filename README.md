# AI Dock

AI Dock is a natural-language desktop agent for Linux that turns conversational, multi-step requests into locally validated MCP actions. It combines an always-on-top GTK interface, cloud-planner bridges, optional Ollama chat, persistent context, deterministic fast routes, and 17 families of system, desktop, research, development, and knowledge tools.

> OpenAI Build Week 2026 submission edition. The public repository contains no browser profile, cookies, chat exports, vault content, credentials, or machine-specific configuration.

## Why it exists

Desktop automation usually forces people to choose between brittle macros and agents with excessive, opaque authority. AI Dock separates understanding from execution: a capable planner proposes structured actions, while a local runtime validates schemas, explicit intent, permissions, risk, and observable outcomes before tools touch the computer.

## Highlights

- Natural commands, follow-up references, typo-tolerant entity resolution, and mandatory coverage of every clause in a multi-command request.
- 190+ discoverable MCP tools across desktop, files, packages, development, research, documents, media, data, monitoring, knowledge, and automation.
- Cloud planning with local execution; untrusted model output never becomes a shell command directly.
- Crash-safe action journals, resume support, idempotency checks, bounded recovery, undo records, and deterministic world-state verification.
- Hyprland workspace-aware window opening, focusing, moving, closing, and normal-profile Brave reuse.
- Optional Connected Brain Obsidian vault and local full-text knowledge index.
- Persistent conversational references without deleting long-term memory when the visible chat is cleared.
- A non-destructive 54-check regression suite.

## Architecture

```text
Natural-language request
        |
        v
Intent contract + persistent discourse state
        |
        v
Cloud planner / deterministic fast route
        |
        v
Schema, authority, risk and intent validation
        |
        v
MCP capability discovery -> local tool execution
        |
        v
Observed-effect verification -> recovery / completion report
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the trust boundaries and component map.

## Supported platform

The demonstrated build targets **CachyOS/Arch Linux, Hyprland, Wayland, Python 3.11+, GTK 4 and WebKitGTK 6**. Many non-desktop MCP servers are portable, but the desktop/window layer currently depends on Hyprland.

## Quick start

```bash
git clone https://github.com/Yogesh20256/ai-dock-build-week.git
cd ai-dock-build-week
./install.sh
./ai-dock
```

The installer creates a local `.venv`, installs Playwright, writes a portable MCP configuration to `~/.config/ai-dock/mcp_servers.json`, and installs a user desktop entry. It does not import browser data or overwrite an existing configuration without making a backup.

Useful optional packages include `ollama`, `brave`, `obsidian`, `ffmpeg`, `tesseract`, `wl-clipboard`, `imagemagick`, `pandoc`, `libreoffice`, `gh`, and `uv`.

## Test

```bash
python power_suite_tests.py
```

The suite checks syntax, MCP discovery, natural-language routes, cloud-plan validation, contaminated JSON recovery, multi-clause contracts, task recovery, secret redaction, world-state verification, software identity resolution, research, knowledge, media, monitoring, and system-awareness. Tests avoid destructive desktop operations.

## Safety and privacy

- Credentials are redacted from task journals.
- Mutating actions use structured allowlisted tools; arbitrary model-generated shell is not executed.
- Sensitive actions require confirmation and explicit high-risk operations use exact confirmation tokens.
- File tools are confined to the current home directory and optional `/mnt/shared`.
- Deletion routes use the desktop Trash.
- Screen access is opt-in and captured only when a visual action requires it.
- Website bridges use sessions the user establishes themselves. No credentials are bundled.

Read [SECURITY.md](SECURITY.md) before enabling system, package, browser, or screen-control capabilities.

## Build Week contribution

AI Dock existed as an early personal popup before the event. During the submission period it was meaningfully extended into a validated agent runtime with adaptive cloud planning, MCP capability discovery, multi-clause intent contracts, crash-safe execution, recovery, world-state checks, normal-profile browser reuse, portable packaging, and a repeatable power suite. See [BUILD_WEEK.md](BUILD_WEEK.md) for the dated scope and the Codex collaboration narrative.

## Judge testing

Judges can evaluate the project without connecting personal accounts:

1. Run `./install.sh` on a Hyprland/Wayland test account.
2. Run `python power_suite_tests.py` for the non-destructive backend demonstration.
3. Launch `./ai-dock`, open MCP, and try `/help`, `show system resources`, `open w2`, or a file operation inside a disposable test directory.
4. Keep **Confirm risky** enabled. Cloud website planners are optional; deterministic and local validation paths remain testable without logging into third-party sites.

## License

MIT. See [LICENSE](LICENSE).
