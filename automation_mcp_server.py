#!/usr/bin/env python3
"""Automation, recipes, schedules, audit history, and health MCP for AI Dock."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

from mcp_client import McpServer


ROOT = Path(__file__).resolve().parent
CONFIG = Path.home() / ".config" / "ai-dock" / "mcp_servers.json"
DATA = Path.home() / ".local" / "share" / "ai-dock" / "automation"
RECIPES = DATA / "recipes.json"
SCHEDULES = DATA / "schedules.json"
ACTIVITY = DATA / "activity.jsonl"
PROCEDURES = DATA.parent / "learned_procedures.json"
BACKUPS = Path.home() / "Documents" / "C_Programming" / "ai-dock-backups" / "power-snapshots"
DATA.mkdir(parents=True, exist_ok=True)

RISKY_TOOLS = {
    "packages__package_install_or_update", "packages__software_install_resolved", "packages__software_install_product", "system__file_write", "system__file_create",
    "system__file_copy_move", "system__file_trash", "system__process_stop",
    "system__service_manage", "system__git_manage", "desktop__create_folder",
    "desktop__close_application", "desktop__type_text", "desktop__press_key",
    "desktop__click_screen",
    "browser__browser_close",
    "data__json_format", "data__data_convert", "data__data_filter", "data__data_sort", "data__data_deduplicate",
    "operations__clipboard_write", "operations__clipboard_capture", "operations__clipboard_restore", "operations__snippet_save", "operations__batch_rename_apply", "operations__organize_apply",
    "operations__extract_pdf_text", "operations__convert_image", "operations__convert_media", "operations__sync_apply",
    "monitor__monitor_rule_create", "monitor__monitor_rule_enable", "monitor__monitor_rule_delete",
    "research__download_verified", "knowledge__knowledge_remove_source", "missions__github_publish", "missions__project_build",
}

TOOLS = [
    {"name":"automation_health_check","description":"Run a comprehensive read-only AI Dock health check covering dependencies, Ollama, MCP servers, Brain, storage, browser profile, and configuration.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
    {"name":"automation_capabilities","description":"Search or list AI Dock tools and capabilities by natural keywords.","inputSchema":{"type":"object","properties":{"query":{"type":"string"}},"additionalProperties":False}},
    {"name":"recipe_save","description":"Save a reusable named multi-step MCP recipe. Each action contains tool and arguments. Risky actions require allow_risky=true.","inputSchema":{"type":"object","properties":{"name":{"type":"string"},"description":{"type":"string"},"actions":{"type":"array","items":{"type":"object","properties":{"tool":{"type":"string"},"arguments":{"type":"object"}},"required":["tool"],"additionalProperties":False},"minItems":1,"maxItems":20},"allow_risky":{"type":"boolean"}},"required":["name","actions"],"additionalProperties":False}},
    {"name":"recipe_list","description":"List saved automation recipes and their action counts.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
    {"name":"recipe_read","description":"Show the full steps of a saved recipe.","inputSchema":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"],"additionalProperties":False}},
    {"name":"recipe_run","description":"Execute a saved multi-step recipe and return verified step-by-step results.","inputSchema":{"type":"object","properties":{"name":{"type":"string"},"variables":{"type":"object"}},"required":["name"],"additionalProperties":False}},
    {"name":"recipe_delete","description":"Delete a saved recipe by name.","inputSchema":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"],"additionalProperties":False}},
    {"name":"recipe_simulate","description":"Validate a saved recipe and show fully substituted steps, tool availability and risky actions without executing anything.","inputSchema":{"type":"object","properties":{"name":{"type":"string"},"variables":{"type":"object"}},"required":["name"],"additionalProperties":False}},
    {"name":"learned_procedure_list","description":"List multi-step procedures automatically learned only after independent result verification.","inputSchema":{"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":200}},"additionalProperties":False}},
    {"name":"learned_procedure_read","description":"Read one verified learned procedure by ID, including request, actions, verification and success count.","inputSchema":{"type":"object","properties":{"id":{"type":"string"}},"required":["id"],"additionalProperties":False}},
    {"name":"learned_procedure_delete","description":"Delete a learned procedure record without affecting files or saved recipes. Requires confirm exactly FORGET PROCEDURE.","inputSchema":{"type":"object","properties":{"id":{"type":"string"},"confirm":{"type":"string"}},"required":["id","confirm"],"additionalProperties":False}},
    {"name":"learned_procedure_promote","description":"Promote a verified learned procedure into a named reusable recipe after review. Risky steps require allow_risky=true.","inputSchema":{"type":"object","properties":{"id":{"type":"string"},"name":{"type":"string"},"allow_risky":{"type":"boolean"}},"required":["id","name"],"additionalProperties":False}},
    {"name":"schedule_create","description":"Schedule a saved recipe once or repeatedly. Use run_at ISO local time or delay_minutes; interval_minutes enables repetition.","inputSchema":{"type":"object","properties":{"name":{"type":"string"},"recipe":{"type":"string"},"run_at":{"type":"string"},"delay_minutes":{"type":"integer","minimum":0},"interval_minutes":{"type":"integer","minimum":1},"variables":{"type":"object"},"enabled":{"type":"boolean"}},"required":["name","recipe"],"additionalProperties":False}},
    {"name":"schedule_list","description":"List pending, repeating, completed, and failed scheduled recipes.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
    {"name":"schedule_cancel","description":"Cancel and remove a scheduled job.","inputSchema":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"],"additionalProperties":False}},
    {"name":"schedule_run_due","description":"Run every due scheduled recipe now. Normally called automatically by AI Dock's timer.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
    {"name":"activity_recent","description":"Read recent recipe, schedule, and automation activity for debugging and accountability.","inputSchema":{"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":100}},"additionalProperties":False}},
    {"name":"backup_create","description":"Create a lightweight timestamped AI Dock source and configuration backup with a SHA-256 integrity file; excludes large browser profiles and virtual environments.","inputSchema":{"type":"object","properties":{"label":{"type":"string"}},"additionalProperties":False}},
    {"name":"backup_list","description":"List AI Dock power snapshots with size and integrity status.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
    {"name":"backup_verify","description":"Verify the SHA-256 integrity of a named AI Dock power snapshot.","inputSchema":{"type":"object","properties":{"file":{"type":"string"}},"required":["file"],"additionalProperties":False}},
    {"name":"backup_restore","description":"Restore AI Dock source/configuration from a verified power snapshot. Requires confirm exactly RESTORE and application restart afterward.","inputSchema":{"type":"object","properties":{"file":{"type":"string"},"confirm":{"type":"string"}},"required":["file","confirm"],"additionalProperties":False}},
    {"name":"diagnostic_bundle","description":"Create a shareable text diagnostic report containing health, service, model, MCP, scheduler, and recent activity status without credentials.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
]


def load(path: Path, default):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def result(text):
    return {"content": [{"type": "text", "text": str(text)}]}


def record(kind, name, status, detail=""):
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, "name": name, "status": status, "detail": str(detail)[:4000]}
    with ACTIVITY.open("a") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")


def clean_name(value):
    name = " ".join(str(value).strip().split())
    if not name or len(name) > 80: raise ValueError("Name must contain 1-80 characters")
    return name


def public_tools():
    config = load(CONFIG, {"servers": {}})
    found = []
    for server_name, server_config in config.get("servers", {}).items():
        if server_name == "automation" or not server_config.get("enabled", True): continue
        server = None
        try:
            server = McpServer(server_name, server_config)
            for tool in server.tools():
                found.append({"name": f"{server_name}__{tool['name']}", "description": tool.get("description", ""), "schema": tool.get("inputSchema", {})})
        finally:
            if server: server.close()
    return found


def substitute(value, variables):
    if isinstance(value, str):
        for key, replacement in variables.items():
            value = value.replace("{{" + str(key) + "}}", str(replacement))
        return value
    if isinstance(value, list): return [substitute(item, variables) for item in value]
    if isinstance(value, dict): return {key: substitute(item, variables) for key, item in value.items()}
    return value


def execute_actions(actions, variables=None):
    variables = variables or {}
    config = load(CONFIG, {"servers": {}}).get("servers", {})
    connections, outputs = {}, []
    try:
        for index, action in enumerate(actions, 1):
            public_name = str(action.get("tool", ""))
            if "__" not in public_name: raise ValueError(f"Invalid tool name in step {index}: {public_name}")
            server_name, tool_name = public_name.split("__", 1)
            if server_name == "automation": raise ValueError("Recipes cannot recursively call automation tools")
            if server_name not in config or not config[server_name].get("enabled", True): raise ValueError(f"MCP server unavailable: {server_name}")
            if server_name not in connections: connections[server_name] = McpServer(server_name, config[server_name])
            server = connections[server_name]
            catalog = {tool["name"]: tool for tool in server.tools()}
            if tool_name not in catalog: raise ValueError(f"Tool unavailable: {public_name}")
            arguments = substitute(action.get("arguments", {}), variables)
            response = server.call(tool_name, arguments)
            text = "\n".join(item.get("text", "") for item in response.get("content", []) if item.get("type") == "text")
            outputs.append(f"STEP {index} · {public_name}\n{text or 'Completed.'}")
        return "\n\n".join(outputs)
    finally:
        for connection in connections.values(): connection.close()


def health_check():
    checks = []
    def add(name, ok, detail): checks.append((name, bool(ok), str(detail)))
    for command in ("python3", "ollama", "grim", "slurp", "hyprctl", "notify-send", "brave", "dolphin"):
        path = shutil.which(command); add(f"command:{command}", path, path or "missing")
    try:
        reply = subprocess.run(["curl", "-fsS", "--max-time", "4", "http://127.0.0.1:11434/api/tags"], capture_output=True, text=True, timeout=6)
        models = [item.get("name") for item in json.loads(reply.stdout).get("models", [])] if reply.returncode == 0 else []
        add("ollama", bool(models), ", ".join(models[:8]) or reply.stderr.strip())
    except Exception as error: add("ollama", False, error)
    def find_vault():
        for name in ("Obsidian Vault", "Connected Brain", "Brain"):
            p = Path.home() / "Documents" / name
            if p.is_dir(): return p
        return Path.home() / "Documents" / "Obsidian Vault"
    brain = find_vault()
    notes = sum(1 for _ in brain.rglob("*.md")) if brain.is_dir() else 0
    add("obsidian-vault", notes > 0, f"{notes} Markdown notes")
    add("mcp-config", CONFIG.is_file(), CONFIG)
    try:
        tools = public_tools(); add("mcp-tools", len(tools) > 0, f"{len(tools)} tools across {len(set(item['name'].split('__',1)[0] for item in tools))} servers")
    except Exception as error: add("mcp-tools", False, error)
    profile = Path.home() / ".local" / "share" / "ai-dock" / "web-data"
    add("browser-profile", profile.exists(), profile)
    usage = shutil.disk_usage(Path.home())
    add("disk-space", usage.free > 2 * 1024**3, f"{usage.free / 1024**3:.1f} GiB free")
    passed = sum(ok for _name, ok, _detail in checks)
    lines = [f"AI DOCK HEALTH · {passed}/{len(checks)} passed · {datetime.now().isoformat(timespec='seconds')}"]
    lines.extend(f"{'PASS' if ok else 'FAIL'} · {name} · {detail}" for name, ok, detail in checks)
    return "\n".join(lines)


def run_recipe(name, variables=None):
    recipes = load(RECIPES, {})
    if name not in recipes: raise ValueError(f"Recipe not found: {name}")
    record("recipe", name, "started")
    try:
        output = execute_actions(recipes[name]["actions"], variables)
        record("recipe", name, "completed", output)
        return output
    except Exception as error:
        record("recipe", name, "failed", error)
        raise


def run_due():
    schedules = load(SCHEDULES, {})
    now, outputs, changed = datetime.now(), [], False
    for name, item in list(schedules.items()):
        if not item.get("enabled", True) or item.get("status") == "completed": continue
        try: due = datetime.fromisoformat(item["next_run"])
        except (KeyError, ValueError): continue
        if due > now: continue
        try:
            output = run_recipe(item["recipe"], item.get("variables", {}))
            outputs.append(f"{name}: completed\n{output}")
            item["last_status"], item["last_error"], item["last_run"] = "completed", "", now.isoformat(timespec="seconds")
        except Exception as error:
            outputs.append(f"{name}: failed · {error}")
            item["last_status"], item["last_error"], item["last_run"] = "failed", str(error), now.isoformat(timespec="seconds")
        interval = item.get("interval_minutes")
        if interval: item["next_run"] = (now + timedelta(minutes=int(interval))).isoformat(timespec="seconds")
        else: item["status"] = "completed"
        changed = True
    if changed: save(SCHEDULES, schedules)
    return "\n\n".join(outputs) or "No scheduled recipes are due."


def backup_path(value):
    name = Path(str(value)).name
    path = (BACKUPS / name).resolve()
    if path.parent != BACKUPS.resolve() or path.suffixes[-2:] != [".tar", ".gz"]: raise ValueError("Choose a .tar.gz file from the AI Dock power snapshots folder")
    if not path.is_file(): raise ValueError(f"Backup not found: {name}")
    return path


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): hasher.update(chunk)
    return hasher.hexdigest()


def call_tool(name, args):
    if name == "automation_health_check": return result(health_check())
    if name == "automation_capabilities":
        query = str(args.get("query", "")).lower().split()
        tools = public_tools()
        if query: tools = [item for item in tools if all(word in (item["name"] + " " + item["description"]).lower() for word in query)]
        return result("\n".join(f"{item['name']} · {item['description']}" for item in tools) or "No matching capabilities.")
    if name == "backup_create":
        BACKUPS.mkdir(parents=True, exist_ok=True)
        label = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(args.get("label", "manual")).strip()).strip("-")[:40] or "manual"
        path = BACKUPS / f"ai-dock-{datetime.now():%Y%m%d-%H%M%S}-{label}.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            for source, arcname in (
                (ROOT, "ai-dock"),
                (Path.home()/".config/ai-dock", "config/ai-dock"),
                (Path.home()/".config/caelestia/hypr-user.lua", "config/caelestia/hypr-user.lua"),
                (Path.home()/".config/systemd/user/ai-dock-monitor.service", "config/systemd/user/ai-dock-monitor.service"),
                (Path.home()/".config/systemd/user/ai-dock-monitor.timer", "config/systemd/user/ai-dock-monitor.timer"),
                (Path.home()/".config/systemd/user/ai-dock-scheduler.service", "config/systemd/user/ai-dock-scheduler.service"),
                (Path.home()/".config/systemd/user/ai-dock-scheduler.timer", "config/systemd/user/ai-dock-scheduler.timer"),
                (Path.home()/".local/share/ai-dock/conversation_state.json", "runtime/conversation_state.json"),
            ):
                if not source.exists(): continue
                archive.add(source, arcname=arcname, filter=lambda info: None if any(part in (".venv","__pycache__","node_modules") for part in Path(info.name).parts) else info)
        sha = digest(path); path.with_suffix(path.suffix+".sha256").write_text(f"{sha}  {path.name}\n")
        record("backup", path.name, "created", sha); return result(f"Created backup: {path}\nSHA-256: {sha}\nSize: {path.stat().st_size} bytes")
    if name == "backup_list":
        BACKUPS.mkdir(parents=True, exist_ok=True); lines=[]
        for path in sorted(BACKUPS.glob("*.tar.gz"), reverse=True):
            checksum = path.with_suffix(path.suffix+".sha256")
            expected = checksum.read_text().split()[0] if checksum.exists() else ""
            status = "verified" if expected and digest(path)==expected else "unverified"
            lines.append(f"{path.name} · {path.stat().st_size/1024:.1f} KiB · {status}")
        return result("\n".join(lines) or "No power snapshots created.")
    if name == "backup_verify":
        path=backup_path(args["file"]); checksum=path.with_suffix(path.suffix+".sha256")
        if not checksum.exists(): raise ValueError("Backup has no SHA-256 file")
        expected=checksum.read_text().split()[0]; actual=digest(path)
        if actual!=expected: raise ValueError(f"Integrity failure: expected {expected}, got {actual}")
        return result(f"Verified backup: {path.name}\nSHA-256: {actual}")
    if name == "backup_restore":
        if args.get("confirm") != "RESTORE": raise ValueError("Set confirm exactly to RESTORE after reviewing the backup")
        path=backup_path(args["file"]); checksum=path.with_suffix(path.suffix+".sha256")
        if not checksum.exists() or digest(path)!=checksum.read_text().split()[0]: raise ValueError("Backup integrity verification failed")
        safety=call_tool("backup_create",{"label":"before-restore"})["content"][0]["text"]
        with tarfile.open(path,"r:gz") as archive:
            members=archive.getmembers()
            if any(member.name.startswith("/") or ".." in Path(member.name).parts for member in members): raise ValueError("Unsafe path in backup archive")
            temporary=DATA/"restore"; shutil.rmtree(temporary,ignore_errors=True); temporary.mkdir(parents=True)
            archive.extractall(temporary,filter="data")
        restored=temporary/"ai-dock"; restored_config=temporary/"config/ai-dock"
        if not (restored/"ai_dock.py").exists(): raise ValueError("Backup does not contain AI Dock source")
        for source in restored.iterdir():
            destination=ROOT/source.name
            if source.is_dir(): shutil.copytree(source,destination,dirs_exist_ok=True)
            else: shutil.copy2(source,destination)
        if restored_config.exists(): shutil.copytree(restored_config,Path.home()/".config/ai-dock",dirs_exist_ok=True)
        for relative in ("caelestia/hypr-user.lua", "systemd/user/ai-dock-monitor.service", "systemd/user/ai-dock-monitor.timer", "systemd/user/ai-dock-scheduler.service", "systemd/user/ai-dock-scheduler.timer"):
            source=temporary/"config"/relative
            if source.exists():
                destination=Path.home()/".config"/relative; destination.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,destination)
        restored_state=temporary/"runtime/conversation_state.json"
        if restored_state.exists():
            destination=Path.home()/".local/share/ai-dock/conversation_state.json";destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(restored_state,destination)
        record("backup",path.name,"restored"); return result(f"Restored {path.name}. Restart AI Dock to load it.\n{safety}")
    if name == "diagnostic_bundle":
        reports=Path.home()/"Documents"/"AI Dock Reports"; reports.mkdir(parents=True,exist_ok=True); path=reports/f"AI-Dock-Diagnostics-{datetime.now():%Y%m%d-%H%M%S}.txt"
        sections=[health_check()]
        for title,command in (("SCHEDULER",["systemctl","--user","status","ai-dock-scheduler.timer","--no-pager"]),("MODELS",["ollama","list"]),("RECENT SERVICE LOG",["journalctl","--user","-u","ai-dock-scheduler.service","-n","30","--no-pager"])):
            response=subprocess.run(command,capture_output=True,text=True,timeout=15); sections.append(f"\n{title}\n{response.stdout}{response.stderr}")
        try: sections.append("\nRECENT AUTOMATION\n"+"\n".join(ACTIVITY.read_text().splitlines()[-30:]))
        except OSError: pass
        path.write_text("\n".join(sections)); return result(f"Created diagnostic bundle: {path}")
    recipes = load(RECIPES, {})
    if name == "recipe_save":
        recipe_name, actions = clean_name(args["name"]), args["actions"]
        risky = [item.get("tool") for item in actions if item.get("tool") in RISKY_TOOLS]
        if risky and not args.get("allow_risky", False): raise ValueError("Recipe contains risky actions; explicitly set allow_risky=true: " + ", ".join(risky))
        available = {item["name"] for item in public_tools()}
        missing = [item.get("tool") for item in actions if item.get("tool") not in available]
        if missing: raise ValueError("Unavailable recipe tools: " + ", ".join(map(str, missing)))
        recipes[recipe_name] = {"description": str(args.get("description", "")), "actions": actions, "allow_risky": bool(args.get("allow_risky")), "created": datetime.now().isoformat(timespec="seconds")}
        save(RECIPES, recipes); record("recipe", recipe_name, "saved")
        return result(f"Saved recipe: {recipe_name} · {len(actions)} steps")
    if name == "recipe_list":
        return result("\n".join(f"{key} · {len(value.get('actions', []))} steps · {value.get('description','')}" for key, value in sorted(recipes.items())) or "No recipes saved.")
    if name == "recipe_read":
        recipe_name = clean_name(args["name"])
        if recipe_name not in recipes: raise ValueError(f"Recipe not found: {recipe_name}")
        return result(json.dumps({recipe_name: recipes[recipe_name]}, indent=2, ensure_ascii=False))
    if name == "recipe_run": return result(run_recipe(clean_name(args["name"]), args.get("variables", {})))
    if name == "recipe_simulate":
        recipe_name=clean_name(args["name"])
        if recipe_name not in recipes:raise ValueError(f"Recipe not found: {recipe_name}")
        available={item["name"]:item for item in public_tools()};steps=[]
        for index,action in enumerate(recipes[recipe_name].get("actions",[]),1):
            tool=action.get("tool");arguments=substitute(action.get("arguments",{}),args.get("variables",{}));steps.append({"step":index,"tool":tool,"arguments":arguments,"available":tool in available,"risky":tool in RISKY_TOOLS})
        return result(json.dumps({"recipe":recipe_name,"will_execute":False,"valid":all(x["available"] for x in steps),"steps":steps},indent=2,ensure_ascii=False))
    if name == "recipe_delete":
        recipe_name = clean_name(args["name"])
        if recipe_name not in recipes: raise ValueError(f"Recipe not found: {recipe_name}")
        del recipes[recipe_name]; save(RECIPES, recipes); record("recipe", recipe_name, "deleted")
        return result(f"Deleted recipe: {recipe_name}")
    procedures=load(PROCEDURES,{})
    if name=="learned_procedure_list":
        items=sorted(procedures.items(),key=lambda pair:pair[1].get("last_verified",""),reverse=True)[:int(args.get("limit",50))]
        return result("\n".join(f"{key} · {item.get('success_count',1)} verified · {item.get('request','')[:120]}" for key,item in items) or "No verified procedures learned yet.")
    if name=="learned_procedure_read":
        key=str(args["id"]);item=procedures.get(key)
        if not item:raise ValueError(f"Learned procedure not found: {key}")
        return result(json.dumps({key:item},indent=2,ensure_ascii=False))
    if name=="learned_procedure_delete":
        if args.get("confirm")!="FORGET PROCEDURE":raise ValueError("confirm must be exactly FORGET PROCEDURE")
        key=str(args["id"])
        if key not in procedures:raise ValueError(f"Learned procedure not found: {key}")
        del procedures[key];save(PROCEDURES,procedures);return result(f"Forgot learned procedure {key}; no original files or recipes were changed.")
    if name=="learned_procedure_promote":
        key=str(args["id"]);item=procedures.get(key)
        if not item:raise ValueError(f"Learned procedure not found: {key}")
        promoted={"name":args["name"],"description":"Promoted from verified procedure "+key,"actions":item.get("actions",[]),"allow_risky":bool(args.get("allow_risky",False))}
        return call_tool("recipe_save",promoted)
    schedules = load(SCHEDULES, {})
    if name == "schedule_create":
        schedule_name, recipe_name = clean_name(args["name"]), clean_name(args["recipe"])
        if recipe_name not in recipes: raise ValueError(f"Recipe not found: {recipe_name}")
        if args.get("run_at"):
            run_at = datetime.fromisoformat(str(args["run_at"]))
        else: run_at = datetime.now() + timedelta(minutes=int(args.get("delay_minutes", 0)))
        schedules[schedule_name] = {"recipe": recipe_name, "next_run": run_at.isoformat(timespec="seconds"), "interval_minutes": args.get("interval_minutes"), "variables": args.get("variables", {}), "enabled": args.get("enabled", True), "status": "pending", "created": datetime.now().isoformat(timespec="seconds")}
        save(SCHEDULES, schedules); record("schedule", schedule_name, "created", schedules[schedule_name])
        return result(f"Scheduled {recipe_name} as {schedule_name} for {run_at.isoformat(timespec='minutes')}")
    if name == "schedule_list": return result(json.dumps(schedules, indent=2, ensure_ascii=False) if schedules else "No schedules configured.")
    if name == "schedule_cancel":
        schedule_name = clean_name(args["name"])
        if schedule_name not in schedules: raise ValueError(f"Schedule not found: {schedule_name}")
        del schedules[schedule_name]; save(SCHEDULES, schedules); record("schedule", schedule_name, "cancelled")
        return result(f"Cancelled schedule: {schedule_name}")
    if name == "schedule_run_due": return result(run_due())
    if name == "activity_recent":
        try: lines = ACTIVITY.read_text().splitlines()[-int(args.get("limit", 20)):]
        except OSError: lines = []
        return result("\n".join(lines) or "No automation activity yet.")
    raise ValueError(f"Unknown automation tool: {name}")


def serve():
    for raw in sys.stdin:
        message = {}
        try:
            message = json.loads(raw); request_id = message.get("id")
            if request_id is None: continue
            method = message.get("method")
            if method == "initialize": response = {"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"AI Dock Automation","version":"1.0"}}
            elif method == "tools/list": response = {"tools": TOOLS}
            elif method == "tools/call":
                params = message.get("params", {}); response = call_tool(params.get("name"), params.get("arguments", {}))
            else: raise ValueError(f"Unsupported MCP method: {method}")
            reply = {"jsonrpc":"2.0","id":request_id,"result":response}
        except Exception as error:
            reply = {"jsonrpc":"2.0","id":message.get("id"),"error":{"code":-32000,"message":str(error)}}
        print(json.dumps(reply, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--run-due", action="store_true"); parser.add_argument("--run-recipe")
    options = parser.parse_args()
    if options.run_due:
        try:
            output = run_due(); print(output)
            if output != "No scheduled recipes are due.": subprocess.run(["notify-send", "-a", "AI Dock", "AI Dock scheduled automation", output[:500]], check=False)
        except Exception as error:
            record("scheduler", "run-due", "failed", error); print(error, file=sys.stderr); raise SystemExit(1)
    elif options.run_recipe:
        try: print(run_recipe(clean_name(options.run_recipe)))
        except Exception as error: print(error, file=sys.stderr); raise SystemExit(1)
    else: serve()
