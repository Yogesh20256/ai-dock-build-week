"""Clean-room universal orchestration primitives for AI Dock.

This module deliberately contains no provider-specific or leaked implementation.
It gives the Dock a compact capability search layer and a crash-safe task journal.
"""
import hashlib
import json
import os
import re
import time
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path


SECRET_KEYS = {"password", "passwd", "token", "secret", "api_key", "apikey", "authorization", "cookie"}
TOOL_SEARCH = {
    "type": "function",
    "function": {
        "name": "runtime__search_tools",
        "description": "Search the complete live MCP capability catalog when the currently exposed tools cannot finish the request. Returns exact tool names, descriptions and argument schemas. Call this instead of guessing a tool name.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Capability needed, in plain language"},
                "server": {"type": "string", "description": "Optional MCP server/family filter"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"], "additionalProperties": False,
        },
    },
}
PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "runtime__set_plan",
        "description": "Record a concise dependency-ordered plan for a multi-step request before executing it. Do not use for a single obvious action.",
        "parameters": {
            "type": "object", "properties": {
                "steps": {"type": "array", "minItems": 2, "maxItems": 20, "items": {
                    "type": "object", "properties": {
                        "id": {"type": "string"}, "goal": {"type": "string"},
                        "depends_on": {"type": "array", "items": {"type": "string"}},
                        "verification": {"type": "string"},
                    }, "required": ["id", "goal", "verification"], "additionalProperties": False,
                }}
            }, "required": ["steps"], "additionalProperties": False,
        },
    },
}


def _words(value):
    return set(re.findall(r"[a-z0-9]{2,}", str(value).lower().replace("_", " ")))


SEMANTIC_ALIASES = {
    "app":{"application","software","program"},"application":{"app","software","program"},
    "folder":{"directory","path"},"directory":{"folder","path"},
    "delete":{"remove","trash"},"remove":{"delete","trash"},
    "download":{"fetch","install"},"install":{"package","software","setup"},
    "website":{"webpage","browser","url","site"},"webpage":{"website","browser","url","page"},
    "remember":{"memory","brain","note"},"memory":{"remember","brain","context"},
    "record":{"capture","screen","video"},"capture":{"record","screenshot","screen"},
    "version":{"package","installed","release"},"update":{"upgrade","package","version"},
    "workspace":{"window","desktop"},"window":{"workspace","application","desktop"},
    "report":{"document","pdf","markdown"},"document":{"file","report","text"},
    "code":{"source","project","developer"},"debug":{"diagnose","code","error","bug"},
    "research":{"internet","search","sources","evidence"},"fetch":{"download","internet","retrieve"},
    "click":{"press","select","tap"},"open":{"launch","start","navigate"},"close":{"quit","exit","stop"},
    "vscode":{"code","editor","application"},"terminal":{"shell","console","application"},
    "dolphin":{"files","folder","manager","application"},"gmail":{"email","mail","website"},
}


def _expanded_words(value):
    base=_words(value);return base|{alias for word in base for alias in SEMANTIC_ALIASES.get(word,set())}


def semantic_terms(value):
    return _expanded_words(value)


def semantic_similarity(left, right):
    a=semantic_terms(left);b=semantic_terms(right)
    if not a or not b:return 0.0
    exact=len(a&b);fuzzy=0
    for word in a-b:
        if len(word)>=4 and max((SequenceMatcher(None,word,target).ratio() for target in b if abs(len(word)-len(target))<=2),default=0)>=.84:fuzzy+=1
    return (exact+0.6*fuzzy)/(len(a|b) or 1)


def redact(value):
    if isinstance(value, dict):
        return {key: ("<redacted>" if str(key).lower() in SECRET_KEYS else redact(item)) for key, item in value.items()}
    if isinstance(value, list): return [redact(item) for item in value]
    text = str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value
    if isinstance(text, str):
        text = re.sub(r"(?i)(bearer\s+)[a-z0-9._~+/-]+", r"\1<redacted>", text)
        text = re.sub(r"(?i)(password|token|secret|api[_-]?key)\s*[:=]\s*\S+", r"\1=<redacted>", text)
        return text[:12000]
    return text


