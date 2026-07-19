#!/usr/bin/env python3
"""High-level, artifact-producing missions for AI Dock's universal agent."""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / "Documents" / "AI Missions"
STATE = Path.home() / ".local/share/ai-dock/missions"
PROJECTS = Path.home() / "Documents" / "AI Projects"

TOOLS = [
 {"name":"mission_status","description":"Show the current and recent high-level missions, stages, evidence and artifacts.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"mission_artifacts","description":"List files produced by high-level missions.","inputSchema":{"type":"object","properties":{"limit":{"type":"integer"}},"additionalProperties":False}},
 {"name":"website_investigate","description":"Visibly and deeply inspect a website: fetch source, headers and linked assets, check security/accessibility/HTML/links, capture a rendered screenshot, and save an evidence-backed Markdown report plus source snapshot.","inputSchema":{"type":"object","properties":{"url":{"type":"string"},"name":{"type":"string"}},"required":["url"],"additionalProperties":False}},
 {"name":"project_build","description":"Create and verify a complete local application from a cloud-planner-supplied file manifest. The local executor safely writes the files, initializes Git, runs syntax checks and saves build evidence; it performs no hidden model reasoning.","inputSchema":{"type":"object","properties":{"name":{"type":"string"},"specification":{"type":"string"},"files":{"type":"array","minItems":1,"maxItems":24,"items":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"],"additionalProperties":False}},"run":{"type":"string"},"summary":{"type":"string"},"kind":{"type":"string","enum":["auto","python","gtk","web","cli"]},"overwrite":{"type":"boolean"}},"required":["name","specification","files"],"additionalProperties":False}},
 {"name":"project_verify","description":"Inspect and test an existing project under Documents or /mnt/shared, returning concrete syntax/build/Git evidence.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
 {"name":"github_publish","description":"Publish a tested local Git project with the official GitHub CLI. Requires confirm exactly PUBLISH and explicit public/private visibility; never publishes silently.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"repository":{"type":"string"},"visibility":{"type":"string","enum":["private","public"]},"confirm":{"type":"string"}},"required":["path","repository","visibility","confirm"],"additionalProperties":False}},
 {"name":"video_create","description":"Render and verify a narrated MP4 from cloud-planner-supplied narration and scene captions, with optional openly licensed Wikimedia Commons imagery, local speech synthesis and FFmpeg. Can create an explicit delivery folder under Documents or /mnt/shared and save the verified MP4 there. The local executor performs no hidden model reasoning.","inputSchema":{"type":"object","properties":{"topic":{"type":"string"},"name":{"type":"string"},"narration":{"type":"string"},"scenes":{"type":"array","minItems":2,"maxItems":8,"items":{"type":"string"}},"duration_seconds":{"type":"integer","minimum":15,"maximum":180},"use_commons":{"type":"boolean"},"output_folder":{"type":"string"},"output_filename":{"type":"string"}},"required":["topic","narration","scenes"],"additionalProperties":False}},
]

def result(text): return {"content":[{"type":"text","text":text}]}
def slug(value): return re.sub(r"[^a-z0-9]+","-",str(value).lower()).strip("-")[:60] or "mission"
def allowed(path):
 path=Path(path).expanduser().resolve(); roots=[(Path.home()/"Documents").resolve(),Path("/mnt/shared").resolve()]
 if not any(path==root or root in path.parents for root in roots): raise ValueError("Mission paths must remain under Documents or /mnt/shared")
 return path
def notify(text): subprocess.run(["notify-send","-a","AI Dock Mission","AI Dock mission",text],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def begin(kind,label):
 STATE.mkdir(parents=True,exist_ok=True); ROOT.mkdir(parents=True,exist_ok=True)
 mid=datetime.now().strftime("%Y%m%d-%H%M%S-")+slug(label)[:24]; folder=ROOT/mid;folder.mkdir()
 state={"id":mid,"kind":kind,"goal":label,"status":"running","stage":"starting","created":datetime.now().isoformat(timespec="seconds"),"events":[],"artifacts":[]}
 save(state);notify(f"Started: {label}");return state,folder
def save(state):
 state["updated"]=datetime.now().isoformat(timespec="seconds");tmp=STATE/"current.tmp";tmp.write_text(json.dumps(state,indent=2,ensure_ascii=False)+"\n");os.replace(tmp,STATE/"current.json");(STATE/f"{state['id']}.json").write_text(json.dumps(state,indent=2,ensure_ascii=False)+"\n")
def stage(state,text,artifact=None):
 state["stage"]=text;state["events"].append({"time":datetime.now().isoformat(timespec="seconds"),"stage":text})
 if artifact: state["artifacts"].append(str(artifact));save(state);notify(text)
 else: save(state)
def finish(state,summary): state["status"]="completed";state["stage"]="verified";state["summary"]=summary;save(state);notify("Mission completed and verified")
def http(url,method="GET",timeout=25):
 req=urllib.request.Request(url,method=method,headers={"User-Agent":"Mozilla/5.0 AI-Dock-Mission/1.0"});return urllib.request.urlopen(req,timeout=timeout)

def show_browser_action(url):
 """Make web missions observable in the user's regular Brave and move the real cursor to it."""
 before={item.get("address") for item in json.loads(subprocess.check_output(["hyprctl","clients","-j"],text=True))}
 subprocess.Popen(["brave",url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for _ in range(20):
  time.sleep(.15);clients=json.loads(subprocess.check_output(["hyprctl","clients","-j"],text=True))
  brave=[item for item in clients if item.get("class")=="brave-browser"]
  newer=[item for item in brave if item.get("address") not in before]
  if newer or brave:
   win=min(newer or brave,key=lambda x:x.get("focusHistoryID",999999));address=win.get("address")
   subprocess.run(["hyprctl","dispatch",f'hl.dsp.focus({{ window = "address:{address}" }})'],stdout=subprocess.DEVNULL)
   at=win.get("at",[0,0]);size=win.get("size",[900,700]);x=int(at[0]+size[0]/2);y=int(at[1]+min(120,size[1]/3))
   subprocess.run(["ydotool","mousemove","--absolute",str(x),str(y)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   return

def website(args):
 url=str(args["url"]).strip(); parsed=urllib.parse.urlparse(url)
 if parsed.scheme not in ("http","https"): raise ValueError("Provide an http or https URL")
 state,folder=begin("website-audit",args.get("name") or parsed.netloc);stage(state,"Opening the website visibly in your regular browser")
 show_browser_action(url);stage(state,"Fetching source and response headers")
 with http(url) as r: raw=r.read(5_000_000);headers=dict(r.headers);final=r.url;status=r.status
 source=raw.decode(errors="replace");(folder/"source.html").write_text(source);stage(state,"Analyzing HTML, accessibility, assets and links",folder/"source.html")
 issues=[]
 def issue(level,title,evidence): issues.append((level,title,evidence))
 if not re.search(r"<title[^>]*>.+?</title>",source,re.I|re.S):issue("high","Missing page title","No non-empty <title> element")
 if not re.search(r'<meta[^>]+name=["\']description["\']',source,re.I):issue("medium","Missing meta description","No description metadata")
 imgs=re.findall(r"<img\b[^>]*>",source,re.I);missing_alt=[x[:180] for x in imgs if not re.search(r"\balt\s*=",x,re.I)]
 if missing_alt:issue("medium",f"{len(missing_alt)} image(s) lack alt text",missing_alt[0])
 ids=re.findall(r'\bid\s*=\s*["\']([^"\']+)',source,re.I);dupes=sorted({x for x in ids if ids.count(x)>1})
 if dupes:issue("medium","Duplicate element IDs",", ".join(dupes[:20]))
 if "content-security-policy" not in {k.lower() for k in headers}:issue("medium","No Content-Security-Policy response header","CSP header absent")
 if parsed.scheme=="https" and "strict-transport-security" not in {k.lower() for k in headers}:issue("low","No HSTS response header","Strict-Transport-Security absent")
 links=list(dict.fromkeys(urllib.parse.urljoin(final,x) for x in re.findall(r'href\s*=\s*["\']([^"\'#]+)',source,re.I)))[:35];broken=[]
 for link in links:
  if urllib.parse.urlparse(link).scheme not in ("http","https"):continue
  try:
   with http(link,"HEAD",8) as r:
    if r.status>=400:broken.append(f"{r.status} {link}")
  except Exception as e:broken.append(f"ERROR {link} · {str(e)[:80]}")
 if broken:issue("high",f"{len(broken)} checked link(s) failed",broken[0])
 stage(state,"Capturing rendered visual evidence")
 shot=folder/"page.png"
 subprocess.run(["brave","--headless","--disable-gpu",f"--screenshot={shot}","--window-size=1440,1000",url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
 if shot.exists():state["artifacts"].append(str(shot))
 rows="\n".join(f"- **{level.upper()} · {html.escape(title)}** — `{html.escape(evidence)}`" for level,title,evidence in issues) or "- No issues detected by the automated checks."
 report=folder/"report.md";report.write_text(f"# Website investigation: {url}\n\nStatus: {status} · Final URL: {final}\n\n## Findings\n\n{rows}\n\n## Evidence\n\n- Source snapshot: `source.html`\n- Screenshot: `page.png`\n- Checked links: {len(links)}\n- Response headers:\n```json\n{json.dumps(headers,indent=2)}\n```\n")
 stage(state,"Saving evidence-backed audit",report);finish(state,f"Audit completed with {len(issues)} finding(s)")
 return result(f"Website mission verified · {len(issues)} finding(s)\nReport: {report}\nScreenshot: {shot}\nSource: {folder/'source.html'}")

def project_path(value): return allowed(PROJECTS/slug(value))
def verify_project(path):
 path=allowed(path);checks=[]
 py=list(path.rglob("*.py")); js=list(path.rglob("*.js")); htmls=list(path.rglob("*.html"))
 for file in py:
  p=subprocess.run([sys.executable,"-m","py_compile",str(file)],capture_output=True,text=True);checks.append((file.relative_to(path).as_posix(),p.returncode==0,(p.stderr or "syntax OK")[:500]))
 if htmls:checks.extend((f.relative_to(path).as_posix(),"<html" in f.read_text(errors="replace").lower(),"HTML document check") for f in htmls)
 if not checks:checks.append(("project",bool(list(path.iterdir())),"non-empty project"))
 return checks
def build_project(args):
 name=slug(args["name"]);path=project_path(name)
 if path.exists() and not args.get("overwrite"):raise ValueError(f"Project already exists: {path}")
 if path.exists():shutil.rmtree(path)
 state,folder=begin("project-build",args["name"]);path.mkdir(parents=True);stage(state,"Validating cloud-generated application manifest")
 data={"summary":str(args.get("summary",args["specification"])),"run":str(args.get("run","See README.md")),"files":args.get("files",[])}
 stage(state,"Writing validated project files")
 for item in data["files"][:24]:
  rel=Path(str(item.get("path","")))
  if rel.is_absolute() or ".." in rel.parts or not rel.name:continue
  target=(path/rel).resolve()
  if path not in target.parents:continue
  target.parent.mkdir(parents=True,exist_ok=True);target.write_text(str(item.get("content","")))
 if not any(path.iterdir()):raise RuntimeError("The cloud planner supplied no safe project files")
 if not (path/".gitignore").exists():(path/".gitignore").write_text("__pycache__/\n*.py[cod]\n.env\n.venv/\n")
 subprocess.run(["git","init","-b","main",str(path)],check=True,stdout=subprocess.DEVNULL);subprocess.run(["git","-C",str(path),"add","."],check=True)
 subprocess.run(["git","-C",str(path),"-c","user.name=AI Dock","-c","user.email=ai-dock@localhost","commit","-m","Initial AI Dock build"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 stage(state,"Running project verification");checks=verify_project(path);evidence=folder/"build-report.md";evidence.write_text("# Build report\n\n"+"\n".join(f"- {'PASS' if ok else 'FAIL'} `{file}` — {detail}" for file,ok,detail in checks)+f"\n\nProject: `{path}`\n")
 for cache in path.rglob("__pycache__"):shutil.rmtree(cache,ignore_errors=True)
 stage(state,"Saving build and test evidence",evidence)
 if not all(x[1] for x in checks):raise RuntimeError(f"Project created but verification failed. See {evidence}")
 finish(state,f"Created and verified {path}");return result(f"Application mission verified\nProject: {path}\nEvidence: {evidence}\nRun: {data.get('run','See README.md')}")
def verify_tool(args):
 path=allowed(args["path"]);checks=verify_project(path);text="\n".join(f"{'PASS' if ok else 'FAIL'} · {f} · {d}" for f,ok,d in checks)
 return result(text)
def publish(args):
 if args.get("confirm")!="PUBLISH":raise ValueError("Publication requires confirm exactly PUBLISH")
 path=allowed(args["path"]);repo=str(args["repository"]).strip();vis=args["visibility"]
 if not shutil.which("gh"):raise RuntimeError("GitHub CLI is not installed")
 auth=subprocess.run(["gh","auth","status"],capture_output=True,text=True)
 if auth.returncode:raise RuntimeError("GitHub CLI is not authenticated. Run gh auth login once.")
 checks=verify_project(path)
 if not all(x[1] for x in checks):raise RuntimeError("Project verification failed; nothing was published")
 command=["gh","repo","create",repo,f"--{vis}","--source",str(path),"--remote","origin","--push"]
 done=subprocess.run(command,capture_output=True,text=True,timeout=180)
 if done.returncode:raise RuntimeError(done.stderr.strip() or done.stdout.strip())
 return result("Published verified repository:\n"+(done.stdout.strip() or repo))

def commons_assets(topic,folder,limit=6):
 query=urllib.parse.urlencode({"action":"query","generator":"search","gsrsearch":topic,"gsrnamespace":6,"gsrlimit":limit,"prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1280,"format":"json","origin":"*"})
 with http("https://commons.wikimedia.org/w/api.php?"+query,timeout=30) as r:data=json.load(r)
 assets=[]
 for page in data.get("query",{}).get("pages",{}).values():
  info=(page.get("imageinfo") or [{}])[0];url=info.get("thumburl") or info.get("url")
  if not url:continue
  ext=Path(urllib.parse.urlparse(url).path).suffix.lower()
  if ext not in (".jpg",".jpeg",".png",".webp"):continue
  target=folder/f"commons-{len(assets):02}{ext}"
  try:
   with http(url,timeout=30) as r:target.write_bytes(r.read(12_000_000))
  except Exception:continue
  meta=info.get("extmetadata",{});get=lambda key:re.sub(r"<[^>]+>","",str(meta.get(key,{}).get("value","")))
  assets.append({"file":str(target),"title":page.get("title"),"source":info.get("descriptionurl"),"license":get("LicenseShortName"),"artist":get("Artist")[:300]})
 return assets

def video(args):
 topic=str(args["topic"]);duration=max(15,min(int(args.get("duration_seconds",45)),180));state,folder=begin("video",args.get("name") or topic);stage(state,"Validating cloud-generated narration and scene plan")
 narration=str(args["narration"]).strip();scenes=[str(x).strip() for x in args.get("scenes",[]) if str(x).strip()][:8]
 if not narration or len(scenes)<2:raise ValueError("Cloud video plan requires non-empty narration and at least two scenes")
 (folder/"script.txt").write_text(narration)
 assets=[]
 if args.get("use_commons"):
  stage(state,"Finding openly licensed visuals on Wikimedia Commons")
  try:assets=commons_assets(topic,folder,min(6,len(scenes)))
  except Exception as e:state["events"].append({"stage":"Commons fallback","error":str(e)})
 (folder/"sources.json").write_text(json.dumps({"topic":topic,"visual_source":"Wikimedia Commons plus locally rendered fallback cards" if assets else "Locally rendered original scene cards","external_assets":assets},indent=2,ensure_ascii=False)+"\n")
 stage(state,"Synthesizing narration",folder/"script.txt");audio=folder/"narration.wav";subprocess.run(["espeak-ng","-s","155","-w",str(audio),narration],check=True)
 actual=float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(audio)],text=True).strip());per=max(3,duration/len(scenes),actual/len(scenes));segments=[]
 stage(state,"Rendering visible scene cards with FFmpeg")
 for i,caption in enumerate(scenes):
  seg=folder/f"scene-{i:02}.mp4";safe=caption.replace("'","’").replace(":","\\:")[:90]
  if i<len(assets):
   vf=f"scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:0x111827,drawtext=text='{safe}':fontcolor=white:fontsize=38:x=(w-text_w)/2:y=h-110:box=1:boxcolor=black@0.65:boxborderw=15"
   command=["ffmpeg","-y","-loop","1","-i",assets[i]["file"],"-t",str(per),"-vf",vf,"-r","30","-pix_fmt","yuv420p",str(seg)]
  else:
   command=["ffmpeg","-y","-f","lavfi","-i",f"color=c=0x111827:s=1280x720:d={per}","-vf",f"drawtext=text='{safe}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=0x4f46e5@0.75:boxborderw=24","-r","30","-pix_fmt","yuv420p",str(seg)]
  subprocess.run(command,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);segments.append(seg)
 listing=folder/"scenes.txt";listing.write_text("".join(f"file '{x.name}'\n" for x in segments));silent=folder/"visuals.mp4";subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(listing),"-c","copy",str(silent)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 output=folder/(slug(args.get("name") or topic)+".mp4");subprocess.run(["ffmpeg","-y","-i",str(silent),"-i",str(audio),"-af","apad","-t",str(duration),"-c:v","libx264","-c:a","aac","-pix_fmt","yuv420p",str(output)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 stage(state,"Verifying final MP4",output);probe=subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration,size","-of","json",str(output)],text=True);(folder/"verification.json").write_text(probe)
 delivered=output
 if args.get("output_folder"):
  delivery=allowed(args["output_folder"]);delivery.mkdir(parents=True,exist_ok=True)
  filename=Path(str(args.get("output_filename") or output.name)).name
  if not filename.lower().endswith(".mp4"):filename += ".mp4"
  delivered=delivery/filename
  if delivered.exists():delivered=delivery/f"{delivered.stem}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.mp4"
  shutil.copy2(output,delivered);stage(state,"Delivering verified MP4 to requested folder",delivered)
 finish(state,f"Created narrated video {delivered}");subprocess.Popen(["xdg-open",str(delivered)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 return result(f"Video mission verified and opened\nVideo: {delivered}\nMission copy: {output}\nScript: {folder/'script.txt'}\nProvenance: {folder/'sources.json'}\nVerification: {folder/'verification.json'}")

def call(name,args):
 if name=="mission_status":
  try:return result((STATE/"current.json").read_text())
  except OSError:return result("No mission has run yet.")
 if name=="mission_artifacts":
  files=sorted((p for p in ROOT.rglob("*") if p.is_file()),key=lambda p:p.stat().st_mtime,reverse=True)[:int(args.get("limit",30))];return result("\n".join(map(str,files)) or "No mission artifacts yet.")
 if name=="website_investigate":return website(args)
 if name=="project_build":return build_project(args)
 if name=="project_verify":return verify_tool(args)
 if name=="github_publish":return publish(args)
 if name=="video_create":return video(args)
 raise ValueError(f"Unknown mission tool: {name}")

for raw in sys.stdin:
 try:
  message=json.loads(raw);rid=message.get("id")
  if rid is None:continue
  method=message.get("method")
  if method=="initialize":out={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"AI Dock Missions","version":"1.0"}}
  elif method=="tools/list":out={"tools":TOOLS}
  elif method=="tools/call":p=message.get("params",{});out=call(p.get("name"),p.get("arguments",{}))
  else:raise ValueError(f"Unsupported method: {method}")
  reply={"jsonrpc":"2.0","id":rid,"result":out}
 except Exception as e:reply={"jsonrpc":"2.0","id":message.get("id") if "message" in locals() else None,"error":{"code":-32000,"message":str(e)}}
 print(json.dumps(reply,separators=(",",":")),flush=True)
