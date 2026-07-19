#!/usr/bin/env python3
"""Persistent same-tab Brave automation for AI Dock MCP."""
import json
import re
import subprocess
import sys
import time
import urllib.request
import html
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from playwright.sync_api import sync_playwright


PORT = 9223
PROFILE = Path.home() / ".local/share/ai-dock/controlled-browser"
ACTIVE_PAGE = Path.home() / ".local/share/ai-dock/active-browser-page.json"
PLAYWRIGHT = BROWSER = CURRENT_PAGE = None

TOOLS = [
    {"name": "browser_open", "description": "Reuse an already-open matching website tab on the target/current workspace. Does nothing destructive when the website is already open. Creates a tab only when absent or new_tab is explicitly requested.", "inputSchema": {"type": "object", "properties": {"website": {"type": "string"}, "workspace": {"type": "string", "description": "Target workspace number or special workspace. Omit for current."}, "new_tab": {"type": "boolean", "description": "Explicitly open another tab even if the site is already open"}}, "required": ["website"], "additionalProperties": False}},
    {"name": "browser_search", "description": "Search in an already-open matching website tab when available. Creates a tab only when absent or new_tab is explicitly requested.", "inputSchema": {"type": "object", "properties": {"site": {"type": "string"}, "query": {"type": "string"}, "workspace": {"type": "string", "description": "Target workspace number or special workspace. Omit for current."}, "new_tab": {"type": "boolean", "description": "Explicitly perform the search in a new tab"}}, "required": ["site", "query"], "additionalProperties": False}},
    {"name": "browser_merge_windows", "description": "Merge multiple AI-controlled Brave windows into one by preserving their pages as tabs in a single window and closing the extra browser windows.", "inputSchema": {"type": "object", "properties": {"workspace": {"type": "string", "description": "Workspace for the merged browser window; omit for current"}}, "additionalProperties": False}},
    {"name": "browser_audit_website", "description": "Inspect the current website's DOM/code for common bugs, accessibility issues, broken links, failed resources, duplicate IDs and console errors, then automatically save HTML and JSON reports under Documents/Bug Reports.", "inputSchema": {"type": "object", "properties": {"label": {"type": "string", "description": "Optional report name"}}, "additionalProperties": False}},
    {"name": "browser_click_first_result", "description": "Click the first result on the current page in the same tab. On YouTube, kind can be channel or video.", "inputSchema": {"type": "object", "properties": {"kind": {"type": "string", "enum": ["auto", "channel", "video"]}}, "additionalProperties": False}},
    {"name": "browser_click_text", "description": "Click the first visible link, button, or control containing the requested text in the current page.", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False}},
    {"name": "browser_read_page", "description": "Read the title, URL, and visible text of the current controlled browser page.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "browser_back", "description": "Go back in the current controlled browser tab.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "browser_close", "description": "Close the current or matching AI-controlled browser tab while preserving other tabs and the browser session.", "inputSchema": {"type":"object","properties":{"website":{"type":"string"}},"additionalProperties":False}},
    {"name": "browser_show_numbers", "description": "Overlay visible numbered badges on clickable controls in the current browser page, similar to Windows Voice Access. Returns the number-to-control list.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "browser_hide_numbers", "description": "Remove all numbered control badges and number mappings from the current browser page.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "browser_click_number", "description": "Click a browser control previously labelled by browser_show_numbers.", "inputSchema": {"type": "object", "properties": {"number": {"type": "integer", "minimum": 1}}, "required": ["number"], "additionalProperties": False}},
]


def endpoint_ready():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1).read()
        return True
    except Exception: return False


