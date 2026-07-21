# AI Dock — native web popup

AI Dock embeds the real ChatGPT, Gemini, DeepSeek, HackerAI, and Claude websites inside a frameless native popup. It also includes a private local chat powered by Ollama, with model selection and per-question thinking control.

- `Super+C`: open, hide, or restore AI Dock
- Hidden state: the popup disappears and is replaced by a draggable floating **AI** orb
- Click the orb: restore the browser
- The popup stays floating and pinned above applications
- `×`: completely close the application; `Super+C` launches it again

## Windows Support

AI Dock is primarily designed for Linux, but it is fully compatible with **Windows 10/11** using **WSLg (Windows Subsystem for Linux GUI)** and AutoHotkey. 

For full installation and shortcut configuration instructions, see the [Windows Installation Guide (INSTALL_WINDOWS.md)](INSTALL_WINDOWS.md).

## Multi-AI workflows

Open the **Flow** tab, choose the participating AIs, enter one question, and select a mode:

- **Parallel** sends the question to every selected AI at the same time.
- **Review chain** sends the first answer to the next selected AI for correction and improvement. Use the **Review order** selector and arrow buttons to choose exactly which AI goes first, second, and so on. The order is remembered after reboot.

The workflow reuses the existing embedded website sessions, so it does not create new logins or replace stored cookies. Website automation depends on each provider's page structure and may require adapter updates after a site redesign.

Workflow runs now maintain `~/.local/share/ai-dock/workflows/current-checkpoint.json`. The Flow page can resume that checkpoint, retry only failed providers, and save/load reusable order, selection, and mode templates. Provider selectors live in `provider_adapters.json`, allowing a website adapter to be repaired independently from the workflow engine.

Workflow answers stream live into the results panel. After a run, **Save + Synthesize** writes the question and every collected answer to `~/.local/share/ai-dock/workflows/`, then sends that report to the selected AI for one consolidated final answer. Qwen workflow prompts and responses are also mirrored into the normal Qwen tab.

There are no API keys and no terminal command is needed after installation.

## MCP tools and one-command agent

MCP intent interpretation is cloud-only. Exact trusted shortcuts execute
deterministically without loading a model; every ambiguous or conversational
request is planned by Gemini, ChatGPT, HackerAI, DeepSeek, Claude, Grok, or the
multi-model council. Qwen remains available as a chat tab but is never used as
an MCP planner. Stop synchronously terminates active bridge/MCP processes and
invalidates late callbacks, so cancelled work cannot resume by itself.

The **MCP** tab uses cloud planners for all semantic interpretation and ambiguous planning, while trusted deterministic shortcuts execute simple exact commands immediately. Qwen remains an optional local chat model and is not allowed to secretly plan MCP, project-building, or video-building actions. The server config is `~/.config/ai-dock/mcp_servers.json`.

AI Dock includes an enabled **desktop** server for opening GitHub, websites, files, and folders, plus an enabled **web** server for fetching web pages. Other services such as GitHub repository management, Gmail, databases, or calendars require their own MCP server and credentials before they can be enabled.

The enabled **browser** MCP uses Playwright and a persistent AI-controlled Brave profile at `~/.local/share/ai-dock/controlled-browser`. It reuses one tab, reads real page controls, supports WhatsApp Web, performs structured searches, and can click the first YouTube channel/video result. Sign into websites once inside that controlled Brave window; those sessions remain separate from your personal Brave profile.

The enabled **brain** MCP connects AI Dock to the Obsidian vault at `/home/yogesh/Documents/Connected Brain`. It can list, search, read, append, and replace Markdown notes. MCP command history is mirrored under `Memory/`, and full Parallel/Review Chain reports are mirrored under `Workflows/`.

The header **Brain** switch is enabled by default. It selects up to six locally relevant notes (with a 12,000-character limit) and supplies them to local Qwen chat, Parallel, Review Chain, final synthesis, and local or web MCP planners. Turn it off for a request that should not use saved context.

