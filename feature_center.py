"""Operational dashboards for AI Dock.

Keeps diagnostics and management UI separate from the provider automation core.
"""
import json
import subprocess
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk


def safe_regression(data, brain, mcp_config, ollama_models, browser_targets):
    checks = []
    def check(name, fn):
        try: checks.append((name, True, str(fn())))
        except Exception as error: checks.append((name, False, str(error)))
    check("Ollama models", lambda: ", ".join(ollama_models()) or (_ for _ in ()).throw(RuntimeError("none")))
    check("Connected Brain", lambda: f"{sum(1 for _ in brain.rglob('*.md'))} notes")
    check("Cookie database", lambda: f"{(data / 'cookies.sqlite').stat().st_size} bytes")
    check("Saved MCP memory", lambda: f"{len(json.loads((data / 'mcp_memory.json').read_text()))} entries")
    def mcp():
        from mcp_client import McpConnections
        with McpConnections(mcp_config) as connections: return f"{len(connections.discover())} tools"
    check("MCP discovery", mcp)
    check("Controlled browser", lambda: f"{len(browser_targets())} targets")
    return checks


class FeatureCenter(Gtk.Box):
    PROVIDERS = ("chatgpt", "gemini", "deepseek", "hackerai", "qwen", "claude", "grok")

    def __init__(self, dock, data, config, brain, mcp_config, ollama_models, cloud_python, cloud_bridge):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.dock, self.data, self.config, self.brain = dock, data, config, brain
        self.mcp_config, self.ollama_models = mcp_config, ollama_models
        self.cloud_python, self.cloud_bridge = cloud_python, cloud_bridge
        title = Gtk.Box(spacing=8, css_classes=["feature-head"])
        title.append(Gtk.Label(label="Control Center", xalign=0, hexpand=True, css_classes=["result-title"]))
        refresh = Gtk.Button(label="Refresh all"); refresh.connect("clicked", self.refresh_all); title.append(refresh)
        self.append(title)
        self.tabs = Gtk.Notebook(vexpand=True); self.append(self.tabs)
        self._health_page(); self._browser_page(); self._brain_page(); self._automation_page(); self._agent_page(); self._regression_page()
        GLib.idle_add(lambda: self.refresh_all() or False)

    def page(self, name):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=10,
                      margin_bottom=10, margin_start=10, margin_end=10)
        scroll = Gtk.ScrolledWindow(vexpand=True); scroll.set_child(box)
        self.tabs.append_page(scroll, Gtk.Label(label=name)); return box

    def _health_page(self):
        page = self.page("Health")
        page.append(Gtk.Label(label="Provider readiness", xalign=0, css_classes=["section-title"]))
        self.health_rows = {}
        for provider in self.PROVIDERS:
            row = Gtk.Box(spacing=8, css_classes=["health-row"])
            row.append(Gtk.Label(label=provider.title(), xalign=0, width_chars=12))
            status = Gtk.Label(label="Not checked", xalign=0, hexpand=True, selectable=True)
            row.append(status); self.health_rows[provider] = status; page.append(row)
        buttons = Gtk.Box(spacing=8)
        test = Gtk.Button(label="Test all providers", css_classes=["send"]); test.connect("clicked", self.test_health)
        buttons.append(test)
        open_flow = Gtk.Button(label="Open Flow"); open_flow.connect("clicked", lambda *_: self.dock.select(self.dock.buttons["flow"], "flow"))
        buttons.append(open_flow); page.append(buttons)
        self.health_summary = Gtk.Label(xalign=0, wrap=True, selectable=True, css_classes=["tiny"]); page.append(self.health_summary)

    def _browser_page(self):
        page = self.page("Browser")
        page.append(Gtk.Label(label="Controlled browser sessions", xalign=0, css_classes=["section-title"]))
        buttons = Gtk.Box(spacing=8)
        refresh = Gtk.Button(label="Refresh tabs"); refresh.connect("clicked", self.refresh_browser); buttons.append(refresh)
        merge = Gtk.Button(label="Merge windows"); merge.connect("clicked", self.merge_browser); buttons.append(merge)
        normal = Gtk.Button(label="Open normal Brave"); normal.connect("clicked", lambda *_: subprocess.Popen(["brave"]))
        buttons.append(normal); page.append(buttons)
        self.browser_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6); page.append(self.browser_list)
        self.browser_status = Gtk.Label(xalign=0, wrap=True, selectable=True, css_classes=["tiny"]); page.append(self.browser_status)

    def _brain_page(self):
        page = self.page("Brain")
        controls = Gtk.Box(spacing=6)
        self.brain_query = Gtk.Entry(placeholder_text="Search Connected Brain…", hexpand=True); controls.append(self.brain_query)
        search = Gtk.Button(label="Search"); search.connect("clicked", self.search_brain); controls.append(search)
        page.append(controls)
        pinrow = Gtk.Box(spacing=6)
        self.pin_text = Gtk.Entry(placeholder_text="Important fact to pin", hexpand=True); pinrow.append(self.pin_text)
        pin = Gtk.Button(label="Pin memory"); pin.connect("clicked", self.pin_memory); pinrow.append(pin); page.append(pinrow)
        temporary = Gtk.Button(label="Mark temporary"); temporary.connect("clicked", self.temporary_memory); pinrow.append(temporary)
        self.brain_results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6); page.append(self.brain_results)
        self.brain_status = Gtk.Label(xalign=0, wrap=True, selectable=True, css_classes=["tiny"]); page.append(self.brain_status)
        editor_head = Gtk.Box(spacing=6)
        self.note_path = Gtk.Entry(placeholder_text="Relative note path, e.g. Memory/Pinned Memories.md", hexpand=True); editor_head.append(self.note_path)
        load = Gtk.Button(label="Load note"); load.connect("clicked", self.load_note); editor_head.append(load); page.append(editor_head)
        self.note_editor = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR); self.note_editor.set_size_request(-1, 150); self.note_editor.add_css_class("prompt")
        page.append(self.note_editor)
        editor_actions = Gtk.Box(spacing=6)
        save = Gtk.Button(label="Save correction"); save.connect("clicked", self.save_note); editor_actions.append(save)
        trash = Gtk.Button(label="Move note to Trash", css_classes=["danger"]); trash.connect("clicked", self.trash_note); editor_actions.append(trash)
        explain = Gtk.Button(label="Show influencing notes"); explain.connect("clicked", self.explain_context); editor_actions.append(explain); page.append(editor_actions)
        page.append(Gtk.Separator())
        page.append(Gtk.Label(label="MCP memory controls", xalign=0, css_classes=["section-title"]))
        memory_actions = Gtk.Box(spacing=6)
        inspect = Gtk.Button(label="Inspect recent"); inspect.connect("clicked", self.inspect_memory); memory_actions.append(inspect)
        export = Gtk.Button(label="Export snapshot"); export.connect("clicked", self.export_memory); memory_actions.append(export)
        page.append(memory_actions)

    def _regression_page(self):
        page = self.page("Tests")
        page.append(Gtk.Label(label="Safe regression suite", xalign=0, css_classes=["section-title"]))
        page.append(Gtk.Label(label="Checks models, sessions, vault, MCP discovery, browser control and saved state. It does not install packages or delete personal files.", wrap=True, xalign=0, css_classes=["tiny"]))
        run = Gtk.Button(label="Run regression suite", css_classes=["send"]); run.connect("clicked", self.run_regression); page.append(run)
        self.test_output = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True); page.append(self.test_output)
        self.test_history = Gtk.Label(xalign=0, wrap=True, selectable=True, css_classes=["tiny"]); page.append(self.test_history)

    def _automation_page(self):
        page = self.page("Power")
        page.append(Gtk.Label(label="Automation and system intelligence", xalign=0, css_classes=["section-title"]))
        page.append(Gtk.Label(label="Run safe diagnostics and inspect recipes, schedules, workspace layouts, Brain health, devices, and developer capabilities.", xalign=0, wrap=True, css_classes=["tiny"]))
        buttons = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3)
        actions = (
            ("Full health", "automation__automation_health_check", {}),
            ("Capabilities", "automation__automation_capabilities", {}),
            ("Recipes", "automation__recipe_list", {}),
            ("Schedules", "automation__schedule_list", {}),
            ("Activity", "automation__activity_recent", {"limit": 30}),
            ("Create backup", "automation__backup_create", {"label": "control-center"}),
            ("List backups", "automation__backup_list", {}),
            ("Diagnostic bundle", "automation__diagnostic_bundle", {}),
            ("Brain stats", "brain__brain_stats", {}),
            ("Workspaces", "workspace__workspace_summary", {}),
            ("Media status", "media__media_status", {}),
            ("Network", "media__network_status", {}),
            ("Bluetooth", "media__bluetooth_status", {}),
        )
        for label, tool, arguments in actions:
            button = Gtk.Button(label=label); button.connect("clicked", self.run_power_tool, tool, arguments); buttons.insert(button, -1)
        page.append(buttons)
        self.power_status = Gtk.Label(label="Choose a diagnostic.", xalign=0, yalign=0, wrap=True, selectable=True)
        power_scroll = Gtk.ScrolledWindow(vexpand=True); power_scroll.set_child(self.power_status); page.append(power_scroll)

    def _agent_page(self):
        page = self.page("Agent")
        page.append(Gtk.Label(label="Universal task runtime", xalign=0, css_classes=["section-title"]))
        page.append(Gtk.Label(label="Dynamic capability discovery, crash-safe task journals, secret redaction, completion verification, and interrupted-task recovery.", xalign=0, wrap=True, css_classes=["tiny"]))
        actions = Gtk.Box(spacing=7)
        refresh = Gtk.Button(label="Refresh tasks"); refresh.connect("clicked", self.refresh_agent_tasks); actions.append(refresh)
        open_mcp = Gtk.Button(label="Open MCP", css_classes=["send"]); open_mcp.connect("clicked", lambda *_: self.dock.select(self.dock.buttons["mcp"], "mcp")); actions.append(open_mcp)
        task_folder = Gtk.Button(label="Open task journals"); task_folder.connect("clicked", lambda *_: subprocess.Popen(["dolphin", str(self.data / "agent-tasks")]))
        actions.append(task_folder); page.append(actions)
        page.append(Gtk.Label(label="Use /tasks in MCP to inspect recent tasks and /resume after an interrupted run.", xalign=0, wrap=True, css_classes=["tiny"]))
        self.agent_status = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True); page.append(self.agent_status)

    def refresh_agent_tasks(self, *_):
        try:
            from agent_runtime import TaskJournal
            journal = TaskJournal(self.data); items = journal.recent(15); active = journal.recoverable()
            lines = ["Runtime ready · tasks are stored locally with sensitive arguments redacted."]
            if active: lines.append(f"\nRECOVERABLE\n{active.get('updated','')} · {active.get('command','')}")
            if items:
                lines.append("\nRECENT TASKS")
                lines.extend(f"{item.get('updated','')[:16].replace('T',' ')} · {item.get('status')} · {item.get('command','')[:90]}" for item in reversed(items))
            else: lines.append("\nNo recorded tasks yet.")
            try:
                mission = json.loads((self.data / "missions" / "current.json").read_text())
                lines.append(f"\nCURRENT MISSION\n{mission.get('status')} · {mission.get('kind')} · {mission.get('stage')}\n{mission.get('goal')}\nArtifacts: {len(mission.get('artifacts',[]))}")
            except (OSError, ValueError, TypeError): pass
            self.agent_status.set_text("\n".join(lines))
        except Exception as error: self.agent_status.set_text(f"Task runtime error: {error}")

    def run_power_tool(self, _button, tool_name, arguments):
        self.power_status.set_text(f"Running {tool_name}…")
        def worker():
            try:
                from mcp_client import McpConnections
                with McpConnections(self.mcp_config) as connections:
                    tools = {tool["name"]: tool for tool in connections.discover()}
                    if tool_name not in tools: raise RuntimeError(f"Tool is not loaded: {tool_name}")
                    response = connections.call(tools[tool_name], arguments)
                text = "\n".join(item.get("text", "") for item in response.get("content", []) if item.get("type") == "text") or "Completed."
            except Exception as error: text = f"Failed: {error}"
            GLib.idle_add(self.power_status.set_text, text)
        threading.Thread(target=worker, daemon=True).start()

    def clear(self, box):
        while child := box.get_first_child(): box.remove(child)

    def refresh_all(self, *_):
        self.refresh_browser(); self.inspect_memory(); self.refresh_agent_tasks(); self.load_test_history()

    def test_health(self, *_):
        for label in self.health_rows.values(): label.set_text("Checking…")
        self.health_summary.set_text("Testing provider composers and local services…")
        pending = {"count": 4, "ok": 0}
        selectors = self.dock.pages["flow"].INPUT_SELECTORS
        def done(view, result, provider):
            try:
                ready = bool(view.evaluate_javascript_finish(result).to_boolean())
                self.health_rows[provider].set_text("Ready" if ready else "Login or adapter attention required")
                pending["ok"] += int(ready)
            except Exception as error: self.health_rows[provider].set_text(f"Adapter error: {error}")
            pending["count"] -= 1
            if pending["count"] == 0: self._finish_health(pending["ok"])
        for provider in ("chatgpt", "gemini", "deepseek", "hackerai"):
            script = f"!!document.querySelector({json.dumps(selectors[provider])})"
            self.dock.pages[provider].evaluate_javascript(script, -1, None, None, None, done, provider)
        models = self.ollama_models(); self.health_rows["qwen"].set_text("Ready · " + str(len(models)) + " models" if models else "Ollama unavailable")
        threading.Thread(target=self._cloud_health, daemon=True).start()

    def _cloud_health(self):
        for provider in ("claude", "grok"):
            try:
                result = subprocess.run([str(self.cloud_python), str(self.cloud_bridge), "status", provider], capture_output=True, text=True, timeout=5)
                info = json.loads(result.stdout.strip().splitlines()[-1])
                text = "Ready" if info.get("ok") else "Browser not started · open popup once"
            except Exception as error: text = f"Bridge error: {error}"
            GLib.idle_add(self.health_rows[provider].set_text, text)

    def _finish_health(self, embedded_ok):
        self.health_summary.set_text(f"Embedded providers ready: {embedded_ok}/4. Health checks do not send messages or alter conversations.")

    def _browser_targets(self):
        try:
            with urllib.request.urlopen("http://127.0.0.1:9223/json", timeout=2) as response: return json.load(response)
        except Exception: return []

    def refresh_browser(self, *_):
        targets = self._browser_targets(); self.clear(self.browser_list)
        pages = [item for item in targets if item.get("type") == "page"]
        for item in pages:
            row = Gtk.Box(spacing=8, css_classes=["browser-row"])
            text = Gtk.Label(label=f"{item.get('title') or 'Untitled'}\n{item.get('url','')}", xalign=0, wrap=True, hexpand=True, selectable=True)
            row.append(text); self.browser_list.append(row)
        self.browser_status.set_text(f"{len(pages)} controlled tab(s)" if pages else "Controlled Brave is not running.")

    def merge_browser(self, *_):
        threading.Thread(target=self._merge_worker, daemon=True).start()

    def _merge_worker(self):
        try:
            from mcp_client import McpConnections
            with McpConnections(self.mcp_config) as c:
                tool = next(t for t in c.discover() if t["name"] == "browser__browser_merge_windows")
                result = c.call(tool, {})
            text = "\n".join(x.get("text", "") for x in result.get("content", []))
        except Exception as error: text = f"Merge failed: {error}"
        GLib.idle_add(self.browser_status.set_text, text); GLib.idle_add(self.refresh_browser)

    def search_brain(self, *_):
        query = self.brain_query.get_text().strip().lower(); self.clear(self.brain_results)
        if not query: return
        matches = []
        for note in self.brain.rglob("*.md"):
            try:
                body = note.read_text(errors="replace")
                if query in (note.name + " " + body).lower(): matches.append((note, body))
            except OSError: pass
        for note, body in matches[:20]:
            excerpt = next((line.strip() for line in body.splitlines() if query in line.lower()), body[:180])
            label = Gtk.Label(label=f"{note.relative_to(self.brain)}\n{excerpt[:260]}", xalign=0, wrap=True, selectable=True, css_classes=["brain-result"])
            self.brain_results.append(label)
        self.brain_status.set_text(f"{len(matches)} matching note(s). Showing up to 20.")

    def pin_memory(self, *_):
        text = self.pin_text.get_text().strip()
        if not text: return
        path = self.brain / "Memory" / "Pinned Memories.md"; path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists(): path.write_text("# Pinned Memories\n\n")
        with path.open("a") as stream: stream.write(f"- {datetime.now().isoformat(timespec='seconds')} — {text}\n")
        self.pin_text.set_text(""); self.brain_status.set_text(f"Pinned to {path.relative_to(self.brain)}")

    def temporary_memory(self, *_):
        text = self.pin_text.get_text().strip()
        if not text: return
        path = self.brain / "Memory" / "Temporary Memories.md"; path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists(): path.write_text("# Temporary Memories\n\nThese notes are not durable preferences and may be cleared manually.\n\n")
        with path.open("a") as stream: stream.write(f"- {datetime.now().isoformat(timespec='seconds')} — {text}\n")
        self.pin_text.set_text(""); self.brain_status.set_text(f"Marked temporary in {path.relative_to(self.brain)}")

    def safe_note(self):
        raw = self.note_path.get_text().strip()
        if not raw: raise ValueError("Enter a relative note path")
        candidate = (self.brain / raw).resolve()
        if self.brain.resolve() not in candidate.parents or candidate.suffix.lower() != ".md": raise ValueError("Only Markdown notes inside Connected Brain are allowed")
        return candidate

    def load_note(self, *_):
        try:
            path = self.safe_note(); self.note_editor.get_buffer().set_text(path.read_text(errors="replace")); self.brain_status.set_text(f"Loaded {path.relative_to(self.brain)}")
        except Exception as error: self.brain_status.set_text(f"Could not load note: {error}")

    def save_note(self, *_):
        try:
            path = self.safe_note(); buf = self.note_editor.get_buffer(); text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text); self.brain_status.set_text(f"Saved correction to {path.relative_to(self.brain)}")
        except Exception as error: self.brain_status.set_text(f"Could not save note: {error}")

    def trash_note(self, *_):
        try:
            path = self.safe_note(); Gio.File.new_for_path(str(path)).trash(None); self.note_editor.get_buffer().set_text("")
            self.brain_status.set_text(f"Moved {path.name} to Trash. It can be restored.")
        except Exception as error: self.brain_status.set_text(f"Could not Trash note: {error}")

    def explain_context(self, *_):
        query = self.brain_query.get_text().strip()
        if not query: self.brain_status.set_text("Enter a query first to see which notes may influence it."); return
        words = set(query.lower().split()); scored = []
        for note in self.brain.rglob("*.md"):
            try:
                body = note.read_text(errors="replace").lower(); score = sum(word in body or word in note.name.lower() for word in words)
                if score: scored.append((score, note))
            except OSError: pass
        names = [str(note.relative_to(self.brain)) for _score, note in sorted(scored, reverse=True)[:6]]
        self.brain_status.set_text("Likely influencing notes:\n" + ("\n".join(names) if names else "None"))

    def inspect_memory(self, *_):
        path = self.data / "mcp_memory.json"
        try: items = json.loads(path.read_text())
        except Exception: items = []
        self.brain_status.set_text(f"{len(items)} saved MCP memories. Clear chat does not delete them or the Obsidian archive.")

    def export_memory(self, *_):
        source = self.data / "mcp_memory.json"; folder = self.brain / "System"; folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"MCP Memory Snapshot {datetime.now().strftime('%Y-%m-%d %H%M%S')}.json"
        target.write_text(source.read_text() if source.exists() else "[]\n")
        self.brain_status.set_text(f"Exported: {target.relative_to(self.brain)}")

    def run_regression(self, *_):
        self.test_output.set_text("Running safe checks…")
        threading.Thread(target=self._regression_worker, daemon=True).start()

    def _regression_worker(self):
        checks = safe_regression(self.data, self.brain, self.mcp_config, self.ollama_models, self._browser_targets)
        stamp = datetime.now().isoformat(timespec="seconds")
        result = {"time": stamp, "checks": [{"name": n, "passed": ok, "detail": d} for n, ok, d in checks]}
        path = self.data / "regression-results.json"; path.write_text(json.dumps(result, indent=2) + "\n")
        lines = [f"{'PASS' if ok else 'FAIL'} · {name} · {detail}" for name, ok, detail in checks]
        GLib.idle_add(self.test_output.set_text, "\n".join(lines)); GLib.idle_add(self.load_test_history)

    def load_test_history(self):
        path = self.data / "regression-results.json"
        try:
            result = json.loads(path.read_text()); passed = sum(x["passed"] for x in result["checks"])
            self.test_history.set_text(f"Last run: {result['time']} · {passed}/{len(result['checks'])} passed")
        except Exception: self.test_history.set_text("No saved regression run yet.")
