#!/usr/bin/env python3
"""Bridge AI Dock to real Brave app windows for sites that reject WebKit."""
import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path.home() / ".local/share/ai-dock/cloud-browser/claude"
PORT = 9331
PROVIDERS = {
    "chatgpt": {
        "name": "ChatGPT", "url": "https://chatgpt.com", "port": PORT,
        "host": "chatgpt.com",
        "input": ["#prompt-textarea", "div.ProseMirror[contenteditable=true]"],
        "responses": ["[data-message-author-role=assistant]"],
        "busy": ["[data-testid=stop-button]", "button[aria-label*=Stop]"],
        "users": ["[data-message-author-role=user]"],
    },
    "claude": {
        "name": "Claude", "url": "https://claude.ai/new", "port": PORT,
        "host": "claude.ai",
        "input": ["div.ProseMirror[contenteditable=true]", "div[contenteditable=true]", "textarea"],
        "responses": ["[data-testid=assistant-message]", ".font-claude-response"],
        "busy": ["button[aria-label*=Stop]", "button[data-testid*=stop]"],
        "users": ["[data-testid=user-message]", "[data-testid=human-turn]"],
    },
    "grok": {
        "name": "Grok", "url": "https://grok.com", "port": PORT,
        "host": "grok.com",
        "input": ["textarea[placeholder='Ask Grok']", "textarea[placeholder*=Grok]", "div[contenteditable=true]", "textarea"],
        "responses": ["[data-testid=assistant-message]", ".items-start .prose", ".items-start [class*=markdown]", "article"],
        "busy": ["button[aria-label*=Stop]", "button[data-testid*=stop]"],
        "users": ["[data-testid=user-message]", "article [data-testid*=user]"],
    },
}


def ready(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.6).read()
        return True
    except Exception:
        return False


def window_address():
    try:
        root_pid = int(subprocess.check_output(
            ["pgrep", "-f", f"^/opt/brave-bin/brave --remote-debugging-port={PORT}"], text=True
        ).splitlines()[0])
        clients = json.loads(subprocess.check_output(["hyprctl", "clients", "-j"], text=True))
        return next(item["address"] for item in clients if item.get("pid") == root_pid)
    except Exception:
        return None


def dispatch(expression):
    subprocess.run(["hyprctl", "dispatch", expression], check=True, stdout=subprocess.DEVNULL)


def show_window():
    address = window_address()
    if not address: raise RuntimeError("Cloud browser window was not found")
    target = f"address:{address}"
    dispatch(f'hl.dsp.window.float({{ action = "on", window = "{target}" }})')
    dispatch(f'hl.dsp.window.pin({{ action = "on", window = "{target}" }})')
    # Compact portrait popup, centered on the 1920x1080 laptop display.
    dispatch(f'hl.dsp.window.resize({{ x = 620, y = 720, exact = true, window = "{target}" }})')
    dispatch(f'hl.dsp.window.move({{ x = 650, y = 180, relative = false, window = "{target}" }})')
    dispatch(f'hl.dsp.focus({{ window = "{target}" }})')


def hide_window():
    address = window_address()
    if not address: return {"ok": True, "provider": "cloud", "message": "Browser popup is already hidden"}
    # Keep the window alive on this workspace, but move it fully beyond the
    # right screen edge. This avoids the old hidden-workspace side effect.
    target = f"address:{address}"
    dispatch(f'hl.dsp.window.float({{ action = "on", window = "{target}" }})')
    dispatch(f'hl.dsp.window.pin({{ action = "off", window = "{target}" }})')
    dispatch(f'hl.dsp.window.resize({{ x = 620, y = 720, exact = true, window = "{target}" }})')
    dispatch(f'hl.dsp.window.move({{ x = 1940, y = 120, relative = false, window = "{target}" }})')
    return {"ok": True, "provider": "cloud", "message": "Browser popup hidden"}