AI Dock archives clean prompts and completed responses as append-only daily Markdown notes under `Chats/YYYY-MM/YYYY-MM-DD.md`. This includes local chat, Parallel, Review Chain, synthesis, Claude/Grok bridge calls, and MCP conversations. Injected Brain context and temporary typing/status messages are not duplicated into the archive.

AI Dock also observes the currently loaded conversation in each supported provider tab every 20 seconds. Direct ChatGPT, Gemini, DeepSeek, HackerAI, Claude, and Grok turns are deduplicated across restarts and archived into the same dated Chat notes. A compact inventory is maintained at `Chats/Cross-AI Index.md`; these notes participate in Brain retrieval and MCP planning like other vault notes. Provider history that has never been opened or loaded remains on the provider's servers and cannot be copied until it becomes visible to AI Dock or is imported from an official data export.

The enabled **packages** MCP is system-aware: it detects CachyOS/Arch, architecture, Hyprland/Wayland, available package managers and installed desktop entries before resolving software. Human product names are matched against product identity, vendor/category hints, official repository metadata and the official AUR RPC. Ambiguous results install nothing. Confirmed installs use `pacman` or `paru`, then verify package ownership, version, executables and desktop entries. For example, `install Antigravity` resolves to `antigravity-ide`, not the unrelated `antigravity` package.

The enabled **system** MCP provides structured tools for system inspection, files, reversible Trash deletion, copy/move, ZIP/TAR extraction, processes, systemd services, Git repositories, installed-application discovery, and read-only diagnostics. Paths are confined to the home folder and `/mnt/shared`; privileged service operations use normal system authentication.

The **Cloud** page launches Claude and Grok in separate real Brave app windows because those services reject embedded WebKit login. Each gets a persistent profile under `~/.local/share/ai-dock/cloud-browser/`. Once logged in, the bridge can use them in Parallel, Review Chain, final synthesis, and as MCP planning AIs.

The MCP panel keeps up to 500 successful commands in `~/.local/share/ai-dock/mcp_memory.json` and retrieves older entries relevant to the current request. **Clear** resets only the visible chat; saved sessions, MCP memory and Connected Brain notes remain available. The History drawer restores grouped past sessions. **Stop** interrupts an active model/tool loop. **See screen** keeps the dock opaque, briefly hides it only during capture, and restores it afterward. The smart router does not invoke vision for ordinary questions or known fast opening/search commands. Commands that explicitly refer to visible controls use local `qwen3-vl:2b` observations plus the tool controller. Visual mode can click screen coordinates, enter text, and press a restricted set of safe keys.

The MCP page also includes a timestamped task timeline, confirmation for sensitive fast/local/cloud-planned actions, an expandable undo history, and an **Undo last** button for recorded reversible operations such as newly created files/folders and moves. Undo records are stored in `~/.local/share/ai-dock/undo_history.json`.

## Power suite

AI Dock currently exposes 192 structured backend tools across 17 MCP families. They are selected and chained from normal text; the Control buttons are optional diagnostics, not the primary interface. In addition to the original desktop, browser, system, packages, documents, Brain and web servers:

The clean-room universal runtime in `agent_runtime.py` adds deferred capability discovery: the model begins with a compact relevant subset and can call `runtime__search_tools` to retrieve exact live schemas from the complete catalog during execution. Multi-step tasks can record a dependency-checked plan with per-step verification. Every MCP run is atomically journaled under `~/.local/share/ai-dock/agent-tasks/`, with common credentials redacted, tool outcomes recorded, completion checked against actual MCP results, and interrupted commands offered through `/resume` after restart.

