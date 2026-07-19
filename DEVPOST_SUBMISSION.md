# Devpost submission draft

## Project name

AI Dock — A Validated Natural-Language Desktop Agent

## Tagline

Turn everyday language into safe, verified desktop and developer workflows through a local MCP execution layer.

## Track

Developer Tools

## Inspiration

Most desktop automation sits at one of two extremes: rigid macros that break when wording changes, or autonomous agents that ask users to trust opaque model output with broad system access. AI Dock began with a simpler personal need—a small AI popup available above any application—but grew into an experiment in making natural-language computer control useful, observable and bounded.

## What it does

AI Dock is an always-on-top desktop agent for Hyprland Linux. A user can request several actions conversationally, refer back to earlier objects with words such as “it” or “that,” make typing mistakes, and specify workspaces without writing scripts.

The agent converts the request into an explicit intent contract, obtains a structured plan from a cloud planner or a deterministic fast route, validates every action against live MCP schemas and the original authority, requests confirmation for risky operations, executes only narrow local tools, and verifies observable outcomes. It supports desktop and workspace control, files, software identity and packages, development diagnostics, research, documents, media, data, monitoring, reusable automation, persistent memory and an optional Obsidian knowledge vault.

## How we built it

The interface is written in Python with GTK 4 and WebKitGTK. Local capabilities are exposed through 17 short-lived JSON-RPC MCP stdio servers. The planning layer supports adaptive cloud-provider selection and a multi-model council, but privileged execution remains local. A universal capability index retrieves only relevant schemas. The runtime includes recursive schema validation, authority checks, multi-clause coverage, risk gates, atomic task journals, action fingerprints, idempotent preflight, bounded recovery and deterministic world-state checks.

Codex was the primary engineering collaborator. It helped inspect the real CachyOS/Hyprland environment, implement capabilities across the MCP servers, translate repeated real-world failures into regression tests, diagnose browser/workspace behavior, harden trust boundaries, and create the portable public submission. The human directed the product, tested natural-language behavior, reported failures, made product and safety choices, and established the acceptance criteria.

## Challenges

- Preserving the user’s actual intent across twisted multi-command sentences instead of stopping after the first recognizable phrase.
- Reusing the normal logged-in browser and correct workspace without stealing a window from another workspace or creating duplicate profiles.
- Treating cloud-planner responses and webpage content as untrusted while still allowing useful automation.
- Verifying that reported success corresponds to real files, windows, workspaces and processes.
- Recovering safely after interruptions without replaying completed mutations.

## Accomplishments

- 180+ tools across 17 MCP capability families.
- Explicit completion contracts for compound instructions.
- Crash-safe resumable execution with bounded self-recovery.
- Adaptive planner and tool reliability with circuit breakers.
- Persistent typed conversational references and correction learning.
- A portable sanitized installer and 54-check non-destructive regression suite.

## What we learned

The strongest agent architecture is not simply the strongest model. Reliability improves when probabilistic interpretation is separated from authority, model output is constrained by schemas, every requested clause becomes testable, state is represented explicitly, and success is checked against the environment.

## What is next

Broader Wayland compositor support, accessibility-tree-first UI control, signed capability packages, richer policy profiles, reproducible containerized judge demos, and an OpenAI-native planner adapter that avoids website-specific bridges.

## Built with

Python, GTK 4, WebKitGTK, Model Context Protocol, Codex, GPT-5.6, Hyprland, Wayland, Playwright, Ollama, SQLite FTS5, FFmpeg and GitHub CLI.

## Repository

https://github.com/Yogesh20256/ai-dock-build-week

## Codex session ID

`019f65a1-2eda-73a1-96f7-facb6a4bced6`

## Testing instructions

Use a disposable CachyOS/Arch Hyprland account. Clone the repository, run `./install.sh`, then run `python power_suite_tests.py`. Launch `./ai-dock`; keep **Confirm risky** enabled. Try `/help`, `show system resources`, `open w2`, and a file operation inside a disposable folder. Third-party website accounts are not required for the regression suite.
