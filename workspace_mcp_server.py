#!/usr/bin/env python3
"""Workspace layout and application-session intelligence for Hyprland."""
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

DATA = Path.home()/".local/share/ai-dock/workspace-sessions.json"
APP_LAUNCHERS = {
 "brave-browser":["brave","--profile-directory=Default"], "firefox":["firefox"],
 "code":["gtk-launch","code.desktop"], "obsidian":["gtk-launch","obsidian.desktop"],
 "org.kde.dolphin":["gtk-launch","org.kde.dolphin.desktop"], "kitty":["kitty"],
 "Alacritty":["alacritty"], "spotify":["gtk-launch","spotify-launcher.desktop"],
}
TOOLS = [
 {"name":"workspace_summary","description":"Summarize every Hyprland workspace and the applications/windows currently on it.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"session_save","description":"Save the current application-to-workspace layout as a named session.","inputSchema":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"],"additionalProperties":False}},
 {"name":"session_list","description":"List saved workspace/application sessions.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"session_restore","description":"Restore a saved layout by moving matching open windows back to their workspaces and optionally reopening missing known applications.","inputSchema":{"type":"object","properties":{"name":{"type":"string"},"launch_missing":{"type":"boolean"}},"required":["name"],"additionalProperties":False}},
 {"name":"session_delete","description":"Delete a saved workspace session.","inputSchema":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"],"additionalProperties":False}},
 {"name":"focus_session","description":"Move all windows except the active window and AI Dock from the current workspace to a holding workspace for distraction-free focus.","inputSchema":{"type":"object","properties":{"holding_workspace":{"type":"string"}},"additionalProperties":False}},
]
def result(text): return {"content":[{"type":"text","text":str(text)}]}
def clients(): return json.loads(subprocess.check_output(["hyprctl","clients","-j"],text=True))
def active(): return json.loads(subprocess.check_output(["hyprctl","activewindow","-j"],text=True))
def load():
 try: return json.loads(DATA.read_text())
 except (OSError,ValueError): return {}
def save(value):
 DATA.parent.mkdir(parents=True,exist_ok=True); temp=DATA.with_suffix(".tmp"); temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n"); temp.replace(DATA)
def clean(value):
 name=" ".join(str(value).strip().split())
 if not name or len(name)>80: raise ValueError("Session name must contain 1-80 characters")
 return name
def move(window,workspace):
 address=window.get("address");
 if address: subprocess.run(["hyprctl","dispatch",f'hl.dsp.window.move({{ window = "address:{address}", workspace = "{workspace}", follow = false }})'],check=True,stdout=subprocess.DEVNULL)
def important(window):
 return window.get("mapped",True) and window.get("class") not in ("io.github.yogesh.AIDock","") and window.get("workspace",{}).get("name") not in (None,"")
def call(name,args):
 if name=="workspace_summary":
  groups={}
  for item in clients():
   if important(item): groups.setdefault(str(item.get("workspace",{}).get("name")),[]).append(f"{item.get('class')} · {item.get('title')}")
  def key(item):
   return (0,int(item[0])) if item[0].isdigit() else (1,item[0])
  return result("\n\n".join(f"WORKSPACE {workspace}\n"+"\n".join(f"• {label}" for label in labels) for workspace,labels in sorted(groups.items(),key=key)) or "No mapped windows found.")
 sessions=load()
 if name=="session_save":
  session=clean(args["name"]); windows=[]
  for item in clients():
   if important(item): windows.append({"class":item.get("class"),"title":item.get("title"),"workspace":str(item.get("workspace",{}).get("name"))})
  sessions[session]={"created":datetime.now().isoformat(timespec="seconds"),"windows":windows}; save(sessions)
  return result(f"Saved workspace session: {session} · {len(windows)} windows")
 if name=="session_list": return result("\n".join(f"{key} · {len(value.get('windows',[]))} windows · {value.get('created','')}" for key,value in sorted(sessions.items())) or "No workspace sessions saved.")
 if name=="session_delete":
  session=clean(args["name"])
  if session not in sessions: raise ValueError(f"Session not found: {session}")
  del sessions[session]; save(sessions); return result(f"Deleted workspace session: {session}")
 if name=="session_restore":
  session=clean(args["name"])
  if session not in sessions: raise ValueError(f"Session not found: {session}")
  current=clients(); moved=[]; missing=[]; used=set()
  for target in sessions[session].get("windows",[]):
   match=next((item for item in current if item.get("address") not in used and item.get("class")==target.get("class") and (item.get("title")==target.get("title") or target.get("class") in APP_LAUNCHERS)),None)
   if match:
    move(match,target["workspace"]); used.add(match.get("address")); moved.append(f"{target.get('class')} → w{target['workspace']}")
   else: missing.append(target)
  launched=[]
  if args.get("launch_missing",False):
   for target in missing:
    command=APP_LAUNCHERS.get(target.get("class"))
    if command:
     before={item.get("address") for item in clients()}; subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
     for _ in range(30):
      new=next((item for item in clients() if item.get("address") not in before and item.get("class")==target.get("class")),None)
      if new: move(new,target["workspace"]); launched.append(f"{target.get('class')} → w{target['workspace']}"); break
      time.sleep(.1)
  return result(f"Restored session {session}\nMoved: {len(moved)}\nLaunched: {len(launched)}\nStill missing: {len(missing)-len(launched)}\n"+"\n".join(moved+launched))
 if name=="focus_session":
  holding=str(args.get("holding_workspace","9")).strip()
  if not re.fullmatch(r"[1-9][0-9]*|special:[a-z0-9_-]+",holding): raise ValueError("Invalid holding workspace")
  current=active(); workspace=str(current.get("workspace",{}).get("name")); address=current.get("address"); moved=[]
  for item in clients():
   if important(item) and str(item.get("workspace",{}).get("name"))==workspace and item.get("address")!=address:
    move(item,holding); moved.append(item.get("title") or item.get("class"))
  return result(f"Focus session ready on workspace {workspace}. Moved {len(moved)} other windows to {holding}: "+"; ".join(moved))
 raise ValueError(f"Unknown workspace tool: {name}")
for raw in sys.stdin:
 message={}
 try:
  message=json.loads(raw); rid=message.get("id")
  if rid is None: continue
  method=message.get("method")
  if method=="initialize": response={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"AI Dock Workspace Sessions","version":"1.0"}}
  elif method=="tools/list": response={"tools":TOOLS}
  elif method=="tools/call":
   params=message.get("params",{}); response=call(params.get("name"),params.get("arguments",{}))
  else: raise ValueError(f"Unsupported MCP method: {method}")
  reply={"jsonrpc":"2.0","id":rid,"result":response}
 except Exception as error: reply={"jsonrpc":"2.0","id":message.get("id"),"error":{"code":-32000,"message":str(error)}}
 print(json.dumps(reply,separators=(",",":")),flush=True)
