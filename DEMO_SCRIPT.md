# Demo video plan — 2 minutes 40 seconds

## 0:00–0:15 — Problem and product

**Visual:** AI Dock floating above the desktop, expand from its orb.

**Narration:** “This is AI Dock, a natural-language desktop agent built for OpenAI Build Week. It turns informal, multi-step requests into locally validated actions instead of sending model text directly to a shell.”

## 0:15–0:50 — Complex request

**Visual:** Enter a prepared compound command:

> Clear only workspace seven, open example.com there, meanwhile create a folder named Judge Demo in Documents and put proof.txt inside saying the maze worked, then return me to workspace two.

Show the intent timeline, approval, workspace change, folder and file result.

**Narration:** “The request contains several obligations and workspace constraints. AI Dock converts each clause into a completion contract, selects relevant MCP capabilities, validates the plan, asks before sensitive actions, and checks the actual desktop and filesystem afterward.”

## 0:50–1:20 — Follow-up memory and browser reuse

**Visual:** Enter `open YouTube`, then `after checking something else, focus that again`. Show that no duplicate normal Brave window is created.

**Narration:** “Typed discourse state resolves references such as ‘that’ even after unrelated conversation. Website routes reuse the normal logged-in Brave profile and preserve workspace ownership instead of creating disposable profiles or stealing another workspace’s window.”

## 1:20–1:50 — Safety and recovery

**Visual:** Expand Task timeline, Undo History and Confirm risky controls; briefly show `/plan` and `/tools`.

**Narration:** “Cloud planning is treated as untrusted advice. Recursive schemas, authority checks and risk gates remain local. Every action is journaled before side effects, completed steps are fingerprinted, interrupted plans can resume, and deterministic checks reject false success.”

## 1:50–2:15 — Developer and research capabilities

**Visual:** Run `analyze examples/hello.c for warnings`, then show a concise result and capability count.

**Narration:** “Seventeen MCP families cover development, research, knowledge, packages, documents, media, data, monitoring and automation. Deferred discovery keeps prompts compact while still exposing more than 190 structured tools.”

## 2:15–2:40 — Codex and evidence

**Visual:** Terminal running `python power_suite_tests.py`, ending at `54/54`; then GitHub README.

**Narration:** “Codex was the primary engineering collaborator: implementing cross-file changes, diagnosing the real Hyprland environment, and turning failures into permanent tests. The sanitized public edition passes all 54 checks. AI Dock shows that a powerful agent can also be observable, recoverable and bounded.”

## Recording checklist

- Record at 1080p, 30 fps.
- Use a disposable workspace and test folder.
- Hide notifications and personal browser tabs.
- Do not show email addresses, cookies, vault notes, passwords or exported chats.
- Use original narration only; no copyrighted music or third-party logos beyond what is necessary to demonstrate interoperability.
- Keep the final export below 2:55 and upload it publicly to YouTube.
