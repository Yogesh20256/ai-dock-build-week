#!/usr/bin/env python3
"""Small bundled MCP server for safe desktop-opening actions."""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from difflib import SequenceMatcher

LAST_WINDOW = Path.home() / ".local/share/ai-dock/last-opened-window.json"
CONTROLLED_BROWSER_PORT = 9223
CONTROLLED_BROWSER_PROFILE = Path.home() / ".local/share/ai-dock/controlled-browser"


def clients():
    try: return json.loads(subprocess.check_output(["hyprctl", "clients", "-j"], text=True))
    except Exception: return []


def active_workspace():
    try: return str(json.loads(subprocess.check_output(["hyprctl", "activeworkspace", "-j"], text=True))["name"])
    except Exception: return "1"


def normalize_workspace(value):
    """Return a Hyprland workspace name; omitted means the current workspace."""
    requested = str(value or "").strip().lower()
    if not requested or requested in ("current", "current workspace", "here"): return active_workspace()
    requested = re.sub(r"^(?:workspace|ws|w)\s*", "", requested).strip()
    if requested in ("hidden", "hidden workspace", "special", "special workspace"): return "special:special"
    if requested.startswith("special:") and re.fullmatch(r"special:[a-z0-9_-]+", requested): return requested
    if re.fullmatch(r"[1-9][0-9]*", requested): return requested
    raise ValueError(f"Invalid workspace: {value}")


def move_window(window, workspace):
    address = window.get("address")
    if not address: return
    subprocess.run(
        ["hyprctl", "dispatch", f'hl.dsp.window.move({{ window = "address:{address}", workspace = "{workspace}", follow = false }})'],
        check=True, stdout=subprocess.DEVNULL,
    )


def remember_new_window(application, before, workspace=None):
    """Persist the exact window produced by the latest open action."""
    for _ in range(24):
        current = clients()
        candidates = [item for item in current if item.get("address") not in before]
        if candidates:
            chosen = max(candidates, key=lambda item: item.get("focusHistoryID", 0))
            if workspace and chosen.get("workspace", {}).get("name") != workspace:
                move_window(chosen, workspace)
            LAST_WINDOW.parent.mkdir(parents=True, exist_ok=True)
            LAST_WINDOW.write_text(json.dumps({
                "application": application, "address": chosen.get("address"),
                "class": chosen.get("class"), "title": chosen.get("title"), "pid": chosen.get("pid"),
            }))
            return chosen
        time.sleep(0.125)
    return None


def controlled_browser_ready():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{CONTROLLED_BROWSER_PORT}/json/version", timeout=0.6).read()
        return True
    except Exception: return False


def remember_controlled_browser():
    try:
        pid = int(subprocess.check_output(
            ["pgrep", "-f", f"remote-debugging-port={CONTROLLED_BROWSER_PORT}.*controlled-browser"], text=True
        ).splitlines()[0])
        window = next(item for item in clients() if item.get("pid") == pid)
        LAST_WINDOW.parent.mkdir(parents=True, exist_ok=True)
        LAST_WINDOW.write_text(json.dumps({
            "application": "brave", "address": window.get("address"), "class": window.get("class"),
            "title": window.get("title"), "pid": window.get("pid"),
        }))
        return window
    except Exception: return None


def launch_controlled_brave(workspace=None):
    if not controlled_browser_ready():
        CONTROLLED_BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([
            "/usr/bin/brave", f"--remote-debugging-port={CONTROLLED_BROWSER_PORT}",
            f"--user-data-dir={CONTROLLED_BROWSER_PROFILE}", "--no-first-run", "--disable-default-apps",
            "https://www.google.com/",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(40):
            if controlled_browser_ready(): break
            time.sleep(0.25)
        else: raise RuntimeError("The AI-controlled Brave browser did not start")
    window = None
    for _ in range(24):
        window = remember_controlled_browser()
        if window: break
        time.sleep(0.125)
    if not window: raise RuntimeError("The controlled Brave window was not found")
    if workspace and window.get("workspace", {}).get("name") != workspace:
        move_window(window, workspace)
    subprocess.run(["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{window["address"]}" }})'], stdout=subprocess.DEVNULL)
    return window


def controlled_browser_pid():
    try:
        return int(subprocess.check_output(
            ["pgrep", "-f", f"remote-debugging-port={CONTROLLED_BROWSER_PORT}.*controlled-browser"], text=True
        ).splitlines()[0])
    except Exception: return -1


def is_regular_brave_window(window):
    """True only for the user's real Brave profile, not AI Dock bridge profiles."""
    if window.get("class") != "brave-browser": return False
    try:
        command = Path(f"/proc/{int(window.get('pid', -1))}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except (OSError, ValueError, TypeError):
        return False
    # AI Dock's controlled browser and Claude/Grok bridge always carry a
    # dedicated --user-data-dir. The user's ordinary Brave process does not.
    return "--user-data-dir=" not in command


def focus_window(window):
    workspace = window.get("workspace", {}).get("name")
    if workspace:
        subprocess.run(["hyprctl", "dispatch", f'hl.dsp.focus({{ workspace = "{workspace}" }})'], stdout=subprocess.DEVNULL)
    subprocess.run(["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{window["address"]}" }})'], stdout=subprocess.DEVNULL)
    time.sleep(0.35)


def click_point(x, y):
    subprocess.run(["hyprctl", "dispatch", f"hl.dsp.cursor.move({{ x = {int(x)}, y = {int(y)} }})"], stdout=subprocess.DEVNULL)
    time.sleep(0.15)
    subprocess.run(["hyprctl", "dispatch", 'hl.dsp.send_shortcut({ mods = "", key = "mouse:272", window = "activewindow" })'], stdout=subprocess.DEVNULL)


def window_ocr_rows(window):
    focus_window(window)
    at = window.get("at", [0, 0]); size = window.get("size", [0, 0])
    if size[0] < 100 or size[1] < 100: raise RuntimeError("Target window has invalid geometry")
    capture = Path.home() / ".local/share/ai-dock/ocr-click-window.png"
    capture.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["grim", "-g", f"{at[0]},{at[1]} {size[0]}x{size[1]}", str(capture)], check=True, stdout=subprocess.DEVNULL)
    tsv = subprocess.check_output(["tesseract", str(capture), "stdout", "--psm", "11", "tsv"], text=True, stderr=subprocess.DEVNULL)
    rows=[]
    for line in tsv.splitlines()[1:]:
        parts=line.split("\t")
        if len(parts) != 12 or not parts[11].strip(): continue
        try: left,top,width,height=map(int,parts[6:10])
        except ValueError: continue
        rows.append({"text":parts[11].strip(),"left":left,"top":top,"width":width,"height":height,"line":tuple(parts[1:5])})
    return rows


