#!/usr/bin/env python3
"""Import official AI chat exports and an authenticated ChatGPT history into Obsidian Vault."""
import argparse, hashlib, html, json, re, sqlite3, time, urllib.request, zipfile
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

def find_vault():
    for name in ("Obsidian Vault", "Connected Brain", "Brain"):
        p = Path.home() / "Documents" / name
        if p.is_dir(): return p
    return Path.home() / "Documents" / "Obsidian Vault"
VAULT = find_vault()
DEST = VAULT / "Imported Chats"
MANIFEST = DEST / ".imported.json"

def clean(text): return re.sub(r"\n{3,}", "\n\n", str(text or "").replace("\x00", "")).strip()
def imported(provider, ident):
    digest=hashlib.sha256(f"{provider}\0{ident}".encode()).hexdigest()
    try: return digest in set(json.loads(MANIFEST.read_text()))
    except Exception: return False
def slug(text): return (re.sub(r"[^A-Za-z0-9._ -]", "", clean(text))[:90].strip(" .") or "Untitled")
def stamp(value):
    if isinstance(value, dict): value = value.get("$date") or value.get("seconds")
    try:
        if isinstance(value, (int,float)): return datetime.fromtimestamp(value).isoformat(timespec="seconds")
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat(timespec="seconds")
    except Exception: return clean(value) or "Unknown date"

def save(provider, ident, title, created, messages):
    digest=hashlib.sha256(f"{provider}\0{ident}".encode()).hexdigest()
    try: seen=set(json.loads(MANIFEST.read_text()))
    except Exception: seen=set()
    if digest in seen: return False
    year=(stamp(created)[:4] if stamp(created)[:4].isdigit() else "Unknown")
    folder=DEST/provider/year; folder.mkdir(parents=True,exist_ok=True)
    path=folder/f"{slug(title)} - {str(ident)[:12]}.md"
    out=["---",f"type: imported-chat",f"provider: {provider}",f"created: {stamp(created)}","tags: [connected-brain, imported-chat]","---","",f"# {clean(title) or 'Untitled'}","",f"Connected to [[Home]] · [[Brain Map]] · [[Providers/{provider}|{provider}]] · [[Imported Chats/Index|Imported Chat Index]]",""]
    for role,text,when in messages:
        text=clean(text)
        if text: out += [f"## {str(role).title()} · {stamp(when)}","",text,"","---",""]
    path.write_text("\n".join(out))
    seen.add(digest); MANIFEST.parent.mkdir(parents=True,exist_ok=True); MANIFEST.write_text(json.dumps(sorted(seen),indent=2)+"\n")
    return True

def deepseek(path):
    with zipfile.ZipFile(path) as z: data=json.loads(z.read("conversations.json"))
    n=0
    for c in data:
        msgs=[]
        for node in c.get("mapping",{}).values():
            m=node.get("message") or {}
            for f in m.get("fragments",[]):
                role="user" if f.get("type")=="REQUEST" else "assistant"
                msgs.append((role,f.get("content"),m.get("inserted_at")))
        n+=save("DeepSeek",c.get("id"),c.get("title"),c.get("inserted_at"),msgs)
    return n

def claude(path):
    with zipfile.ZipFile(path) as z: data=json.loads(z.read("conversations.json"))
    n=0
    for c in data:
        msgs=[("user" if m.get("sender")=="human" else "assistant",m.get("text"),m.get("created_at")) for m in c.get("chat_messages",[])]
        n+=save("Claude",c.get("uuid"),c.get("name"),c.get("created_at"),msgs)
    return n

def grok(path):
    with zipfile.ZipFile(path) as z:
        name=next(x for x in z.namelist() if x.endswith("prod-grok-backend.json")); data=json.loads(z.read(name))["conversations"]
    n=0
    for item in data:
        c=item["conversation"]; msgs=[]
        for wrapper in item.get("responses",[]):
            r=wrapper.get("response",{}); sender=str(r.get("sender","")).lower(); role="user" if sender in ("human","user") else "assistant"
            msgs.append((role,r.get("message"),r.get("create_time")))
        n+=save("Grok",c.get("id"),c.get("title"),c.get("create_time"),msgs)
    return n