def validate_plan(steps):
    if not isinstance(steps, list) or not 2 <= len(steps) <= 20: raise ValueError("A plan needs 2-20 steps")
    ids = [str(item.get("id", "")).strip() for item in steps]
    if any(not item for item in ids) or len(set(ids)) != len(ids): raise ValueError("Plan step IDs must be non-empty and unique")
    seen = set(); clean = []
    for item, step_id in zip(steps, ids):
        dependencies = [str(value) for value in item.get("depends_on", [])]
        if any(value not in seen for value in dependencies): raise ValueError(f"Step {step_id} depends on a missing or future step")
        goal = str(item.get("goal", "")).strip(); verification = str(item.get("verification", "")).strip()
        if not goal or not verification: raise ValueError(f"Step {step_id} needs a goal and verification")
        clean.append({"id": step_id, "goal": goal[:500], "depends_on": dependencies, "verification": verification[:500]}); seen.add(step_id)
    return clean


class CapabilityIndex:
    """Rank a live MCP catalog without putting every schema in model context."""
    def __init__(self, tools):
        self.tools = list(tools)
        self.by_name = {tool["name"]: tool for tool in self.tools}

    def search(self, query, server=None, limit=10, exclude=()):
        wanted = _expanded_words(query); excluded = set(exclude); ranked = []
        for tool in self.tools:
            if tool["name"] in excluded: continue
            if server and tool.get("server", "").lower() != str(server).lower(): continue
            name_words = _words(tool["name"]); description_words = _words(tool.get("description", ""))
            overlap = len(wanted & description_words) + 3 * len(wanted & name_words)
            fuzzy=0
            for word in wanted:
                if len(word)<4:continue
                best=max((SequenceMatcher(None,word,target).ratio() for target in name_words|description_words if abs(len(target)-len(word))<=2),default=0)
                if best>=.82:fuzzy+=2 if best>=.9 else 1
            phrase = str(query).lower() in (tool["name"] + " " + tool.get("description", "")).lower()
            family = int(tool.get("server", "").lower() in wanted)
            score = overlap + fuzzy + 4 * phrase + 2 * family
            if score: ranked.append((score, tool["name"], tool))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [tool for _score, _name, tool in ranked[:max(1, min(int(limit or 10), 20))]]

    @staticmethod
    def compact(tools):
        return [{"name": t["name"], "description": t.get("description", ""), "arguments": t.get("inputSchema", {})} for t in tools]