def target_workspace(value):
    requested = str(value or "").strip().lower()
    if not requested or requested in ("current", "current workspace", "here"):
        return str(json.loads(subprocess.check_output(["hyprctl", "activeworkspace", "-j"], text=True))["name"])
    requested = re.sub(r"^(?:workspace|ws|w)\s*", "", requested).strip()
    if requested in ("hidden", "hidden workspace", "special", "special workspace"): return "special:special"
    if requested.startswith("special:") and re.fullmatch(r"special:[a-z0-9_-]+", requested): return requested
    if re.fullmatch(r"[1-9][0-9]*", requested): return requested
    raise ValueError(f"Invalid workspace: {value}")


def place_browser(workspace):
    for _ in range(30):
        windows = json.loads(subprocess.check_output(["hyprctl", "clients", "-j"], text=True))
        try:
            controlled_pid = int(subprocess.check_output(
                ["pgrep", "-f", f"remote-debugging-port={PORT}.*controlled-browser"], text=True
            ).splitlines()[0])
        except Exception: controlled_pid = -1
        matches = [item for item in windows if item.get("pid") == controlled_pid]
        if matches:
            window = min(matches, key=lambda item: item.get("focusHistoryID", 999999))
            if window.get("workspace", {}).get("name") != workspace:
                subprocess.run(["hyprctl", "dispatch", f'hl.dsp.window.move({{ window = "address:{window["address"]}", workspace = "{workspace}", follow = false }})'], check=True, stdout=subprocess.DEVNULL)
            return
        time.sleep(0.1)