The **missions** MCP is the high-level artifact engine. It can visibly open and investigate a website while preserving source, headers, checked links, a rendered screenshot and a Markdown bug report; validate and write a cloud-authored multi-file application manifest, initialize Git and verify syntax; publish a verified repository using the official GitHub CLI only after `PUBLISH` confirmation; and render cloud-authored narration and scene captions into a narrated MP4 with speech, FFmpeg scenes, provenance and FFprobe verification. Video missions accept an explicit output folder and filename, create the allowed destination under Documents or `/mnt/shared`, and deliver the verified MP4 directly instead of requiring a guessed intermediate path. The local mission executor performs validation and artifact work, never hidden model reasoning. Mission stages and artifact counts stream into the MCP timeline and Control Center Agent page. Artifacts live under `~/Documents/AI Missions` and projects under `~/Documents/AI Projects`.

The **AI Council** planner consults ChatGPT, Gemini and HackerAI concurrently for complex, ambiguous, multi-clause, application, website-audit, video and publication missions. It no longer accepts the first response: an arbiter compares all usable candidates and synthesizes one consensus plan, with a structurally ranked fallback if the arbiter bridge is unavailable. Cloud output is schema- and intent-validated against the original request and live tool catalog; only local MCP tools can touch the system. For high-impact, risky or three-plus-action plans, a different cloud AI independently criticizes the plan before execution. Qwen is not an MCP planner.

Multi-step execution has bounded self-recovery. If a tool fails after earlier steps succeeded, the agent preserves those actual results, asks its cloud planner for only corrective and remaining actions, validates the recovery plan through the normal safety pipeline, and retries once. Canonical action fingerprints remove any already-completed mutation even if a recovery model tries to repeat it. Final outcome verification still checks the whole original request.

Every validated cloud action is also written atomically to a crash-safe execution ledger before side effects begin. Completed action fingerprints and bounded results are checkpointed after each step. After an application or system interruption, `/resume` executes only unfinished actions and asks for renewed approval if any remaining action is sensitive; `/plan` shows completed and pending steps. Plans are explicitly limited to 12 actions and are never silently truncated.

The executor maintains compact local world-state checkpoints around tool calls. It deterministically verifies workspace activation, window movement and closure, file creation/writing/trashing, and folder creation directly against Hyprland and the filesystem. A tool that reports success without the required observable effect enters recovery. Ambiguous effects such as webpage meaning remain cloud-verified instead of causing false local failures.

Before calling a mutating tool, deterministic idempotency checks recognize goals that are already satisfied: an active workspace, already-closed window, identical file content, existing folder, completed move or already-absent trash target. These actions are checkpointed without repeating their side effects.

Auto routing learns from real local outcomes. Provider success, bridge failures, invalid plans, response latency, recent streaks and task-domain specialties are stored locally in `~/.local/share/ai-dock/provider_intelligence.json` using smoothed scores so a single failure does not overreact. Type `/providers` in MCP to inspect the evidence Auto currently uses.

Repeated bridge failures activate a time-bounded circuit breaker. Auto, Council and independent critics temporarily prefer healthy logged-in providers, then automatically reconsider a cooled-down provider later. Capability discovery uses semantic aliases and fuzzy typo matching at both MCP-family and individual-tool levels.

The same adaptive reliability layer operates below the planners. Cloud-executed MCP tools accumulate local success, failure, latency, failure-streak and deterministic world-mismatch evidence in `~/.local/share/ai-dock/tool_intelligence.json`. Three consecutive failures temporarily cool down that backend so capability selection can prefer a healthy alternative; a later success clears the breaker. `/tools` reports active tool cooldowns.

The **research** MCP searches the web, extracts and compares readable pages, creates multi-source evidence bundles, performs bounded same-domain site crawls, checks Internet Archive history, queries Wikipedia, Crossref and public GitHub repositories, reads RSS/Atom and public JSON APIs, checks source freshness, and performs provenance-verified downloads. Research results are sent back to the cloud planner for a final source-linked synthesis.

The **knowledge** MCP incrementally indexes local text, code, Markdown, CSV, JSON, HTML, PDF and DOCX content in a private SQLite FTS5 database. Indexed roots retain provenance, modification time and hashes. Each root independently controls whether excerpts may be supplied to cloud planners; local-only content never enters cloud context.

