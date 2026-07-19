# Architecture and trust model

AI Dock deliberately separates probabilistic interpretation from privileged execution.

1. **Interface** — GTK/WebKit always-on-top dock, local Qwen chat, workflow views, MCP console and Control Center.
2. **Context layer** — bounded recent conversation, typed discourse slots, verified examples, corrections and optional Obsidian knowledge.
3. **Planning layer** — deterministic fast routes for complete low-ambiguity commands; cloud planners or a multi-provider council for semantic and compound requests.
4. **Validation layer** — recursive JSON Schema checks, explicit intent coverage, workspace preservation, risk classification, prompt-injection boundaries and action-count limits.
5. **Execution layer** — short-lived MCP stdio servers expose narrow structured capabilities. Model text is never evaluated as shell code.
6. **Reliability layer** — atomic journals, action fingerprints, preflight idempotency, observed-effect checks, provider/tool circuit breakers, one bounded recovery pass and final completion reports.

## Data flow

Cloud planners receive the request, compact state and only relevant tool schemas. Tool execution and authority decisions remain local. Local-only indexed knowledge is excluded from cloud context unless a root is explicitly marked shareable. Persistent runtime data is stored under `~/.local/share/ai-dock`; configuration is under `~/.config/ai-dock`.

## MCP families

Desktop, browser, system, packages, documents, automation, developer, workspace, media, data, operations, monitoring, missions, research, knowledge, Brain and optional web fetching.

## Known boundaries

The demonstrated desktop controller is Hyprland-specific. Website DOMs and authentication policies change, so browser bridges are adapters rather than guaranteed APIs. Screen-coordinate actions are a fallback and are less reliable than structured tools. System mutations can have real consequences and remain confirmation-gated.
