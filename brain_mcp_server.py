#!/usr/bin/env python3
"""Obsidian vault MCP server for AI Dock's persistent shared brain."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path


VAULT = Path.home() / "Documents" / "Connected Brain"
VAULT.mkdir(parents=True, exist_ok=True)

TOOLS = [
    {"name": "brain_search", "description": "Search the Obsidian brain for notes relevant to a query and return matching excerpts.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}},
    {"name": "brain_read", "description": "Read a Markdown note from the Obsidian brain by title or relative path.", "inputSchema": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"], "additionalProperties": False}},
    {"name": "brain_write", "description": "Create, replace, or append to a Markdown note in the Obsidian brain.", "inputSchema": {"type": "object", "properties": {"note": {"type": "string"}, "content": {"type": "string"}, "mode": {"type": "string", "enum": ["append", "replace"]}}, "required": ["note", "content"], "additionalProperties": False}},
    {"name": "brain_list", "description": "List Markdown notes in the Obsidian brain, optionally under a folder.", "inputSchema": {"type": "object", "properties": {"folder": {"type": "string"}}, "additionalProperties": False}},
    {"name": "brain_context", "description": "Build a compact context packet from multiple relevant Brain notes for a new command or question.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "max_chars": {"type": "integer", "minimum": 1000, "maximum": 30000}}, "required": ["query"], "additionalProperties": False}},
    {"name": "brain_tasks", "description": "Find unfinished Markdown checkbox tasks across the Connected Brain, optionally filtered by a query.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "additionalProperties": False}},
    {"name": "brain_daily_note", "description": "Append a timestamped memory, decision, idea, or task to today's Connected Brain daily note.", "inputSchema": {"type": "object", "properties": {"content": {"type": "string"}, "section": {"type": "string", "enum": ["Memories", "Decisions", "Ideas", "Tasks"]}}, "required": ["content"], "additionalProperties": False}},
    {"name": "brain_stats", "description": "Report Connected Brain size, links, orphan notes, unfinished tasks, and most-linked notes.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
]

STOP_WORDS = {"the","and","for","with","that","this","from","into","your","you","are","was","were","have","has","had","can","could","would","should","what","when","where","which","who","why","how","about","then","than","them","they","their","there","here","just","also","some","any","all","not","but","its","our","out","use","using"}


def safe_note(value):
    value = value.strip().replace("\\", "/")
    if not value.lower().endswith(".md"): value += ".md"
    path = (VAULT / value).resolve()
    if VAULT.resolve() not in path.parents: raise ValueError("Note must remain inside the Connected Brain vault")
    return path


def text_result(text): return {"content": [{"type": "text", "text": text}]}


def search_matches(query):
    words = set(re.findall(r"[a-z0-9_]{3,}", query.lower())) - STOP_WORDS
    if not words: words = set(re.findall(r"[a-z0-9_]{3,}", query.lower()))
    matches = []
    for path in VAULT.rglob("*.md"):
        try: content = path.read_text(errors="replace")
        except OSError: continue
        lowered, title = content.lower(), path.stem.lower()
        positions = [lowered.find(word) for word in words if word in lowered]
        title_hits = sum(word in title for word in words)
        if positions or title_hits:
            start = max(0, min(positions) - 350) if positions else 0
            excerpt = content[start:start + 2400]
            exact = 5 if query.lower() in lowered else 0
            score = exact + title_hits * 4 + sum(min(8, excerpt.lower().count(word)) for word in words)
            matches.append((score, path, excerpt))
    matches.sort(key=lambda item: (-item[0], str(item[1])))
    return matches


def call_tool(name, args):
    if name == "brain_stats":
        notes = list(VAULT.rglob("*.md")); stems = {path.stem.lower() for path in notes}
        incoming = {stem: 0 for stem in stems}; outgoing = {stem: 0 for stem in stems}; links = tasks = 0
        for path in notes:
            content = path.read_text(errors="replace"); tasks += len(re.findall(r"(?m)^\s*[-*]\s+\[ \]", content))
            targets = re.findall(r"\[\[([^\]|#]+)", content); outgoing[path.stem.lower()] = len(targets)
            for target in targets:
                links += 1; key = Path(target.strip()).stem.lower()
                if key in incoming: incoming[key] += 1
        # Obsidian graph nodes are connected when they have either incoming
        # or outgoing links. Imported chats intentionally link outward to
        # their provider and index hubs, so they are not graph orphans.
        orphans = sum(1 for stem in stems if incoming[stem] == 0 and outgoing[stem] == 0)
        top = sorted(incoming.items(), key=lambda item: (-item[1], item[0]))[:8]
        return text_result(f"Connected Brain\nNotes: {len(notes)}\nWiki links: {links}\nOrphan notes: {orphans}\nUnfinished tasks: {tasks}\nMost linked: " + ", ".join(f"{name} ({count})" for name, count in top))
    if name == "brain_tasks":
        query, limit = str(args.get("query", "")).lower(), int(args.get("limit", 30)); found = []
        for path in VAULT.rglob("*.md"):
            for line_no, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if re.match(r"\s*[-*]\s+\[ \]", line) and (not query or query in (str(path) + " " + line).lower()):
                    found.append(f"{path.relative_to(VAULT)}:{line_no} · {line.strip()}")
                    if len(found) >= limit: return text_result("\n".join(found))
        return text_result("\n".join(found) or "No unfinished Brain tasks found.")
    if name == "brain_daily_note":
        today = datetime.now(); path = VAULT / "Daily" / f"{today:%Y-%m-%d}.md"; path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists(): path.write_text(f"---\ntype: daily-note\ndate: {today:%Y-%m-%d}\ntags: [connected-brain, daily]\n---\n\n# {today:%Y-%m-%d}\n")
        section, content = args.get("section", "Memories"), str(args["content"]).strip()
        with path.open("a") as stream: stream.write(f"\n## {section}\n\n- {today:%H:%M} · {content}\n")
        return text_result(f"Added to daily Brain note: {path.relative_to(VAULT)} · {section}")
    if name == "brain_context":
        query, maximum = str(args["query"]).strip(), int(args.get("max_chars", 12000)); chunks, used = [], 0
        for score, path, excerpt in search_matches(query)[:12]:
            header = f"## [[{path.relative_to(VAULT).with_suffix('')}]] · relevance {score}\n"
            piece = header + excerpt.strip() + "\n"
            if used + len(piece) > maximum: piece = piece[:max(0, maximum - used)]
            if piece: chunks.append(piece); used += len(piece)
            if used >= maximum: break
        return text_result("\n\n".join(chunks) or "No relevant Brain context found.")
    if name == "brain_list":
        folder = str(args.get("folder", "")).strip()
        root = (VAULT / folder).resolve()
        if root != VAULT.resolve() and VAULT.resolve() not in root.parents: raise ValueError("Folder is outside the vault")
        notes = sorted(str(path.relative_to(VAULT)) for path in root.rglob("*.md")) if root.exists() else []
        return text_result("\n".join(notes) or "No notes found.")
    if name == "brain_read":
        requested = str(args.get("note", args.get("path", "")))
        if not requested: raise ValueError("Provide a note or path")
        path = safe_note(requested)
        if not path.exists():
            matches = [item for item in VAULT.rglob("*.md") if item.stem.lower() == Path(requested).stem.lower()]
            if not matches: raise ValueError(f"Brain note not found: {requested}")
            path = matches[0]
        return text_result(f"NOTE: {path.relative_to(VAULT)}\n\n{path.read_text(errors='replace')}")
    if name == "brain_write":
        requested = str(args.get("note", args.get("path", "")))
        if not requested: raise ValueError("Provide a note or path")
        path = safe_note(requested); path.parent.mkdir(parents=True, exist_ok=True)
        content, mode = str(args["content"]), str(args.get("mode", "append"))
        if mode == "replace": path.write_text(content.rstrip() + "\n")
        else:
            with path.open("a") as stream: stream.write(content.rstrip() + "\n\n")
        return text_result(f"Wrote Obsidian note: {path.relative_to(VAULT)}")
    if name == "brain_search":
        query = str(args["query"]).strip(); matches = search_matches(query)
        if not matches: return text_result("No relevant brain notes found.")
        return text_result("\n\n".join(f"## {path.relative_to(VAULT)}\n{excerpt}" for _score, path, excerpt in matches[:8]))
    raise ValueError(f"Unknown brain tool: {name}")


for raw in sys.stdin:
    try:
        message = json.loads(raw); request_id = message.get("id")
        if request_id is None: continue
        method = message.get("method")
        if method == "initialize": response = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "AI Dock Obsidian Brain", "version": "1.0"}}
        elif method == "tools/list": response = {"tools": TOOLS}
        elif method == "tools/call":
            params = message.get("params", {}); response = call_tool(params.get("name"), params.get("arguments", {}))
        else: raise ValueError(f"Unsupported MCP method: {method}")
        reply = {"jsonrpc": "2.0", "id": request_id, "result": response}
    except Exception as error:
        reply = {"jsonrpc": "2.0", "id": message.get("id") if "message" in locals() else None, "error": {"code": -32000, "message": str(error)}}
    print(json.dumps(reply, separators=(",", ":")), flush=True)