class TaskJournal:
    """Crash-safe durable MCP task history and resumable last-command state."""
    def __init__(self, data_dir):
        self.root = Path(data_dir) / "agent-tasks"; self.root.mkdir(parents=True, exist_ok=True)
        self.active_path = self.root / "active.json"; self.index_path = self.root / "index.json"

    def _atomic(self, path, payload):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)

    def start(self, command, metadata=None):
        now = datetime.now().isoformat(timespec="seconds")
        task_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + hashlib.sha256(f"{time.time_ns()}:{command}".encode()).hexdigest()[:8]
        task = {"version": 1, "id": task_id, "command": str(command), "status": "running", "created": now, "updated": now,
                "metadata": redact(metadata or {}), "events": []}
        self._atomic(self.active_path, task); self._atomic(self.root / f"{task_id}.json", task)
        return task

    def event(self, task, kind, **detail):
        if not task: return
        now = datetime.now().isoformat(timespec="seconds")
        task["events"].append({"time": now, "kind": kind, **redact(detail)})
        task["events"] = task["events"][-300:]; task["updated"] = now
        self._atomic(self.active_path, task); self._atomic(self.root / f"{task['id']}.json", task)

    @staticmethod
    def action_fingerprint(action):
        payload=str(action.get("tool",""))+"\0"+json.dumps(action.get("arguments",{}),sort_keys=True,ensure_ascii=False,separators=(",",":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def set_execution_plan(self, task, actions, provider="", preserve_completed=False):
        if not task:return
        previous=task.get("execution",{}) if preserve_completed else {}
        completed=list(previous.get("completed",[]));completed_ids={item.get("fingerprint") for item in completed}
        clean=redact(actions)
        task["execution"]={"provider":str(provider),"actions":clean,"completed":completed,"completed_fingerprints":sorted(x for x in completed_ids if x),"updated":datetime.now().isoformat(timespec="seconds")}
        self.event(task,"execution_plan_set",provider=provider,actions=len(clean),preserved_completed=len(completed))

    def complete_action(self, task, action, result_text=""):
        if not task:return
        execution=task.setdefault("execution",{"actions":[],"completed":[],"completed_fingerprints":[]})
        fingerprint=self.action_fingerprint(redact(action))
        if fingerprint not in set(execution.get("completed_fingerprints",[])):
            execution.setdefault("completed",[]).append({"fingerprint":fingerprint,"action":redact(action),"result":redact(str(result_text)[:4000]),"time":datetime.now().isoformat(timespec="seconds")})
            execution["completed"]=execution["completed"][-100:]
            execution["completed_fingerprints"]=sorted(set(execution.get("completed_fingerprints",[]))|{fingerprint})
        self.event(task,"action_checkpoint",fingerprint=fingerprint,tool=action.get("tool"))

    def remaining_actions(self, task):
        execution=(task or {}).get("execution",{});done=set(execution.get("completed_fingerprints",[]))
        return [item for item in execution.get("actions",[]) if self.action_fingerprint(item) not in done]

    def finish(self, task, status, summary=""):
        if not task: return
        self.event(task, "finished", status=status, summary=str(summary)[:12000])
        task["status"] = status; task["updated"] = datetime.now().isoformat(timespec="seconds")
        self._atomic(self.root / f"{task['id']}.json", task)
        try: current = json.loads(self.index_path.read_text())
        except (OSError, ValueError, TypeError): current = []
        current = [item for item in current if item.get("id") != task["id"]]
        current.append({key: task.get(key) for key in ("id", "command", "status", "created", "updated")})
        self._atomic(self.index_path, current[-200:])
        try: self.active_path.unlink()
        except FileNotFoundError: pass

    def recoverable(self):
        try:
            task = json.loads(self.active_path.read_text())
            return task if task.get("status") == "running" else None
        except (OSError, ValueError, TypeError): return None

    def recent(self, limit=10):
        try: items = json.loads(self.index_path.read_text())
        except (OSError, ValueError, TypeError): items = []
        active = self.recoverable()
        if active: items.append({key: active.get(key) for key in ("id", "command", "status", "created", "updated")})
        return items[-max(1, int(limit)):]


def completion_report(command, tool_events, final_text):
    successes = [event for event in tool_events if event.get("status") == "completed"]
    failures = [event for event in tool_events if event.get("status") == "failed"]
    action_words = _words(command) & {"open", "close", "create", "delete", "move", "install", "update", "search", "click", "write", "download"}
    if action_words and not successes:
        return {"verified": False, "reason": "The request required an action but no tool completed successfully."}
    if failures and (not successes or tool_events[-1].get("status") == "failed"):
        return {"verified": False, "reason": f"{len(failures)} tool action(s) failed and the last action did not demonstrate recovery."}
    if not str(final_text).strip():
        return {"verified": False, "reason": "The agent produced no completion summary."}
    recovery = f" after recovering from {len(failures)} failure(s)" if failures else ""
    return {"verified": True, "reason": f"{len(successes)} tool action(s) completed with MCP results{recovery}."}