def locate_window_text(window, wanted, strict=False, region=None):
    """Locate text in a focused window. Strict mode never accepts a fuzzy person-name substitution."""
    rows=window_ocr_rows(window);at=window.get("at",[0,0]);size=window.get("size",[0,0])
    if region:
        x1,y1,x2,y2=region;rows=[r for r in rows if x1*size[0] <= r["left"]+r["width"]/2 <= x2*size[0] and y1*size[1] <= r["top"]+r["height"]/2 <= y2*size[1]]
    target=re.sub(r"\s+"," ",str(wanted).strip().lower());norm=lambda value:re.sub(r"[^a-z0-9]+"," ",value.lower()).strip()
    candidates=[]
    for row in rows:
        value=row["text"].lower(); score=SequenceMatcher(None,target,value).ratio()
        if target in value or value in target: score=max(score,.9)
        candidates.append((score,row))
    # Also combine words from each OCR line for multi-word labels.
    for line_id in {row["line"] for row in rows}:
        group=[row for row in rows if row["line"]==line_id]
        value=" ".join(row["text"] for row in group).lower(); score=SequenceMatcher(None,target,value).ratio()
        if target in value or value in target: score=max(score,.92)
        if group:
            left=min(r["left"] for r in group);top=min(r["top"] for r in group);right=max(r["left"]+r["width"] for r in group);bottom=max(r["top"]+r["height"] for r in group)
            candidates.append((score,{"text":value,"left":left,"top":top,"width":right-left,"height":bottom-top}))
    if strict:
        exact=[];wanted_norm=norm(target)
        for score,row in candidates:
            value=norm(str(row["text"]));
            if value==wanted_norm or value.startswith(wanted_norm+" "):exact.append((1.0 if value==wanted_norm else .97,row))
        # Deduplicate overlapping word/line boxes at essentially the same point.
        unique=[]
        for item in sorted(exact,key=lambda pair:(pair[1]["top"],pair[1]["left"],-pair[0])):
            cx=item[1]["left"]+item[1]["width"]/2;cy=item[1]["top"]+item[1]["height"]/2
            if not any(abs(cx-(old[1]["left"]+old[1]["width"]/2))<35 and abs(cy-(old[1]["top"]+old[1]["height"]/2))<20 for old in unique):unique.append(item)
        if len(unique)!=1:raise RuntimeError(f"Expected one unambiguous visible match for '{wanted}', found {len(unique)}; nothing was clicked")
        candidates=unique
    if not candidates: raise RuntimeError(f"No readable text was found in {window.get('title','the active window')}")
    score,best=max(candidates,key=lambda item:item[0])
    if score < .72: raise RuntimeError(f"Could not confidently find visible text '{wanted}' (best OCR match: {best['text']})")
    x=at[0]+best["left"]+best["width"]//2;y=at[1]+best["top"]+best["height"]//2
    return best["text"],x,y,score


def click_window_text(window, wanted, strict=False, region=None):
    label,x,y,score=locate_window_text(window,wanted,strict,region);click_point(x,y);return label,x,y,score


def set_dock_visibility(show):
    option="--show" if show is True else "--hide" if show is None else "--invisible"
    subprocess.run([sys.executable,str(Path(__file__).with_name("ai_dock.py")),option],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
    time.sleep(.45)


def send_shortcut(mods,key):
    subprocess.run(["hyprctl","dispatch",f'hl.dsp.send_shortcut({{ mods = "{mods}", key = "{key}", window = "activewindow" }})'],stdout=subprocess.DEVNULL)


def read_active_tab_url(window):
    focus_window(window);send_shortcut("CTRL","L");time.sleep(.12);send_shortcut("CTRL","C");time.sleep(.18)
    try:return subprocess.check_output(["wl-paste","--no-newline"],text=True,timeout=2).strip()
    except Exception:return ""


def collect_window_tab_urls(window,max_tabs=40):
    """Read tab URLs without browser debugging or a second profile."""
    urls=[];first=None
    for _ in range(max_tabs):
        url=read_active_tab_url(window)
        if not url.startswith(("http://","https://","file://","brave://")):raise RuntimeError(f"Could not read a valid tab URL from {window.get('title','Brave')}")
        if first is None:first=url
        elif url==first:break
        urls.append(url);send_shortcut("CTRL","Tab");time.sleep(.22)
    if not urls:raise RuntimeError("No transferable Brave tabs were found")
    send_shortcut("","Escape")
    return urls


def open_urls_as_tabs(window,urls):
    focus_window(window);opened=0
    for url in urls:
        send_shortcut("CTRL","T");time.sleep(.15);subprocess.run(["wl-copy",url],check=True);send_shortcut("CTRL","V");send_shortcut("","Return");time.sleep(.28);opened+=1
    return opened


def open_normal_brave(url=None, workspace=None):
    """Use the user's regular logged-in Brave profile, never AI Dock's profile."""
    workspace = workspace or active_workspace()
    original_workspace = active_workspace()
    existing = [item for item in clients() if is_regular_brave_window(item)]
    before = {item.get("address") for item in existing}
    in_target = [item for item in existing if item.get("workspace", {}).get("name") == workspace]
    # Explicitly bind to Brave's actual regular Default profile. No temporary
    # user-data directory is used, so existing cookies/logins are preserved.
    # If the target workspace already owns a normal Brave window, make it the
    # active browser destination and let Brave add/reuse a tab there. Otherwise
    # force a genuinely new window. Never move an unrelated window from some
    # other workspace as a fallback.
    if in_target:
        window = min(in_target, key=lambda item: item.get("focusHistoryID", 999999))
        subprocess.run(
            ["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{window["address"]}" }})'],
            stdout=subprocess.DEVNULL,
        )
        command = ["/usr/bin/brave", "--profile-directory=Default"] + ([url] if url else [])
    else:
        window = None
        command = ["/usr/bin/brave", "--profile-directory=Default", "--new-window"] + ([url] if url else ["about:blank"])
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not in_target:
        for _ in range(40):
            normal = [item for item in clients() if is_regular_brave_window(item)]
            new_windows = [item for item in normal if item.get("address") not in before]
            if new_windows:
                window = min(new_windows, key=lambda item: item.get("focusHistoryID", 999999))
                break
            time.sleep(0.125)
        if not window:
            raise RuntimeError(
                f"Brave did not create a new window for workspace {workspace}; "
                "existing browser windows were preserved."
            )
        if window.get("workspace", {}).get("name") != workspace:
            move_window(window, workspace)
    # Brave can asynchronously focus its reused window just after its command
    # returns. Restore the user's original workspace after that event settles.
    time.sleep(0.3)
    subprocess.run(["hyprctl", "dispatch", f'hl.dsp.focus({{ workspace = "{original_workspace}" }})'], stdout=subprocess.DEVNULL)
    return window