class GeminiParser(HTMLParser):
    def __init__(self): super().__init__(); self.depth=0; self.buf=[]; self.cards=[]
    def handle_starttag(self,tag,attrs):
        classes=dict(attrs).get("class","")
        if tag=="div" and self.depth: self.depth+=1
        elif tag=="div" and "outer-cell" in classes: self.depth=1; self.buf=[]
        if self.depth and tag in ("br","p","div"): self.buf.append("\n")
    def handle_endtag(self,tag):
        if self.depth and tag=="div":
            self.depth-=1
            if self.depth==0: self.cards.append(clean(html.unescape("".join(self.buf))))
    def handle_data(self,data):
        if self.depth: self.buf.append(data)

def gemini(path):
    with zipfile.ZipFile(path) as z: raw=z.read("Takeout/My Activity/Gemini Apps/MyActivity.html").decode(errors="replace")
    p=GeminiParser(); p.feed(raw); n=0
    for i,card in enumerate(p.cards):
        title=next((x.strip() for x in card.splitlines() if x.strip()),f"Gemini activity {i+1}")
        n+=save("Gemini",f"activity-{i}-{hashlib.sha256(card.encode()).hexdigest()[:12]}",title,"Unknown date",[("activity",card,"Unknown date")])
    return n

def chatgpt(cookie_db):
    db=sqlite3.connect(cookie_db); rows=db.execute("select name,value from moz_cookies where host in ('chatgpt.com','.chatgpt.com')").fetchall()
    cookie="; ".join(f"{n}={v}" for n,v in rows); headers={"Cookie":cookie,"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36","Accept":"application/json"}
    def get(url):
        error=None
        for delay in (0,1,3,7):
            if delay: time.sleep(delay)
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=45) as r: return json.load(r)
            except Exception as exc: error=exc
        raise error
    session=get("https://chatgpt.com/api/auth/session")
    if not session.get("accessToken"): raise RuntimeError("ChatGPT session has no access token; log in again in AI Dock")
    headers["Authorization"]="Bearer "+session["accessToken"]
    offset=0; items=[]
    while True:
        page=get(f"https://chatgpt.com/backend-api/conversations?offset={offset}&limit=100&order=updated")
        batch=page.get("items",[]); items.extend(batch)
        if not batch or len(items)>=page.get("total",len(items)): break
        offset+=len(batch)
    n=0
    for item in items:
        cid=item.get("id")
        if imported("ChatGPT",cid): continue
        c=get(f"https://chatgpt.com/backend-api/conversation/{cid}"); msgs=[]
        for node in c.get("mapping",{}).values():
            m=node.get("message") or {}; author=(m.get("author") or {}).get("role","")
            parts=(m.get("content") or {}).get("parts",[]); text="\n".join(x for x in parts if isinstance(x,str))
            if author in ("user","assistant") and text: msgs.append((author,text,m.get("create_time")))
        msgs.sort(key=lambda x: stamp(x[2])); n+=save("ChatGPT",cid,c.get("title") or item.get("title"),c.get("create_time") or item.get("create_time"),msgs)
    return n,len(items)

def index():
    providers=[]
    for folder in sorted(p for p in DEST.iterdir() if p.is_dir()):
        count=sum(1 for _ in folder.rglob("*.md")); providers.append((folder.name,count))
    text="# Imported Chat Index\n\nConnected to [[Home]] · [[Brain Map]] · [[Chats/Cross-AI Index|Live Chat Index]]\n\n"+"\n".join(f"- [[Providers/{p}|{p}]]: {n} imported conversations" for p,n in providers)+"\n"
    (DEST/"Index.md").write_text(text)

if __name__=="__main__":
    a=argparse.ArgumentParser(); a.add_argument("--all",action="store_true"); a.add_argument("--chatgpt",action="store_true"); args=a.parse_args(); result={}
    if args.all:
        result.update(DeepSeek=deepseek(Path.home()/"Downloads/DeepSeekExport.zip"),Claude=claude(Path.home()/"Downloads/ClaudeExport.zip"),Grok=grok(Path.home()/"Downloads/GrokExport.zip"),Gemini=gemini(Path.home()/"Downloads/GeminiExport.zip"))
    if args.chatgpt: result["ChatGPT_new"],result["ChatGPT_total"]=chatgpt(Path.home()/".local/share/ai-dock/cookies.sqlite")
    index(); print(json.dumps(result,indent=2))