def ensure_browser():
    if endpoint_ready(): return
    PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([
        "/usr/bin/brave", f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE}",
        "--no-first-run", "--disable-default-apps", "https://www.google.com/",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(40):
        if endpoint_ready(): return
        time.sleep(0.25)
    raise RuntimeError("The AI-controlled Brave browser did not start")


def with_page(action):
    global PLAYWRIGHT, BROWSER, CURRENT_PAGE
    ensure_browser()
    if BROWSER is None or not BROWSER.is_connected():
        PLAYWRIGHT = sync_playwright().start()
        BROWSER = PLAYWRIGHT.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
    context = BROWSER.contexts[0]
    usable = [item for item in context.pages if item.url != "about:blank"]
    page = CURRENT_PAGE if CURRENT_PAGE in context.pages else None
    if page is None:
        try:
            remembered = json.loads(ACTIVE_PAGE.read_text()).get("url", "")
            page = next((item for item in usable if item.url == remembered), None)
        except (OSError, ValueError, TypeError): pass
    page = page or (usable[-1] if usable else (context.pages[-1] if context.pages else context.new_page()))
    answer = action(page)
    remember_page(page)
    # Old launcher versions left empty tabs behind. Remove them after a real
    # page is available so the controlled browser never appears blank again.
    if page.url != "about:blank":
        for item in list(context.pages):
            if item != page and item.url == "about:blank":
                try: item.close()
                except Exception: pass
    return answer


def browser_context():
    global PLAYWRIGHT, BROWSER
    ensure_browser()
    if BROWSER is None or not BROWSER.is_connected():
        PLAYWRIGHT = sync_playwright().start()
        BROWSER = PLAYWRIGHT.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
    return BROWSER.contexts[0]


def remember_page(page):
    try:
        ACTIVE_PAGE.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE_PAGE.write_text(json.dumps({"url": page.url, "title": page.title()}))
    except Exception: pass


def site_host(value):
    return urlparse(website_url(value)).netloc.lower().removeprefix("www.")


def matching_page(context, site):
    host = site_host(site)
    matches = []
    for page in context.pages:
        try:
            page_host = urlparse(page.url).netloc.lower().removeprefix("www.")
            if page_host == host or page_host.endswith("." + host): matches.append(page)
        except Exception: pass
    return matches[-1] if matches else None


def choose_site_page(site, new_tab=False):
    global CURRENT_PAGE
    context = browser_context()
    page = None if new_tab else matching_page(context, site)
    if page is None: page = context.new_page()
    page.bring_to_front()
    CURRENT_PAGE = page
    remember_page(page)
    return context, page


def result(text): return {"content": [{"type": "text", "text": text}]}


def website_url(value):
    value = value.strip(); key = value.lower().replace(" web", "")
    sites = {
        "whatsapp": "https://web.whatsapp.com", "youtube": "https://www.youtube.com",
        "leetcode": "https://leetcode.com", "github": "https://github.com",
        "reddit": "https://www.reddit.com", "wikipedia": "https://wikipedia.org",
        "google": "https://www.google.com", "gmail": "https://mail.google.com",
        "instagram": "https://www.instagram.com", "facebook": "https://www.facebook.com",
        "linkedin": "https://www.linkedin.com", "twitter": "https://x.com",
        "netflix": "https://www.netflix.com", "spotify": "https://open.spotify.com",
    }
    if key in sites: return sites[key]
    if value.startswith(("http://", "https://")): return value
    return "https://" + value


def call_tool(name, args):
    if name == "browser_open":
        url = website_url(str(args["website"]))
        original_workspace = target_workspace(None)
        workspace = target_workspace(args.get("workspace"))
        context, page = choose_site_page(str(args["website"]), bool(args.get("new_tab", False)))
        already_open = site_host(page.url) == site_host(url) if page.url.startswith(("http://", "https://")) else False
        if not already_open: page.goto(url, wait_until="domcontentloaded", timeout=45000)
        remember_page(page)
        answer = result(f"{'Reused' if already_open else 'Opened'} {page.title()} in {'a new' if args.get('new_tab') else 'the matching'} tab on workspace {workspace}: {page.url}")
        place_browser(workspace)
        if original_workspace != workspace:
            subprocess.run(["hyprctl", "dispatch", f'hl.dsp.focus({{ workspace = "{original_workspace}" }})'], stdout=subprocess.DEVNULL)
        return answer
    if name == "browser_search":
        site, query = str(args["site"]).lower().strip(), str(args["query"]).strip()
        original_workspace = target_workspace(None)
        workspace = target_workspace(args.get("workspace"))
        def search(page):
            if site == "youtube":
                # Navigation commitment is enough to start the requested
                # search. Do not block the MCP result on YouTube rendering its
                # heavy result cards; they continue loading visibly.
                page.goto(f"https://www.youtube.com/results?search_query={quote_plus(query)}", wait_until="commit", timeout=20000)
                page.wait_for_timeout(400)
            elif site == "leetcode": page.goto(f"https://leetcode.com/problemset/?search={quote_plus(query)}", wait_until="domcontentloaded", timeout=45000)
            elif site == "github": page.goto(f"https://github.com/search?q={quote_plus(query)}", wait_until="domcontentloaded", timeout=45000)
            elif site == "reddit": page.goto(f"https://www.reddit.com/search/?q={quote_plus(query)}", wait_until="domcontentloaded", timeout=45000)
            elif site == "wikipedia": page.goto(f"https://en.wikipedia.org/w/index.php?search={quote_plus(query)}", wait_until="domcontentloaded", timeout=45000)
            else: page.goto(f"https://www.google.com/search?q={quote_plus(query)}", wait_until="domcontentloaded", timeout=45000)
            return result(f"Searched {site} for '{query}' in the existing tab on workspace {workspace}. Current page: {page.title()}")
        _context, page = choose_site_page(site, bool(args.get("new_tab", False)))
        answer = search(page); remember_page(page); place_browser(workspace)
        # Chromium may emit a delayed focus/map event after navigation. Apply
        # the explicit workspace once more after that short event window.
        time.sleep(0.35); place_browser(workspace)
        if original_workspace != workspace:
            subprocess.run(["hyprctl", "dispatch", f'hl.dsp.focus({{ workspace = "{original_workspace}" }})'], stdout=subprocess.DEVNULL)
        return answer
    if name == "browser_merge_windows":
        workspace = target_workspace(args.get("workspace"))
        context = browser_context()
        pages = [page for page in context.pages if page.url != "about:blank"]
        if not pages: raise RuntimeError("No controlled Brave pages are open")
        sessions = []
        for page in pages:
            session = context.new_cdp_session(page)
            target = session.send("Target.getTargetInfo")["targetInfo"]["targetId"]
            window_id = session.send("Browser.getWindowForTarget", {"targetId": target})["windowId"]
            sessions.append((page, window_id))
        window_ids = list(dict.fromkeys(window_id for _page, window_id in sessions))
        if len(window_ids) <= 1:
            place_browser(workspace); return result("Controlled Brave is already merged into one window.")
        primary_id = window_ids[0]
        primary_page = next(page for page, window_id in sessions if window_id == primary_id)
        primary_page.bring_to_front()
        moved = 0
        for old_page, window_id in list(sessions):
            if window_id == primary_id: continue
            url = old_page.url
            if url.startswith(("http://", "https://")):
                replacement = context.new_page(); replacement.goto(url, wait_until="domcontentloaded", timeout=45000); moved += 1
            old_page.close()
        # Closing every tab in an extra Chromium window closes that window.
        place_browser(workspace)
        return result(f"Merged {len(window_ids)} controlled Brave windows into one on workspace {workspace}; preserved {moved} page(s) as tabs.")
    if name == "browser_audit_website":
        def audit(page):
            data = page.evaluate("""() => {
              const duplicates=[...document.querySelectorAll('[id]')].map(e=>e.id).filter((id,i,a)=>id&&a.indexOf(id)!==i).filter((id,i,a)=>a.indexOf(id)===i);
              const images=[...document.images].filter(i=>!i.alt).map(i=>i.src).slice(0,100);
              const emptyLinks=[...document.querySelectorAll('a[href]')].filter(a=>!(a.textContent||a.getAttribute('aria-label')||'').trim()).map(a=>a.href).slice(0,100);
              const unlabeled=[...document.querySelectorAll('input,textarea,select')].filter(e=>!e.labels?.length&&!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')).map(e=>e.outerHTML.slice(0,200)).slice(0,100);
              const failed=performance.getEntriesByType('resource').filter(r=>r.transferSize===0&&r.decodedBodySize===0&&!r.name.startsWith('data:')).map(r=>r.name).slice(0,150);
              return {title:document.title,url:location.href,htmlSize:document.documentElement.outerHTML.length,duplicateIds:duplicates,imagesMissingAlt:images,emptyLinks,unlabeledFields:unlabeled,failedResources:failed,headingCount:document.querySelectorAll('h1,h2,h3,h4,h5,h6').length,forms:document.forms.length};
            }""")
            links = page.locator("a[href]").evaluate_all("els => [...new Set(els.map(e=>e.href).filter(h=>h.startsWith('http')))].slice(0,30)")
            broken=[]
            for url in links:
                try:
                    request=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"Mozilla/5.0"})
                    with urllib.request.urlopen(request,timeout=4) as response:
                        if response.status>=400: broken.append({"url":url,"status":response.status})
                except Exception as error: broken.append({"url":url,"error":str(error)[:160]})
            data["brokenLinks"]=broken
            findings=[]
            labels=(("Duplicate IDs","duplicateIds"),("Images missing alt text","imagesMissingAlt"),("Empty links","emptyLinks"),("Unlabelled form fields","unlabeledFields"),("Failed resources","failedResources"),("Broken or unreachable links","brokenLinks"))
            for title,key in labels:
                if data[key]: findings.append({"category":title,"count":len(data[key]),"items":data[key]})
            data["findings"]=findings
            folder=Path.home()/"Documents"/"Bug Reports"; folder.mkdir(parents=True,exist_ok=True)
            stamp=datetime.now().strftime("%Y%m%d-%H%M%S"); safe=re.sub(r"[^a-z0-9]+","-",str(args.get("label") or data["title"] or "website").lower()).strip("-")[:60]
            base=folder/f"{safe}-{stamp}"; json_path=base.with_suffix(".json"); html_path=base.with_suffix(".html")
            json_path.write_text(json.dumps(data,indent=2,ensure_ascii=False))
            sections="".join(f"<section><h2>{html.escape(item['category'])} ({item['count']})</h2><pre>{html.escape(json.dumps(item['items'],indent=2,ensure_ascii=False))}</pre></section>" for item in findings)
            html_path.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>Bug report - {html.escape(data['title'])}</title><style>body{{font:15px system-ui;max-width:1000px;margin:40px auto;padding:0 24px}}pre{{white-space:pre-wrap;background:#f2f4f8;padding:14px;border-radius:8px}}.ok{{color:green}}</style></head><body><h1>Website Bug Report</h1><p><b>Page:</b> {html.escape(data['title'])}<br><b>URL:</b> {html.escape(data['url'])}<br><b>Generated:</b> {datetime.now().isoformat(timespec='seconds')}</p>{sections or '<p class=ok>No common DOM/resource defects detected by this automated audit.</p>'}</body></html>")
            return result(f"Website audit completed with {sum(x['count'] for x in findings)} finding(s).\nHTML report: {html_path}\nJSON evidence: {json_path}")
        return with_page(audit)
    if name == "browser_click_first_result":
        kind = str(args.get("kind", "auto"))
        def click(page):
            candidates = []
            if kind in ("channel", "auto"): candidates.append("ytd-channel-renderer a#main-link")
            if kind in ("video", "auto"): candidates.append("ytd-video-renderer a#video-title")
            candidates.extend(["main a[href]", "a[href]"])
            for selector in candidates:
                target = page.locator(selector).first
                if target.count() and target.is_visible():
                    label = (target.inner_text(timeout=3000) or target.get_attribute("aria-label") or "first result").strip()
                    target.click(); page.wait_for_timeout(3000)
                    return result(f"Clicked {label}. Current page: {page.title()} · {page.url}")
            raise RuntimeError("No visible result link was found on the current page")
        return with_page(click)
    if name == "browser_click_text":
        wanted = str(args["text"])
        def click(page):
            target = page.get_by_text(wanted, exact=False).first
            target.wait_for(state="visible", timeout=15000); target.click()
            return result(f"Clicked the first visible control containing '{wanted}'. Current page: {page.title()}")
        return with_page(click)
    if name == "browser_read_page":
        return with_page(lambda page: result(f"TITLE: {page.title()}\nURL: {page.url}\n\n{page.locator('body').inner_text()[:12000]}"))
    if name == "browser_back":
        return with_page(lambda page: (page.go_back(wait_until="domcontentloaded"), result(f"Went back to {page.title()} · {page.url}"))[1])
    if name == "browser_close":
        global CURRENT_PAGE
        context=browser_context();target=matching_page(context,args.get("website")) if args.get("website") else (CURRENT_PAGE if CURRENT_PAGE in context.pages else next((p for p in reversed(context.pages) if p.url!="about:blank"),None))
        if not target:return result("No matching controlled browser tab is open.")
        title,url=target.title(),target.url;target.close();remaining=[p for p in context.pages if p.url!="about:blank"];CURRENT_PAGE=remaining[-1] if remaining else None
        if CURRENT_PAGE:remember_page(CURRENT_PAGE)
        return result(f"Closed browser tab: {title} · {url}")
    if name == "browser_show_numbers":
        def show(page):
            items = page.locator("a[href], button, input, textarea, select, [role='button'], [role='link'], [tabindex]").evaluate_all("""els => {
              document.querySelectorAll('.ai-dock-number-badge').forEach(e => e.remove());
              document.querySelectorAll('[data-ai-dock-number]').forEach(e => delete e.dataset.aiDockNumber);
              let n = 0, out = [];
              for (const el of els) {
                const r = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                if (el.disabled || el.getAttribute('aria-hidden') === 'true' || r.width < 8 || r.height < 8 || r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth || style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') continue;
                // Avoid duplicate numbers for a clickable child nested inside
                // an already numbered clickable parent at the same location.
                if (out.some(x => Math.abs(x.left-r.left)<3 && Math.abs(x.top-r.top)<3 && Math.abs(x.width-r.width)<3 && Math.abs(x.height-r.height)<3)) continue;
                const number = ++n; el.dataset.aiDockNumber = String(number);
                const badge = document.createElement('span'); badge.className = 'ai-dock-number-badge'; badge.textContent = String(number);
                Object.assign(badge.style,{position:'fixed',left:`${Math.min(innerWidth-28,Math.max(2,r.left))}px`,top:`${Math.min(innerHeight-24,Math.max(2,r.top))}px`,zIndex:'2147483647',background:'#ff315f',color:'white',font:'bold 12px sans-serif',lineHeight:'16px',padding:'1px 5px',border:'2px solid white',borderRadius:'10px',pointerEvents:'none',boxShadow:'0 1px 4px #000'});
                document.documentElement.appendChild(badge);
                const label=(el.getAttribute('aria-label')||el.innerText||el.placeholder||el.title||el.value||el.tagName).trim().replace(/\\s+/g,' ').slice(0,100);
                out.push({number,label,left:r.left,top:r.top,width:r.width,height:r.height}); if(n>=60) break;
              } return out;
            }""")
            if not items: raise RuntimeError("No visible clickable controls were found")
            listing = "\n".join(f"{item['number']}: {item['label']}" for item in items)
            return result(f"Numbered {len(items)} visible controls on {page.title()}. Say 'click NUMBER'.\n\n{listing}")
        return with_page(show)
    if name == "browser_hide_numbers":
        def hide(page):
            removed = page.evaluate("""() => {
              const badges = [...document.querySelectorAll('.ai-dock-number-badge')];
              badges.forEach(e => e.remove());
              document.querySelectorAll('[data-ai-dock-number]').forEach(e => delete e.dataset.aiDockNumber);
              return badges.length;
            }""")
            return result(f"Hidden {removed} numbered badges on {page.title()}.")
        return with_page(hide)
    if name == "browser_click_number":
        number = int(args["number"])
        def click_number(page):
            target = page.locator(f"[data-ai-dock-number='{number}']").first
            if not target.count(): raise RuntimeError(f"Number {number} is no longer available. Run show numbers again.")
            label = (target.get_attribute("aria-label") or target.inner_text() or f"control {number}").strip()[:120]
            target.click(); page.locator(".ai-dock-number-badge").evaluate_all("els => els.forEach(e => e.remove())")
            page.locator("[data-ai-dock-number]").evaluate_all("els => els.forEach(e => delete e.dataset.aiDockNumber)")
            page.wait_for_timeout(1500)
            remember_page(page)
            return result(f"Clicked number {number}: {label}. Current page: {page.title()} · {page.url}")
        return with_page(click_number)
    raise ValueError(f"Unknown browser tool: {name}")


for raw in sys.stdin:
    try:
        message = json.loads(raw); request_id = message.get("id")
        if request_id is None: continue
        method = message.get("method")
        if method == "initialize": response = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "AI Dock Browser", "version": "1.0"}}
        elif method == "tools/list": response = {"tools": TOOLS}
        elif method == "tools/call":
            params = message.get("params", {}); response = call_tool(params.get("name"), params.get("arguments", {}))
        else: raise ValueError(f"Unsupported MCP method: {method}")
        reply = {"jsonrpc": "2.0", "id": request_id, "result": response}
    except Exception as error:
        reply = {"jsonrpc": "2.0", "id": message.get("id") if "message" in locals() else None, "error": {"code": -32000, "message": str(error)}}
    print(json.dumps(reply, separators=(",", ":")), flush=True)