Verified compound executions become learned procedure examples with redacted arguments, verification evidence and success counts. Similar future requests receive these procedures as adaptable examples. Learned procedures can be inspected, forgotten, or promoted into named recipes; recipes can be simulated with substituted variables and risk visibility before execution.

Fast routes are confidence-gated across every domain, not only software. A simple complete command such as `open w2` remains instant. Requests containing conversational references (`it`, `there`, `same`, `previous`), conditions, contrasts, sequences, multiple clauses, unclear targets, or long prose bypass regex shortcuts and go through a cloud planner. This prevents one matched phrase from silently discarding the rest of a request.

Explicit multi-clause requests become a local intent contract (`intent_1`, `intent_2`, and so on). Each clause must be covered by a validated action or explicitly answered without a tool; an incomplete cloud plan is rejected before any local side effect. Duplicate sensitive mutations are also rejected before execution.

Repeatedly verified exact workflows become local executable skills after two successful outcome verifications. Reuse skips unnecessary replanning but still revalidates current schemas and intent, requests sensitive approval, writes crash-safe checkpoints, checks observable effects, and verifies the final request.

Verified examples, corrections and procedures use semantic aliases plus typo-tolerant similarity rather than literal word overlap alone. Cloud arguments are recursively checked against their complete JSON schemas, including nested objects, array items, required fields, closed properties, enums and size bounds. Web evidence, indexed text, window titles, tool results and errors are explicitly treated as untrusted data rather than instructions; local intent and authority checks remain decisive.

The intent learner supplies each cloud planner with compact persistent action state, relevant verified examples, and relevant corrections. Natural feedback such as “no,” “that was wrong,” “I meant,” or “do this instead” invalidates the previous positive example, records the rejected behavior in `Connected Brain/Memory/Corrections.md`, and teaches future plans what not to repeat.

Before planning, the agent also supplies a read-only snapshot of the active workspace and open windows. A compact directory describes all MCP capability families. If casual wording requires a tool that was not initially exposed, the cloud planner can request a capability expansion and receive matching live schemas before returning its final plan. Every returned action is schema-checked for required fields, valid argument names, types, and enums before execution.

A separate intent guard compares valid actions back to the original wording. It preserves explicit workspace numbers and rejects invented move, close, delete, installation, or publication authority.

Persistent conversational state lives at `~/.local/share/ai-dock/conversation_state.json`. It remembers typed action references such as the last opened/closed application or website, last file/folder created or moved, last workspace, last entity and last successful action. These references survive unrelated questions, hiding/closing AI Dock and rebooting. `/context` shows the current reference slots. Clear chat only clears the visible conversation and does not erase this state or the Connected Brain. Controlled browser tabs can be closed individually, so `close that thing` after opening a website does not have to close the entire browser.

- **Automation** saves and executes named multi-step recipes, schedules one-time or repeating jobs, records activity, searches capabilities, performs full health checks, creates verified lightweight backups, restores explicitly confirmed snapshots, and exports credential-free diagnostic bundles. The persistent user timer is `ai-dock-scheduler.timer`.
- **Developer** maps projects, searches code and symbols, analyzes C with compiler warnings, detects build systems, runs recognized project checks, summarizes Git repositories, and invokes installed dependency auditors.
- **Workspace** summarizes Hyprland workspaces, saves/restores named layouts, reopens missing known applications, and creates focus sessions without moving AI Dock itself.
- **Media** performs fast local screen/window OCR with Tesseract, reads and controls MPRIS media, reports network/Bluetooth state, records the desktop, and displays notifications.
- **Brain** additionally builds bounded context packets, finds unfinished tasks, appends structured daily notes, and reports vault graph health.
- **Data** inspects, validates, filters, sorts, deduplicates, converts and summarizes CSV/JSON/JSONL data, and performs read-only SQLite discovery and queries.
- **Operations** performs fast file/content search, recent/largest-file discovery, exact duplicate detection, storage maps, metadata and checksums, clipboard control, previewed batch rename/organization, PDF extraction, image/media conversion and reviewed folder sync.
- **Monitor** reads resources, processes, services, ports, network and disk health, checks websites, and persists background `when X then Y` rules. Rules can notify the desktop or run an existing recipe; `ai-dock-monitor.timer` evaluates them every 30 seconds after login/reboot.