def launch(provider, visible=False):
    spec = PROVIDERS[provider]
    if not ready(PORT):
        ROOT.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([
            "/usr/bin/brave", f"--remote-debugging-port={PORT}",
            f"--user-data-dir={ROOT}", "--no-first-run", "--disable-default-apps",
            # One browser-style popup containing Claude and Grok as two tabs.
            "--new-window", PROVIDERS["claude"]["url"], PROVIDERS["grok"]["url"],
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(60):
            if ready(PORT): break
            time.sleep(0.25)
        else: raise RuntimeError(f"{spec['name']} browser window did not start")
        if not visible:
            # A background Flow/MCP request must not expose the popup merely
            # because the persistent browser had to be started.
            time.sleep(0.5); hide_window()
    return {"ok": True, "provider": provider, "message": "Claude + Grok browser popup connected"}


def page_for(browser, spec):
    context = browser.contexts[0]
    if spec["host"] == "chatgpt.com": import_chatgpt_cookies(context)
    pages = [page for page in context.pages if spec["host"] in page.url]
    # Prefer a fully loaded tab with a usable composer. Duplicate/stale tabs
    # can survive a browser crash and otherwise cause false login errors.
    for page in reversed(pages):
        try:
            if visible_locator(page, spec["input"]) is not None:
                # Keep one healthy tab per provider. Stale duplicates are a
                # common source of intermittent attachment/login failures.
                for duplicate in pages:
                    if duplicate != page:
                        try: duplicate.close()
                        except Exception: pass
                return page
        except Exception: pass
    if pages:
        pages[-1].reload(wait_until="domcontentloaded", timeout=60000)
        return pages[-1]
    page = context.new_page(); page.goto(spec["url"], wait_until="domcontentloaded", timeout=60000)
    return page


def import_chatgpt_cookies(context):
    """Copy the persistent WebKit ChatGPT login into the local browser bridge."""
    database = Path.home() / ".local/share/ai-dock/cookies.sqlite"
    if not database.exists(): return
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "select name,value,host,path,expiry,isSecure,isHttpOnly,sameSite from moz_cookies "
            "where host in ('chatgpt.com','.chatgpt.com')"
        ).fetchall()
    same_site = {0: "None", 1: "Lax", 2: "Strict"}
    cookies=[]
    for name,value,domain,path,expiry,secure,http_only,same in rows:
        item={"name":name,"value":value,"domain":domain,"path":path or "/",
              "secure":bool(secure),"httpOnly":bool(http_only),"sameSite":same_site.get(same,"Lax")}
        if expiry and expiry > time.time(): item["expires"]=float(expiry)
        cookies.append(item)
    if cookies: context.add_cookies(cookies)


def open_popup():
    """Normalize the shared browser window to one Claude and one Grok tab."""
    launch("claude", visible=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        context = browser.contexts[0]
        keep = {}
        for page in list(context.pages):
            provider = next((key for key, spec in PROVIDERS.items() if spec["host"] in page.url), None)
            if provider and provider not in keep: keep[provider] = page
            elif page.url != "about:blank": page.close()
        for provider, spec in PROVIDERS.items():
            if provider not in keep:
                page = context.new_page(); page.goto(spec["url"], wait_until="domcontentloaded", timeout=60000)
                keep[provider] = page
        keep["claude"].bring_to_front()
    show_window()
    return {"ok": True, "provider": "cloud", "message": "Claude + Grok browser popup connected"}


def visible_locator(page, selectors):
    for selector in selectors:
        items = page.locator(selector)
        for index in range(items.count() - 1, -1, -1):
            item = items.nth(index)
            try:
                if item.is_visible(): return item
            except Exception: pass
    return None


def response_texts(page, selectors):
    for selector in selectors:
        try:
            values = [text.strip() for text in page.locator(selector).all_inner_texts() if text.strip()]
            if values: return values
        except Exception: pass
    return []


def dismiss_overlays(page):
    """Dismiss transient Claude/Grok coachmarks and modal portals."""
    try: page.keyboard.press("Escape")
    except Exception: pass
    page.wait_for_timeout(150)
    selectors = [
        "button[aria-label*='Close']", "button[aria-label*='Dismiss']",
        "button:has-text('Got it')", "button:has-text('Dismiss')",
        "button:has-text('Maybe later')", "button:has-text('Not now')",
        "[role=dialog] button:has-text('Close')",
    ]
    for selector in selectors:
        items = page.locator(selector)
        for index in range(items.count() - 1, -1, -1):
            item = items.nth(index)
            try:
                if item.is_visible(): item.click(force=True, timeout=1200)
            except Exception: pass
    try: page.keyboard.press("Escape")
    except Exception: pass


def enter_prompt(page, field, prompt, provider=None):
    """Enter text without requiring an unobstructed pointer click."""
    dismiss_overlays(page)
    try:
        field.focus(timeout=3000)
        if provider == "chatgpt":
            field.click(force=True, timeout=3000)
            page.keyboard.press("Control+A"); page.keyboard.insert_text(prompt)
        elif field.get_attribute("contenteditable") == "true":
            field.evaluate("""(el, text) => {
              el.focus(); el.innerHTML = ''; const p=document.createElement('p');
              p.textContent=text; el.appendChild(p);
              el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:text}));
            }""", prompt)
        else: field.fill(prompt, force=True, timeout=3000)
    except Exception:
        field.click(force=True, timeout=3000)
        page.keyboard.press("Control+A"); page.keyboard.insert_text(prompt)
    page.wait_for_timeout(150)
    # Keyboard submission works even if a non-modal coachmark remains above
    # the editor. Fall back to the site's visible Send button when necessary.
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    if field.is_visible() and prompt[:80] in (field.inner_text() if field.get_attribute("contenteditable") == "true" else field.input_value()):
        send = visible_locator(page, ["button[aria-label*='Send']", "button[data-testid*='send']"])
        if send is not None: send.click(force=True, timeout=3000)


def ask(provider, prompt):
    spec = PROVIDERS[provider]; launch(provider, visible=False)
    hide_window()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        page = page_for(browser, spec)
        page.wait_for_load_state("domcontentloaded", timeout=60000)
        if any(marker in page.url.lower() for marker in ("/login", "/sign-in", "/signin", "/auth")):
            raise RuntimeError(f"Log in to {spec['name']} in its browser window, then run the workflow again")
        before = response_texts(page, spec["responses"])
        field = visible_locator(page, spec["input"])
        if field is None:
            # Grok occasionally restores the session shell before hydrating
            # its composer. One reload is more reliable than declaring logout.
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            field = visible_locator(page, spec["input"])
        if field is None:
            visible_login = visible_locator(page, ["a[href*='/login']", "a[href*='/sign-in']", "button:has-text('Sign in')", "button:has-text('Log in')"])
            if visible_login is not None:
                raise RuntimeError(f"Log in to {spec['name']} in its browser window, then run the workflow again")
            raise RuntimeError(f"{spec['name']} loaded but its message box was unavailable. Open the popup once and retry")
        enter_prompt(page, field, prompt, provider)

        # Grok permits one anonymous submission and then replaces the answer
        # with a sign-up card. Report that as login-required immediately.
        if provider == "grok":
            page.wait_for_timeout(1800)
            paywall = page.locator("[data-testid=anon-paywall-sign-up-card]")
            if any(paywall.nth(index).is_visible() for index in range(paywall.count())):
                raise RuntimeError("Log in to Grok in its browser window, then run the workflow again")

        last, stable, saw_busy = "", 0, False
        deadline = time.time() + 420
        while time.time() < deadline:
            time.sleep(0.6)
            current = response_texts(page, spec["responses"])
            candidate = current[-1] if current else ""
            changed = bool(candidate and (not before or candidate != before[-1]) and candidate != prompt)
            busy = visible_locator(page, spec["busy"]) is not None
            saw_busy = saw_busy or busy
            if changed:
                stable = stable + 1 if candidate == last else 0
                last = candidate
                if stable >= (8 if saw_busy else 40) and not busy:
                    hide_window()
                    return {"ok": True, "provider": provider, "answer": last, "url": page.url}
        raise RuntimeError(f"Timed out waiting for {spec['name']}'s complete response")


def snapshot():
    if not ready(PORT): return {"ok": False, "error": "Cloud browser is not running"}
    output = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        for provider, spec in PROVIDERS.items():
            page = next((page for page in browser.contexts[0].pages if spec["host"] in page.url), None)
            if page is None: continue
            items = []
            for role, selectors in (("user", spec.get("users", [])), ("assistant", spec["responses"])):
                seen = set()
                for selector in selectors:
                    try:
                        for value in page.locator(selector).all_inner_texts()[-30:]:
                            value = value.strip()
                            if value and value not in seen: seen.add(value); items.append({"role": role, "text": value})
                    except Exception: pass
            output[provider] = items
    return {"ok": True, "providers": output}


def main():
    action, provider = sys.argv[1:3]
    if provider not in PROVIDERS: raise ValueError("Unknown cloud AI")
    if action in ("open", "show"): output = open_popup()
    elif action == "hide": output = hide_window()
    elif action == "status": output = {"ok": ready(PORT), "provider": provider}
    elif action == "snapshot": output = snapshot()
    elif action == "ask": output = ask(provider, sys.stdin.read())
    else: raise ValueError("Unknown action")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False)); raise SystemExit(1)
