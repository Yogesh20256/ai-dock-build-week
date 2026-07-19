#!/usr/bin/env python3
"""Fast OCR, media, recording, network, Bluetooth, and notification MCP."""
import json
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DATA=Path.home()/".local/share/ai-dock/media"; DATA.mkdir(parents=True,exist_ok=True)
REC_PID=DATA/"recording.pid"
TOOLS=[
 {"name":"ocr_screen","description":"Capture the full screen or active window and extract visible text locally with Tesseract OCR; faster than sending an image to a model.","inputSchema":{"type":"object","properties":{"target":{"type":"string","enum":["screen","active_window"]},"language":{"type":"string"}},"additionalProperties":False}},
 {"name":"media_status","description":"Show the current media player, title, artist, playback state, position, and volume.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"media_control","description":"Control media playback: play, pause, play-pause, next, previous, stop, seek, or set volume.","inputSchema":{"type":"object","properties":{"action":{"type":"string","enum":["play","pause","play-pause","next","previous","stop","seek"]},"seconds":{"type":"integer","minimum":-3600,"maximum":3600},"volume":{"type":"integer","minimum":0,"maximum":100}},"additionalProperties":False}},
 {"name":"screen_record_start","description":"Start recording the desktop to a timestamped MP4 file. Recording continues until screen_record_stop.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"audio":{"type":"boolean"}},"additionalProperties":False}},
 {"name":"screen_record_stop","description":"Stop the active AI Dock screen recording and return the saved file path.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"screen_record_status","description":"Check whether AI Dock screen recording is active.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"network_status","description":"Show active network connections, Wi-Fi radio/state, and IP addresses without changing anything.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"bluetooth_status","description":"Show Bluetooth controller status and connected devices without changing anything.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"desktop_notify","description":"Display a local desktop notification with a title and message.","inputSchema":{"type":"object","properties":{"title":{"type":"string"},"message":{"type":"string"}},"required":["title","message"],"additionalProperties":False}},
]
def result(text): return {"content":[{"type":"text","text":str(text)}]}
def run(command,timeout=20):
 p=subprocess.run(command,capture_output=True,text=True,timeout=timeout); return p.returncode,(p.stdout+("\n" if p.stdout and p.stderr else "")+p.stderr).strip()
def recording():
 try:
  info=json.loads(REC_PID.read_text()); os.kill(int(info["pid"]),0); return info
 except (OSError,ValueError,KeyError,json.JSONDecodeError): return None
def safe_record_path(value):
 if value: path=Path(str(value)).expanduser().resolve()
 else: path=Path.home()/"Videos"/f"AI-Dock-{datetime.now():%Y%m%d-%H%M%S}.mp4"
 home=Path.home().resolve(); shared=Path('/mnt/shared').resolve()
 if not (home in path.parents or shared in path.parents): raise ValueError("Recording path must be under home or /mnt/shared")
 if path.suffix.lower() not in (".mp4",".mkv"): path=path.with_suffix(".mp4")
 path.parent.mkdir(parents=True,exist_ok=True); return path
def call(name,args):
 if name=="ocr_screen":
  image=DATA/"ocr-screen.png"; target=args.get("target","screen")
  if target=="active_window":
   active=json.loads(subprocess.check_output(["hyprctl","activewindow","-j"],text=True)); at=active.get("at",[0,0]); size=active.get("size",[0,0]); geometry=f"{at[0]},{at[1]} {size[0]}x{size[1]}"; subprocess.run(["grim","-g",geometry,str(image)],check=True)
  else: subprocess.run(["grim",str(image)],check=True)
  code,text=run(["tesseract",str(image),"stdout","-l",str(args.get("language","eng")),"--psm","6"],60)
  if code: raise RuntimeError(text)
  return result(f"OCR {target} · {image}\n\n{text or '(no readable text detected)'}")
 if name=="media_status":
  fields="{{status}}\n{{artist}} — {{title}}\nPlayer: {{playerName}}\nPosition: {{position}} / {{mpris:length}}\nVolume: {{volume}}"
  code,text=run(["playerctl","metadata","--format",fields])
  return result(text if code==0 else "No active MPRIS media player.")
 if name=="media_control":
  if "volume" in args: command=["playerctl","volume",f"{int(args['volume'])/100:.2f}"]
  else:
   action=args.get("action","play-pause"); command=["playerctl",action]
   if action=="seek": command.append(f"{int(args.get('seconds',10)):+d}")
  code,text=run(command); 
  if code: raise RuntimeError(text or "Media control failed")
  return result(f"Media command completed: {' '.join(command[1:])}")
 if name=="screen_record_start":
  if recording(): raise ValueError("A screen recording is already active")
  path=safe_record_path(args.get("path")); command=["wf-recorder","-f",str(path)]
  if args.get("audio"): command.extend(["--audio"])
  process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=(DATA/"recording.log").open("w"),start_new_session=True)
  REC_PID.write_text(json.dumps({"pid":process.pid,"path":str(path),"started":datetime.now().isoformat(timespec="seconds")})+"\n")
  return result(f"Screen recording started: {path}")
 if name=="screen_record_stop":
  info=recording()
  if not info: raise ValueError("No AI Dock screen recording is active")
  os.kill(int(info["pid"]),signal.SIGINT)
  try: REC_PID.unlink()
  except OSError: pass
  return result(f"Screen recording stopped: {info['path']}")
 if name=="screen_record_status":
  info=recording(); return result(json.dumps(info,indent=2) if info else "No AI Dock screen recording is active.")
 if name=="network_status":
  _c,connections=run(["nmcli","-t","-f","NAME,TYPE,DEVICE,STATE","connection","show","--active"]); _c,radio=run(["nmcli","radio","all"]); _c,ip=run(["ip","-brief","address"])
  return result(f"ACTIVE CONNECTIONS\n{connections}\n\nRADIOS\n{radio}\n\nADDRESSES\n{ip}")
 if name=="bluetooth_status":
  _c,show=run(["bluetoothctl","show"]); _c,devices=run(["bluetoothctl","devices","Connected"]); return result(f"CONTROLLER\n{show}\n\nCONNECTED\n{devices or 'No connected Bluetooth devices.'}")
 if name=="desktop_notify": subprocess.run(["notify-send","-a","AI Dock",str(args["title"]),str(args["message"])],check=True); return result("Notification displayed.")
 raise ValueError(f"Unknown media tool: {name}")
for raw in sys.stdin:
 message={}
 try:
  message=json.loads(raw); rid=message.get("id")
  if rid is None: continue
  method=message.get("method")
  if method=="initialize": response={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"AI Dock Media and OCR","version":"1.0"}}
  elif method=="tools/list": response={"tools":TOOLS}
  elif method=="tools/call":
   params=message.get("params",{}); response=call(params.get("name"),params.get("arguments",{}))
  else: raise ValueError(f"Unsupported MCP method: {method}")
  reply={"jsonrpc":"2.0","id":rid,"result":response}
 except Exception as error: reply={"jsonrpc":"2.0","id":message.get("id"),"error":{"code":-32000,"message":str(error)}}
 print(json.dumps(reply,separators=(",",":")),flush=True)