Useful MCP commands include `run a health check`, `list recipes`, `run recipe Morning Setup`, `list scheduled jobs`, `show all workspaces`, `save layout as Coding`, `read screen text`, `show network status`, `map this project`, and `analyze Loops/armstrong.c for warnings`.

Slash shortcuts: `/health`, `/recipes`, `/schedules`, `/activity`, `/tasks`, `/resume`, `/history`, `/new`, `/tools`, `/memo`, `/clear`, and `/help`.

Run the non-destructive repeatable regression suite with `python power_suite_tests.py`. Its 51 checks validate syntax, adaptive provider and tool intelligence with circuit breaking, semantic typo and memory retrieval, recursive cloud schemas, idempotent preflight, intent-contract completeness, crash-safe remaining-step recovery, bounded full-plan execution, executable learned skills, explicit video delivery, local world-state assertions, recovery idempotency, cloud-only mission authorship, independent plan criticism, all MCP discovery, full health, Brain context/graph, developer diagnostics, workspaces, media/network, data, file search/storage, monitoring and recording safety.

## Control Center

The **Control** tab provides six operational dashboards:

- **Health** checks embedded message composers, Ollama, and Claude/Grok bridge availability without sending a prompt.
- **Browser** lists the AI-controlled Brave tabs, refreshes their state, merges controlled windows, and opens the normal Brave profile.
- **Brain** searches the Connected Brain, pins durable or temporary memories, edits/corrects Markdown notes, safely moves selected notes to Trash, explains which notes may influence a query, and exports MCP memory snapshots.
- **Power** exposes one-click health, capability, recipe, schedule, activity, backup, diagnostic, Brain, workspace, media, network and Bluetooth status.
- **Agent** shows the universal runtime, recent durable tasks, recoverable interrupted work, and the local journal folder.
- **Tests** runs a safe built-in regression suite covering models, cookies, the vault, MCP discovery, browser connectivity, and saved memory. Results persist in `~/.local/share/ai-dock/regression-results.json`.

Friendly file/folder resolution searches common home folders and `/mnt/shared`, tolerating spaces, underscores, plural forms, and small typing mistakes. Commands such as `open c prgramming folder` and `create folder Loops Practice in c prgramming` do not require absolute paths. In the controlled browser, `show numbers` overlays numbered badges on visible clickable controls and `click 12` selects the labelled control.

Use **Planner AI** to choose Auto cloud intelligence, the multi-AI Council, ChatGPT Web, Gemini Web, DeepSeek Web, HackerAI Web, Claude Bridge, or Grok Bridge. The chosen cloud AI returns structured actions; AI Dock validates them locally before MCP execution.

The **Qwen** tab has a model dropdown populated from the currently installed Ollama models. Switching models starts a fresh local conversation, and Flow uses the selected model for subsequent Qwen workflow steps.

Example (requires `uvx` and downloads the server the first time):

```json
{
  "servers": {
    "web": {
      "command": "uvx",
      "args": ["mcp-server-fetch"],
      "enabled": true
    }
  }
}
```

Restart AI Dock or press **Refresh tools** after editing the file. Enter one natural-language command and the cloud planner can choose and combine connected MCP tools. **Allow automatic tool actions** is on by default; turn it off to preview calls. The separate **Confirm risky** control remains on by default and pauses sensitive local or cloud-planned work for review. Only add MCP servers and folders you trust, because their tools can read or modify the resources you expose.

## Adding another AI

Add another object to `sites.json`. Copy that file to `~/.config/ai-dock/sites.json` first if you want upgrades to leave your plugins untouched.

## Resetting website logins

Close AI Dock and remove `~/.config/AI Dock`. This signs the popup out of every website and does not affect any browser profile.
