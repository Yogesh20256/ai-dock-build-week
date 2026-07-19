#!/usr/bin/env python3
"""Create useful documents and maintain AI Dock's local reports webpage."""
import csv
import html
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / "Documents" / "AI Dock Reports"
INDEX = ROOT / "index.html"
SUPPORTED = {".txt", ".md", ".json", ".csv", ".html", ".pdf"}

TOOLS = [
    {"name": "create_document", "description": "Create a populated TXT, Markdown, JSON, CSV, HTML, or rendered PDF document. Relative filenames are saved in Documents/AI Dock Reports. Updates the local reports webpage.", "inputSchema": {"type": "object", "properties": {"filename": {"type": "string"}, "content": {"type": "string"}, "title": {"type": "string"}}, "required": ["filename", "content"], "additionalProperties": False}},
    {"name": "open_reports_page", "description": "Open the local AI Dock Reports webpage containing links to generated files.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
]

def safe_path(filename):
    raw = Path(str(filename)).expanduser()
    path = raw if raw.is_absolute() else ROOT / raw
    path = path.resolve()
    allowed = (Path.home() / "Documents").resolve()
    if path != allowed and allowed not in path.parents: raise ValueError("Documents must remain under ~/Documents")
    if path.suffix.lower() not in SUPPORTED: raise ValueError("Supported document types: txt, md, json, csv, html, pdf")
    return path

def html_document(title, content):
    paragraphs = "\n".join(f"<p>{html.escape(line)}</p>" if line.strip() else "<br>" for line in content.splitlines())
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>
<style>body{{font:16px system-ui;max-width:900px;margin:48px auto;padding:0 28px;line-height:1.55;color:#172033}}h1{{color:#4d42c7}}p{{white-space:pre-wrap}}</style></head><body><h1>{html.escape(title)}</h1>{paragraphs}</body></html>"""

def update_index():
    ROOT.mkdir(parents=True, exist_ok=True)
    files = sorted((p for p in ROOT.rglob("*") if p.is_file() and p != INDEX), key=lambda p: p.stat().st_mtime, reverse=True)
    rows = "\n".join(f"<li><a href='{html.escape(p.relative_to(ROOT).as_posix())}'>{html.escape(p.name)}</a><small>{datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M}</small></li>" for p in files)
    INDEX.write_text(f"""<!doctype html><html><head><meta charset='utf-8'><title>AI Dock Reports</title><style>
body{{font:16px system-ui;background:#11131a;color:#eef1ff;max-width:900px;margin:50px auto;padding:0 25px}}h1{{color:#7ee0ba}}ul{{padding:0}}li{{list-style:none;background:#202431;margin:10px 0;padding:14px;border-radius:10px}}a{{color:#a99cff;font-weight:700;text-decoration:none}}small{{float:right;color:#9fa8c2}}</style></head><body><h1>AI Dock Reports</h1><p>Generated documents and website audits.</p><ul>{rows or '<li>No reports yet.</li>'}</ul></body></html>""")

def create(args):
    path = safe_path(args["filename"]); content = str(args["content"]); title = str(args.get("title") or path.stem.replace("_", " ").title())
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".json":
        try: parsed = json.loads(content); path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False) + "\n")
        except json.JSONDecodeError: path.write_text(json.dumps({"content": content}, indent=2, ensure_ascii=False) + "\n")
    elif suffix == ".csv":
        rows = list(csv.reader(content.splitlines()));
        with path.open("w", newline="") as stream: csv.writer(stream).writerows(rows)
    elif suffix == ".html": path.write_text(html_document(title, content))
    elif suffix == ".pdf":
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "document.html"; source.write_text(html_document(title, content))
            subprocess.run(["/usr/bin/brave", "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={path}", source.as_uri()], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        if not path.exists() or path.stat().st_size < 500: raise RuntimeError("PDF rendering failed")
    else: path.write_text(content)
    update_index()
    return {"content": [{"type": "text", "text": f"Created {suffix[1:].upper()} document: {path}\nReports page: {INDEX.as_uri()}"}]}

def call(name, args):
    if name == "create_document": return create(args)
    if name == "open_reports_page":
        update_index(); subprocess.Popen(["/usr/bin/brave", INDEX.as_uri()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"content": [{"type": "text", "text": f"Opened reports page: {INDEX.as_uri()}"}]}
    raise ValueError(f"Unknown tool: {name}")

for raw in sys.stdin:
    try:
        message=json.loads(raw); rid=message.get("id")
        if rid is None: continue
        method=message.get("method")
        if method=="initialize": result={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"AI Dock Documents","version":"1.0"}}
        elif method=="tools/list": result={"tools":TOOLS}
        elif method=="tools/call":
            params=message.get("params",{}); result=call(params.get("name"),params.get("arguments",{}))
        else: raise ValueError(f"Unsupported method: {method}")
        reply={"jsonrpc":"2.0","id":rid,"result":result}
    except Exception as error: reply={"jsonrpc":"2.0","id":message.get("id") if "message" in locals() else None,"error":{"code":-32000,"message":str(error)}}
    print(json.dumps(reply,separators=(",",":")),flush=True)