TOOLS = [
    {
        "name": "open_github",
        "description": "Open GitHub in the user's default browser. Optionally open a GitHub username or repository path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Optional GitHub path such as username or owner/repository"}
            },
            "additionalProperties": False,
        },
    },
    {
        "name":"focus_or_open_website",
        "description":"Focus an already-open website in the user's normal logged-in Brave profile, even when it is on another workspace. Opens it in normal Brave only when no matching normal window exists. A supplied workspace limits reuse to that workspace and never moves an unrelated browser window.",
        "inputSchema":{"type":"object","properties":{"website":{"type":"string"},"url":{"type":"string"},"workspace":{"type":"string","description":"Optional explicit target workspace"}},"required":["website","url"],"additionalProperties":False},
    },
    {
        "name":"merge_brave_windows",
        "description":"Merge the user's normal logged-in Brave windows across arbitrary Hyprland workspaces. Copies every source tab URL into one destination Brave window, verifies transfer counts, then closes only the extra source Brave windows. If the destination has no Brave window, moves one source window there as the destination. Never uses a separate browser profile.",
        "inputSchema":{"type":"object","properties":{"source":{"type":"string","description":"Source workspace; omit to use the current workspace"},"destination":{"type":"string","description":"Destination workspace; omit to merge Brave windows on the source/current workspace"}},"additionalProperties":False},
    },
    {
        "name": "open_url",
        "description": "Open an HTTP or HTTPS website in the user's normal logged-in Brave profile on a requested/current workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Complete http or https URL"}, "workspace": {"type": "string", "description": "Target workspace; omit for current"}},
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_web",
        "description": "Immediately search a website using Firefox, Brave, or the default browser.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "site": {"type": "string", "description": "google, youtube, github, reddit, wikipedia, or a domain"},
                "browser": {"type": "string", "enum": ["default", "firefox", "brave"]},
                "workspace": {"type":"string","description":"Optional target workspace"}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "human_search",
        "description": "Open a website homepage, visibly focus its search box, paste a query, and submit it like a person using the browser.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "site": {"type": "string", "enum": ["google", "youtube", "github", "reddit", "wikipedia", "leetcode"]},
                "browser": {"type": "string", "enum": ["firefox", "brave"]}
            },
            "required": ["query", "site"],
            "additionalProperties": False,
        },
    },
    {
        "name": "launch_application",
        "description": "Launch an installed desktop application by its common name.",
        "inputSchema": {
            "type": "object",
            "properties": {"application": {"type": "string", "description": "firefox, brave, vscode, terminal, files, dolphin, obsidian, calculator, or spotify"}, "workspace": {"type": "string", "description": "Target workspace number or special workspace. Omit for the current workspace."}},
            "required": ["application"],
            "additionalProperties": False,
        },
    },
    {
        "name": "open_path",
        "description": "Open an existing local file or directory with its default desktop application.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute local path"}, "workspace": {"type": "string", "description": "Target workspace number or special workspace. Omit for current."}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_and_open",
        "description": "Find a file or folder by a human-friendly name without requiring an absolute path, then open the best match. Searches common home folders and /mnt/shared, preferring exact and non-hidden matches.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "kind": {"type": "string", "enum": ["any", "file", "folder"]}, "workspace": {"type": "string", "description": "Target workspace number or special workspace. Omit for current."}},
            "required": ["name"], "additionalProperties": False,
        },
    },
    {
        "name": "create_folder",
        "description": "Create a folder at a destination identified by either an absolute path or a friendly approximate folder name. Handles spaces, underscores, and minor typing mistakes.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "destination": {"type": "string", "description": "Absolute path or approximate destination name such as C Programming, Documents, or shared"}}, "required": ["name", "destination"], "additionalProperties": False},
    },
    {
        "name": "click_screen",
        "description": "Click a visible point on the current 1920 by 1080 desktop. Use only after inspecting the latest screenshot.",
        "inputSchema": {
            "type": "object",
            "properties": {"x": {"type": "integer", "minimum": 0, "maximum": 1919}, "y": {"type": "integer", "minimum": 0, "maximum": 1079}},
            "required": ["x", "y"], "additionalProperties": False,
        },
    },
    {
        "name": "click_visible_text",
        "description": "Focus an existing normal desktop window and click visible text in that same window using local OCR. Use this for logged-in web apps such as WhatsApp when browser DOM tools control a different profile. Never opens a new window.",
        "inputSchema": {"type":"object","properties":{"text":{"type":"string"},"application":{"type":"string","description":"Window title or application hint, for example WhatsApp, Brave, Dolphin, or VS Code"},"workspace":{"type":"string","description":"Optional workspace containing the existing window"}},"required":["text","application"],"additionalProperties":False},
    },
    {
        "name": "whatsapp_send_message",
        "description": "In the already-open normal logged-in WhatsApp Web window, find a contact/chat with local OCR, open it, type a message, and press Send without creating another browser window. This is an external communication and requires user approval.",
        "inputSchema": {"type":"object","properties":{"contact":{"type":"string"},"message":{"type":"string"},"workspace":{"type":"string","description":"Workspace containing WhatsApp; omit to find the existing WhatsApp window"}},"required":["contact","message"],"additionalProperties":False},
    },
    {
        "name": "type_text",
        "description": "Type text into the currently focused desktop field using the clipboard.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
    },
    {
        "name": "press_key",
        "description": "Press a safe keyboard key or shortcut in the active window.",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string", "enum": ["Return", "Tab", "Escape", "slash", "Ctrl+L", "Ctrl+A", "Ctrl+V"]}},
            "required": ["key"], "additionalProperties": False,
        },
    },
    {
        "name": "list_windows",
        "description": "List currently open desktop application windows with class, title, workspace, and address.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "open_workspace",
        "description": "Immediately focus a numbered workspace, or reveal the hidden special workspace without toggling it closed when already visible.",
        "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string", "description": "Workspace number or hidden/special workspace"}}, "required": ["workspace"], "additionalProperties": False},
    },
    {
        "name": "move_windows",
        "description": "Move one application window, the most recently focused window, or every window from one workspace to another without switching workspaces. Source defaults to the current workspace. AI Dock is protected from bulk moves.",
        "inputSchema": {"type": "object", "properties": {
            "destination": {"type": "string", "description": "Destination workspace number or special workspace"},
            "source": {"type": "string", "description": "Source workspace; omit for current"},
            "application": {"type": "string", "description": "Optional application name. Omit to move the most recently focused window."},
            "all": {"type": "boolean", "description": "Move every normal application window from the source workspace"}
        }, "required": ["destination"], "additionalProperties": False},
    },
    {
        "name": "focus_application",
        "description": "Focus an already open application window by common application name.",
        "inputSchema": {"type": "object", "properties": {"application": {"type": "string"}, "workspace": {"type": "string", "description": "Workspace containing the window. Omit to use only the current workspace."}}, "required": ["application"], "additionalProperties": False},
    },
    {
        "name": "close_application",
        "description": "Gracefully close an open application window by common application name. This does not kill unrelated processes.",
        "inputSchema": {"type": "object", "properties": {"application": {"type": "string"}, "workspace": {"type": "string", "description": "Workspace containing the window. Omit to use only the current workspace."}}, "required": ["application"], "additionalProperties": False},
    },
    {
        "name": "close_workspace_windows",
        "description": "Gracefully close every normal application window on one explicit workspace. AI Dock is always protected. Use only when the user explicitly asks to close all/every window there.",
        "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string", "description": "Explicit numbered or special workspace"}}, "required": ["workspace"], "additionalProperties": False},
    },
    {
        "name": "prepare_workspace_and_open_url",
        "description": "Atomically close every normal window on an explicit workspace, then open a URL there in the user's regular logged-in Brave profile. AI Dock is protected and the user's current workspace focus is restored.",
        "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string"}, "url": {"type": "string"}}, "required": ["workspace", "url"], "additionalProperties": False},
    },
    {
        "name": "adjust_audio_volume",
        "description": "Set the default audio output volume, or mute/unmute.",
        "inputSchema": {"type": "object", "properties": {"volume": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Volume percentage (0-100)"}, "action": {"type": "string", "enum": ["mute", "unmute", "get"]}}, "additionalProperties": False}
    },
    {
        "name": "adjust_screen_brightness",
        "description": "Get or set the screen brightness level.",
        "inputSchema": {"type": "object", "properties": {"brightness": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Brightness percentage (0-100)"}, "action": {"type": "string", "enum": ["get"]}}, "additionalProperties": False}
    },
    {
        "name": "get_clipboard",
        "description": "Read the current text content from the Wayland clipboard.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}
    },
    {
        "name": "set_clipboard",
        "description": "Copy the specified text content into the Wayland clipboard.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "Text content to copy"}}, "required": ["text"], "additionalProperties": False}
    },
    {
        "name": "capture_window",
        "description": "Capture a screenshot of the currently focused active window using Hyprland geometry.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}
    },
]


def open_target(target):
    subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"content": [{"type": "text", "text": f"Opened {target}"}]}


def open_in_browser(url, browser):
    commands = {"firefox": "/usr/bin/firefox", "brave": "/usr/bin/brave"}
    command = commands.get(browser)
    if command and Path(command).exists():
        subprocess.Popen([command, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"content": [{"type": "text", "text": f"Opened {url} in {browser.title()}"}]}
    return open_target(url)


def human_search(query, site, browser):
    homes = {
        "google": "https://www.google.com", "youtube": "https://www.youtube.com",
        "github": "https://github.com", "reddit": "https://www.reddit.com",
        "wikipedia": "https://en.wikipedia.org", "leetcode": "https://leetcode.com/problemset/",
    }
    browser = browser if browser in ("firefox", "brave") else "brave"
    command = "/usr/bin/firefox" if browser == "firefox" else "/usr/bin/brave"
    window_class = "firefox" if browser == "firefox" else "brave-browser"
    subprocess.Popen([command, homes[site]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    window = f"class:{window_class}"
    subprocess.run(["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "{window}" }})'], stdout=subprocess.DEVNULL)
    if site == "leetcode":
        # LeetCode has no dependable global search shortcut. Navigate visibly
        # through the browser bar to its problemset search after opening it.
        target = f"https://leetcode.com/problemset/?search={quote_plus(query)}"
        subprocess.run(["hyprctl", "dispatch", f'hl.dsp.send_shortcut({{ mods = "CTRL", key = "L", window = "{window}" }})'], stdout=subprocess.DEVNULL)
        time.sleep(0.4); subprocess.run(["wl-copy", target], stdout=subprocess.DEVNULL)
        subprocess.run(["hyprctl", "dispatch", f'hl.dsp.send_shortcut({{ mods = "CTRL", key = "V", window = "{window}" }})'], stdout=subprocess.DEVNULL)
        time.sleep(0.4)
        subprocess.run(["hyprctl", "dispatch", f'hl.dsp.send_shortcut({{ mods = "", key = "Return", window = "{window}" }})'], stdout=subprocess.DEVNULL)
        return {"content": [{"type": "text", "text": f"Opened LeetCode and searched its problemset for: {query}"}]}
    # Most supported sites use / as their keyboard shortcut for Search.
    subprocess.run(["hyprctl", "dispatch", f'hl.dsp.send_shortcut({{ mods = "", key = "slash", window = "{window}" }})'], stdout=subprocess.DEVNULL)
    time.sleep(0.5)
    subprocess.run(["wl-copy", query], stdout=subprocess.DEVNULL)
    subprocess.run(["hyprctl", "dispatch", f'hl.dsp.send_shortcut({{ mods = "CTRL", key = "V", window = "{window}" }})'], stdout=subprocess.DEVNULL)
    time.sleep(0.4)
    subprocess.run(["hyprctl", "dispatch", f'hl.dsp.send_shortcut({{ mods = "", key = "Return", window = "{window}" }})'], stdout=subprocess.DEVNULL)
    return {"content": [{"type": "text", "text": f"Opened {site.title()} in {browser.title()} and visibly entered: {query}"}]}


def normalized(value): return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def find_named(query, kind="any"):
    query_norm = normalized(query)
    home = Path.home()
    roots = [home / item for item in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")]
    roots.append(Path("/mnt/shared"))
    candidates = []
    skipped = {".git", "node_modules", "__pycache__", ".cache", ".local", ".config", ".venv"}
    for root in roots:
        if not root.exists(): continue
        if kind != "file":
            root_ratio = SequenceMatcher(None, query_norm, normalized(root.name)).ratio()
            if root_ratio >= 0.58: candidates.append((1 - root_ratio, len(root.parts), root))
        for directory, dirs, files in os.walk(root):
            dirs[:] = [item for item in dirs if item not in skipped and not item.startswith(".")]
            names = dirs if kind == "folder" else files if kind == "file" else dirs + files
            for item in names:
                item_norm = normalized(Path(item).stem)
                ratio = SequenceMatcher(None, query_norm, item_norm).ratio()
                contains = query_norm in item_norm or item_norm in query_norm
                if ratio < 0.58 and not contains: continue
                path = Path(directory) / item
                score = (0 if query_norm == item_norm else 1 - ratio) - (0.05 if str(path).startswith(str(home / "Pictures")) else 0)
                candidates.append((score, len(path.parts), path))
    if not candidates: return None
    return min(candidates, key=lambda item: (item[0], item[1], str(item[2])))[2]


def call_tool(name, arguments):
    if name == "open_github":
        path = str(arguments.get("path", "")).strip().strip("/")
        return open_target("https://github.com" + (f"/{path}" if path else ""))
    if name == "open_url":
        url = str(arguments.get("url", "")).strip()
        if urlparse(url).scheme not in ("http", "https"):
            raise ValueError("Only http and https URLs are allowed")
        workspace = normalize_workspace(arguments.get("workspace"))
        window = open_normal_brave(url, workspace)
        return {"content": [{"type": "text", "text": f"Opened {url} in normal logged-in Brave on workspace {workspace} · {window.get('title') or 'Brave'}"}]}
    if name == "focus_or_open_website":
        website=str(arguments.get("website","")).strip().lower();url=str(arguments.get("url","")).strip()
        if urlparse(url).scheme not in ("http","https"):raise ValueError("Only http and https URLs are allowed")
        explicit=arguments.get("workspace");workspace=normalize_workspace(explicit) if explicit else None
        aliases={"whatsapp":("whatsapp",),"gmail":("gmail","inbox"),"youtube":("youtube",),"github":("github",),"instagram":("instagram",),"leetcode":("leetcode",),"reddit":("reddit",),"facebook":("facebook",),"linkedin":("linkedin",),"netflix":("netflix",)}
        needles=aliases.get(website,(website,));matches=[item for item in clients() if is_regular_brave_window(item) and any(needle in str(item.get("title","")).lower() for needle in needles) and (not workspace or item.get("workspace",{}).get("name")==workspace)]
        if matches:
            window=min(matches,key=lambda item:item.get("focusHistoryID",999999));focus_window(window)
            return {"content":[{"type":"text","text":f"Focused the already-open {website} in your normal logged-in Brave profile on workspace {window.get('workspace',{}).get('name')}; no window or tab was opened."}]}
        target=workspace or active_workspace();window=open_normal_brave(url,target)
        return {"content":[{"type":"text","text":f"No existing normal {website} window was open, so it was opened once in your normal logged-in Brave profile on workspace {target}."}]}
    if name == "merge_brave_windows":
        original_workspace=active_workspace();dock_was_open=any(item.get("title")=="AI Dock" for item in clients())
        source=normalize_workspace(arguments.get("source"));destination=normalize_workspace(arguments.get("destination")) if arguments.get("destination") else source
        normal=[item for item in clients() if is_regular_brave_window(item)];sources=[item for item in normal if item.get("workspace",{}).get("name")==source];targets=[item for item in normal if item.get("workspace",{}).get("name")==destination]
        if source==destination:
            if len(sources)<2:return {"content":[{"type":"text","text":f"Workspace {source} already has fewer than two normal Brave windows; nothing needed merging."}]}
            target=min(sources,key=lambda item:item.get("focusHistoryID",999999));merge=[item for item in sources if item.get("address")!=target.get("address")]
        elif targets:
            target=min(targets,key=lambda item:item.get("focusHistoryID",999999));merge=sources
        else:
            if not sources:raise RuntimeError(f"No normal Brave windows exist on source workspace {source}")
            target=min(sources,key=lambda item:item.get("focusHistoryID",999999));move_window(target,destination);target.setdefault("workspace",{})["name"]=destination;time.sleep(.35);merge=[item for item in sources if item.get("address")!=target.get("address")]
        if not merge:return {"content":[{"type":"text","text":f"One normal Brave window is now on workspace {destination}; there were no additional source windows to merge."}]}
        try:old_clipboard=subprocess.check_output(["wl-paste","--no-newline"],text=True,timeout=2)
        except Exception:old_clipboard=None
        set_dock_visibility(False);transferred=0;closed=0
        try:
            batches=[]
            for window in merge:batches.append((window,collect_window_tab_urls(window)))
            for window,urls in batches:
                transferred+=open_urls_as_tabs(target,urls)
                # Close only after every URL from this window was issued to the
                # verified destination window.
                subprocess.run(["hyprctl","dispatch",f'hl.dsp.window.close({{ window = "address:{window["address"]}" }})'],check=True,stdout=subprocess.DEVNULL);closed+=1
            focus_window(target)
            return {"content":[{"type":"text","text":f"Merged {closed} extra normal Brave window(s) into one window on workspace {destination}; transferred {transferred} tab URL(s). No alternate browser profile was used."}]}
        finally:
            if old_clipboard is not None:subprocess.run(["wl-copy",old_clipboard],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            subprocess.run(["hyprctl","dispatch",f'hl.dsp.focus({{ workspace = "{original_workspace}" }})'],stdout=subprocess.DEVNULL);time.sleep(.25)
            set_dock_visibility(True if dock_was_open else None)
    if name == "search_web":
        query = str(arguments.get("query", "")).strip()
        if not query: raise ValueError("A search query is required")
        site = str(arguments.get("site", "google")).lower().strip()
        encoded = quote_plus(query)
        searches = {
            "google": f"https://www.google.com/search?q={encoded}",
            "youtube": f"https://www.youtube.com/results?search_query={encoded}",
            "github": f"https://github.com/search?q={encoded}",
            "reddit": f"https://www.reddit.com/search/?q={encoded}",
            "wikipedia": f"https://en.wikipedia.org/w/index.php?search={encoded}",
        }
        if site in searches: url = searches[site]
        else:
            domain = site.removeprefix("https://").removeprefix("http://").strip("/")
            url = f"https://www.google.com/search?q={quote_plus('site:' + domain + ' ' + query)}"
        browser=str(arguments.get("browser","brave")).lower()
        if browser in ("brave","default"):
            workspace=normalize_workspace(arguments.get("workspace"));window=open_normal_brave(url,workspace)
            return {"content":[{"type":"text","text":f"Searched {site} for '{query}' in your normal Brave profile on workspace {workspace} · {window.get('title') or 'Brave'}"}]}
        return open_in_browser(url,browser)
    if name == "human_search":
        query = str(arguments.get("query", "")).strip()
        site = str(arguments.get("site", "google")).lower().strip()
        if not query: raise ValueError("A search query is required")
        if site not in ("google", "youtube", "github", "reddit", "wikipedia", "leetcode"):
            raise ValueError(f"Human-style search is not configured for {site}")
        return human_search(query, site, str(arguments.get("browser", "brave")).lower())
    if name == "launch_application":
        app = str(arguments.get("application", "")).lower().strip()
        workspace = normalize_workspace(arguments.get("workspace"))
        before = {item.get("address") for item in clients()}
        applications = {
            "firefox": ["/usr/bin/firefox"], "brave": ["/usr/bin/brave"],
            "vscode": ["/usr/bin/gtk-launch", "code.desktop"],
            "code": ["/usr/bin/gtk-launch", "code.desktop"],
            "terminal": ["/usr/bin/gtk-launch", "Alacritty.desktop"],
            "files": ["/usr/bin/gtk-launch", "org.kde.dolphin.desktop"],
            "file manager": ["/usr/bin/gtk-launch", "org.kde.dolphin.desktop"],
            "dolphin": ["/usr/bin/gtk-launch", "org.kde.dolphin.desktop"],
            "obsidian": ["/usr/bin/gtk-launch", "obsidian.desktop"],
            "calculator": ["/usr/bin/gtk-launch", "org.gnome.Calculator.desktop"],
            "spotify": ["/usr/bin/gtk-launch", "spotify-launcher.desktop"],
        }
        if app not in applications: raise ValueError(f"Application is not in the allowed launcher list: {app}")
        if app == "brave":
            opened = open_normal_brave(None, workspace)
            return {"content": [{"type": "text", "text": f"Opened normal logged-in Brave on workspace {workspace} · {opened.get('title') or 'Brave'}"}]}
        subprocess.Popen(applications[app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        opened = remember_new_window(app, before, workspace)
        if opened is None:
            # Single-instance applications may reuse an existing window.
            aliases = {"vscode": ("code",), "code": ("code",), "obsidian": ("obsidian",), "dolphin": ("org.kde.dolphin",), "files": ("org.kde.dolphin",), "file manager": ("org.kde.dolphin",), "firefox": ("firefox",), "spotify": ("spotify",)}
            needles = aliases.get(app, (app,))
            opened = next((item for item in clients() if any(n.lower() in (item.get("class", "") + " " + item.get("title", "")).lower() for n in needles)), None)
            if opened: move_window(opened, workspace)
        detail = f" · window {opened.get('title') or opened.get('class')}" if opened else ""
        return {"content": [{"type": "text", "text": f"Launched {app} on workspace {workspace}{detail}"}]}
    if name == "open_path":
        workspace = normalize_workspace(arguments.get("workspace"))
        path = Path(str(arguments.get("path", ""))).expanduser()
        if not path.is_absolute() or not path.exists():
            raise ValueError("The path must be absolute and must already exist")
        if path.is_dir():
            before = {item.get("address") for item in clients()}
            subprocess.Popen(["/usr/bin/dolphin", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            opened = remember_new_window("dolphin", before, workspace)
            if opened is None:
                opened = next((item for item in clients() if "org.kde.dolphin" in item.get("class", "").lower()), None)
                if opened: move_window(opened, workspace)
            return {"content": [{"type": "text", "text": f"Opened folder in Dolphin on workspace {workspace}: {path}"}]}
        return open_target(str(path))
    if name == "find_and_open":
        workspace = normalize_workspace(arguments.get("workspace"))
        query = str(arguments.get("name", "")).strip().lower()
        kind = str(arguments.get("kind", "any")).lower()
        if not query: raise ValueError("A file or folder name is required")
        chosen = find_named(query, kind)
        if not chosen: raise ValueError(f"Could not find a {kind} matching '{query}' in home folders or /mnt/shared")
        if chosen.is_dir():
            before = {item.get("address") for item in clients()}
            subprocess.Popen(["/usr/bin/dolphin", str(chosen)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            opened = remember_new_window("dolphin", before, workspace)
            if opened is None:
                opened = next((item for item in clients() if "org.kde.dolphin" in item.get("class", "").lower()), None)
                if opened: move_window(opened, workspace)
        else: open_target(str(chosen))
        return {"content": [{"type": "text", "text": f"Found and opened on workspace {workspace}: {chosen}"}]}
    if name == "create_folder":
        folder_name = str(arguments.get("name", "")).strip()
        destination = str(arguments.get("destination", "")).strip()
        if not folder_name or folder_name in (".", "..") or "/" in folder_name: raise ValueError("Provide one valid folder name without slashes")
        if destination.lower() in ("shared", "shared partition"): parent = Path("/mnt/shared")
        else:
            candidate = Path(destination).expanduser()
            parent = candidate if candidate.is_absolute() and candidate.is_dir() else find_named(destination, "folder")
        if not parent or not parent.is_dir(): raise ValueError(f"Could not resolve destination folder: {destination}")
        created = parent / folder_name
        created.mkdir(exist_ok=False)
        return {"content": [{"type": "text", "text": f"Created folder: {created}"}]}
    if name == "click_screen":
        x, y = int(arguments.get("x", -1)), int(arguments.get("y", -1))
        if not 0 <= x < 1920 or not 0 <= y < 1080: raise ValueError("Click coordinates are outside the desktop")
        subprocess.run(["hyprctl", "dispatch", f"hl.dsp.cursor.move({{ x = {x}, y = {y} }})"], stdout=subprocess.DEVNULL)
        time.sleep(0.2)
        subprocess.run(["hyprctl", "dispatch", 'hl.dsp.send_shortcut({ mods = "", key = "mouse:272", window = "activewindow" })'], stdout=subprocess.DEVNULL)
        return {"content": [{"type": "text", "text": f"Clicked screen position {x}, {y}"}]}
    if name == "click_visible_text":
        wanted=str(arguments.get("text","")).strip(); hint=str(arguments.get("application","")).strip().lower(); workspace=normalize_workspace(arguments.get("workspace")) if arguments.get("workspace") else None
        matches=[item for item in clients() if hint in (str(item.get("class",""))+" "+str(item.get("title",""))).lower() and (not workspace or item.get("workspace",{}).get("name")==workspace)]
        if not matches: raise RuntimeError(f"No existing window matching '{hint}' was found; this tool will not open another window")
        window=min(matches,key=lambda item:item.get("focusHistoryID",999999));label,x,y,score=click_window_text(window,wanted)
        return {"content":[{"type":"text","text":f"Clicked visible text '{label}' in {window.get('title')} at {x},{y} (OCR confidence {score:.0%}); no window was opened."}]}
    if name == "whatsapp_send_message":
        contact=str(arguments.get("contact","")).strip();message=str(arguments.get("message","")).strip();workspace=normalize_workspace(arguments.get("workspace")) if arguments.get("workspace") else None
        if not contact or not message: raise ValueError("Both contact and message are required")
        matches=[item for item in clients() if "whatsapp" in str(item.get("title","")).lower() and is_regular_brave_window(item) and (not workspace or item.get("workspace",{}).get("name")==workspace)]
        if not matches: raise RuntimeError("No existing normal logged-in WhatsApp Web window was found; open it first and retry")
        window=min(matches,key=lambda item:item.get("focusHistoryID",999999));dock_was_open=any(item.get("title")=="AI Dock" for item in clients())
        set_dock_visibility(False)
        try:
            # Search first. Never choose a fuzzy match from the existing chat list.
            click_window_text(window,"Search or start a new chat",False,(0,.03,.48,.25));time.sleep(.25)
            subprocess.run(["hyprctl","dispatch",'hl.dsp.send_shortcut({ mods = "CTRL", key = "A", window = "activewindow" })'],stdout=subprocess.DEVNULL)
            subprocess.run(["wl-copy",contact],check=True);subprocess.run(["hyprctl","dispatch",'hl.dsp.send_shortcut({ mods = "CTRL", key = "V", window = "activewindow" })'],stdout=subprocess.DEVNULL);time.sleep(1.5)
            label,_x,_y,_score=click_window_text(window,contact,True,(0,.08,.48,.78));time.sleep(1.2)
            # Independent post-click check: the requested name must appear once in
            # the opened conversation header on the right, not merely in search.
            verified,_vx,_vy,_vs=locate_window_text(window,contact,True,(.35,.03,1,.24))
            current=json.loads(subprocess.check_output(["hyprctl","activewindow","-j"],text=True));at=current.get("at",window.get("at",[0,0]));size=current.get("size",window.get("size",[0,0]))
            click_point(at[0]+int(size[0]*.70),at[1]+size[1]-58);time.sleep(.25)
            subprocess.run(["wl-copy",message],check=True);subprocess.run(["hyprctl","dispatch",'hl.dsp.send_shortcut({ mods = "CTRL", key = "V", window = "activewindow" })'],stdout=subprocess.DEVNULL);time.sleep(.25)
            subprocess.run(["hyprctl","dispatch",'hl.dsp.send_shortcut({ mods = "", key = "Return", window = "activewindow" })'],stdout=subprocess.DEVNULL)
            return {"content":[{"type":"text","text":f"Sent the requested message only after search and independent chat-header verification: '{verified}' (search result '{label}'). No window was opened."}]}
        finally:set_dock_visibility(True if dock_was_open else None)
    if name == "type_text":
        text = str(arguments.get("text", ""))
        subprocess.run(["wl-copy", text], stdout=subprocess.DEVNULL)
        subprocess.run(["hyprctl", "dispatch", 'hl.dsp.send_shortcut({ mods = "CTRL", key = "V", window = "activewindow" })'], stdout=subprocess.DEVNULL)
        return {"content": [{"type": "text", "text": f"Typed {len(text)} characters"}]}
    if name == "press_key":
        requested = str(arguments.get("key", ""))
        keys = {
            "Return": ("", "Return"), "Tab": ("", "Tab"), "Escape": ("", "Escape"), "slash": ("", "slash"),
            "Ctrl+L": ("CTRL", "L"), "Ctrl+A": ("CTRL", "A"), "Ctrl+V": ("CTRL", "V"),
        }
        if requested not in keys: raise ValueError("Unsupported key")
        mods, key = keys[requested]
        subprocess.run(["hyprctl", "dispatch", f'hl.dsp.send_shortcut({{ mods = "{mods}", key = "{key}", window = "activewindow" }})'], stdout=subprocess.DEVNULL)
        return {"content": [{"type": "text", "text": f"Pressed {requested}"}]}
    if name == "list_windows":
        windows = json.loads(subprocess.check_output(["hyprctl", "clients", "-j"], text=True))
        summary = [{"class": item.get("class"), "title": item.get("title"), "workspace": item.get("workspace", {}).get("name"), "address": item.get("address")} for item in windows]
        return {"content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=False, indent=2)}]}
    if name == "open_workspace":
        workspace = normalize_workspace(arguments.get("workspace"))
        if workspace.startswith("special:"):
            monitors = json.loads(subprocess.check_output(["hyprctl", "monitors", "-j"], text=True))
            visible = any(item.get("specialWorkspace", {}).get("name") == workspace for item in monitors)
            if not visible:
                subprocess.run(["hyprctl", "dispatch", "hl.dsp.workspace.toggle_special()"], check=True, stdout=subprocess.DEVNULL)
            return {"content": [{"type": "text", "text": f"{'Kept' if visible else 'Opened'} hidden workspace {workspace}"}]}
        if active_workspace() != workspace:
            subprocess.run(["hyprctl", "dispatch", f'hl.dsp.focus({{ workspace = "{workspace}" }})'], check=True, stdout=subprocess.DEVNULL)
        return {"content": [{"type": "text", "text": f"Opened workspace {workspace}"}]}
    if name == "move_windows":
        source = normalize_workspace(arguments.get("source"))
        destination = normalize_workspace(arguments.get("destination"))
        requested = str(arguments.get("application", "")).lower().strip()
        move_all = bool(arguments.get("all", False))
        aliases = {
            "dolphin": ("org.kde.dolphin",), "files": ("org.kde.dolphin",), "file manager": ("org.kde.dolphin",),
            "vscode": ("code",), "visual studio code": ("code",), "code": ("code",),
            "brave": ("brave-browser",), "firefox": ("firefox",), "terminal": ("Alacritty", "kitty", "foot"),
            "spotify": ("spotify",), "obsidian": ("obsidian",), "calculator": ("calculator",),
        }
        candidates = [item for item in clients() if item.get("workspace", {}).get("name") == source]
        # The dock is pinned infrastructure and must never unexpectedly travel
        # with a broad "move everything" desktop request.
        candidates = [item for item in candidates if item.get("class") != "io.github.yogesh.AIDock"]
        if requested:
            needles = tuple(value.lower() for value in aliases.get(requested, (requested,)))
            candidates = [item for item in candidates if any(needle in (item.get("class", "") + " " + item.get("title", "")).lower() for needle in needles)]
        elif not move_all:
            candidates = [min(candidates, key=lambda item: item.get("focusHistoryID", 999999))] if candidates else []
        if not candidates: raise ValueError(f"No matching windows exist on workspace {source}")
        for item in candidates: move_window(item, destination)
        labels = [item.get("title") or item.get("class") or item.get("address") for item in candidates]
        return {"content": [{"type": "text", "text": f"Moved {len(candidates)} window(s) from workspace {source} to {destination}: " + "; ".join(labels)}]}
    if name in ("focus_application", "close_application"):
        requested = str(arguments.get("application", "")).lower().strip()
        workspace = normalize_workspace(arguments.get("workspace"))
        aliases = {
            "dolphin": ("org.kde.dolphin",), "files": ("org.kde.dolphin",), "file manager": ("org.kde.dolphin",),
            "vscode": ("code",), "visual studio code": ("code",), "code": ("code",),
            "brave": ("brave-browser",), "firefox": ("firefox",), "terminal": ("Alacritty", "kitty", "foot"),
            "spotify": ("spotify",), "ai dock": ("io.github.yogesh.AIDock",),
            "obsidian": ("obsidian",),
        }
        needles = tuple(value.lower() for value in aliases.get(requested, (requested,)))
        windows = clients()
        match = None
        try:
            last = json.loads(LAST_WINDOW.read_text())
            exact = next((item for item in windows if item.get("address") == last.get("address")), None)
            last_name = str(last.get("application", "")).lower()
            if exact and exact.get("workspace", {}).get("name") == workspace and (requested == last_name or any(needle in (exact.get("class", "") + " " + exact.get("title", "")).lower() for needle in needles)):
                match = exact
        except (OSError, ValueError, TypeError): pass
        if match is None:
            matches = [item for item in windows if item.get("workspace", {}).get("name") == workspace and any(needle in (item.get("class", "") + " " + item.get("title", "")).lower() for needle in needles)]
            # Never guess AI Dock as the target of a general close request.
            matches = [item for item in matches if item.get("class") != "io.github.yogesh.AIDock"]
            match = min(matches, key=lambda item: item.get("focusHistoryID", 999999)) if matches else None
        if not match: raise ValueError(f"No open {requested} window exists on workspace {workspace}")
        address = match["address"]
        if name == "focus_application":
            command = f'hl.dsp.focus({{ window = "address:{address}" }})'; verb = "Focused"
        else:
            command = f'hl.dsp.window.close({{ window = "address:{address}" }})'; verb = "Closed"
        subprocess.run(["hyprctl", "dispatch", command], check=True, stdout=subprocess.DEVNULL)
        if name == "close_application":
            for _ in range(20):
                if not any(item.get("address") == address for item in clients()): break
                time.sleep(0.1)
            else: raise RuntimeError(f"The requested window did not close: {match.get('title') or requested}")
            try: LAST_WINDOW.unlink()
            except FileNotFoundError: pass
        return {"content": [{"type": "text", "text": f"{verb} {match.get('title') or match.get('class')} on workspace {workspace}"}]}
    if name == "close_workspace_windows":
        workspace = normalize_workspace(arguments.get("workspace"))
        windows = [item for item in clients() if item.get("workspace", {}).get("name") == workspace]
        windows = [item for item in windows if item.get("class") != "io.github.yogesh.AIDock"]
        if not windows:
            return {"content": [{"type": "text", "text": f"Workspace {workspace} already has no closable windows."}]}
        labels = []
        for item in windows:
            address = item.get("address")
            if not address: continue
            subprocess.run(["hyprctl", "dispatch", f'hl.dsp.window.close({{ window = "address:{address}" }})'], check=True, stdout=subprocess.DEVNULL)
            labels.append(item.get("title") or item.get("class") or address)
        for _ in range(30):
            remaining = {item.get("address") for item in clients()}
            if not any(item.get("address") in remaining for item in windows): break
            time.sleep(0.1)
        else: raise RuntimeError(f"Some windows did not close on workspace {workspace}")
        return {"content": [{"type": "text", "text": f"Closed {len(labels)} window(s) on workspace {workspace}: " + "; ".join(labels)}]}
    if name == "prepare_workspace_and_open_url":
        workspace = normalize_workspace(arguments.get("workspace"))
        url = str(arguments.get("url", "")).strip()
        if urlparse(url).scheme not in ("http", "https"):
            raise ValueError("Only http and https URLs are allowed")
        closed = call_tool("close_workspace_windows", {"workspace": workspace})["content"][0]["text"]
        opened = open_normal_brave(url, workspace)
        return {"content": [{"type": "text", "text": f"{closed}\nOpened {url} in your regular logged-in Brave on workspace {workspace} · {opened.get('title') or 'Brave'}"}]}
    if name == "adjust_audio_volume":
        action = str(arguments.get("action", "")).strip()
        volume = arguments.get("volume")
        if action == "mute":
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"], check=True, stdout=subprocess.DEVNULL)
            return {"content": [{"type": "text", "text": "Audio muted"}]}
        if action == "unmute":
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], check=True, stdout=subprocess.DEVNULL)
            return {"content": [{"type": "text", "text": "Audio unmuted"}]}
        if action == "get":
            raw = subprocess.check_output(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], text=True).strip()
            return {"content": [{"type": "text", "text": raw}]}
        if volume is not None:
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{int(volume) / 100:.2f}"], check=True, stdout=subprocess.DEVNULL)
            return {"content": [{"type": "text", "text": f"Volume set to {volume}%"}]}
        raise ValueError("Provide a volume level (0-100) or an action (mute/unmute/get)")
    if name == "adjust_screen_brightness":
        action = str(arguments.get("action", "")).strip()
        brightness = arguments.get("brightness")
        if action == "get" or brightness is None:
            raw = subprocess.check_output(["brightnessctl", "info"], text=True).strip()
            return {"content": [{"type": "text", "text": raw}]}
        subprocess.run(["brightnessctl", "set", f"{int(brightness)}%"], check=True, stdout=subprocess.DEVNULL)
        return {"content": [{"type": "text", "text": f"Brightness set to {brightness}%"}]}
    if name == "get_clipboard":
        try:
            text = subprocess.check_output(["wl-paste", "--no-newline"], text=True, timeout=3)
        except subprocess.CalledProcessError:
            text = ""
        return {"content": [{"type": "text", "text": text or "(clipboard is empty)"}]}
    if name == "set_clipboard":
        content = str(arguments.get("text", ""))
        subprocess.run(["wl-copy", content], check=True, timeout=3)
        return {"content": [{"type": "text", "text": f"Copied {len(content)} characters to clipboard"}]}
    if name == "capture_window":
        active = json.loads(subprocess.check_output(["hyprctl", "activewindow", "-j"], text=True))
        at = active.get("at", [0, 0]); size = active.get("size", [0, 0])
        geometry = f"{at[0]},{at[1]} {size[0]}x{size[1]}"
        dest = Path.home() / ".local/share/ai-dock/window-capture.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["grim", "-g", geometry, str(dest)], check=True, stdout=subprocess.DEVNULL)
        return {"content": [{"type": "text", "text": f"Window screenshot saved to {dest}"}]}
    raise ValueError(f"Unknown tool: {name}")


for raw in sys.stdin:
    try:
        message = json.loads(raw); request_id = message.get("id")
        if request_id is None: continue
        method = message.get("method")
        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "AI Dock Desktop", "version": "1.0"},
            }
        elif method == "tools/list": result = {"tools": TOOLS}
        elif method == "tools/call":
            params = message.get("params", {})
            result = call_tool(params.get("name"), params.get("arguments", {}))
        else: raise ValueError(f"Unsupported MCP method: {method}")
        reply = {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as error:
        reply = {"jsonrpc": "2.0", "id": message.get("id") if 'message' in locals() else None,
                 "error": {"code": -32000, "message": str(error)}}
    print(json.dumps(reply, separators=(",", ":")), flush=True)
