#!/usr/bin/env python3
"""Fast backend file, search, clipboard, conversion, and batch-operation tools."""
import hashlib, json, mimetypes, os, re, shutil, subprocess, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DATA=Path.home()/'.local/share/ai-dock/operations';DATA.mkdir(parents=True,exist_ok=True)
CLIPBOARD_HISTORY=DATA/'clipboard-history.json';SNIPPETS=DATA/'snippets.json'

TOOLS=[
 {"name":"find_files","description":"Find files and folders by fuzzy name, extension, type, size, and modification age.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"query":{"type":"string"},"extension":{"type":"string"},"kind":{"type":"string","enum":["any","file","folder"]},"modified_days":{"type":"integer","minimum":0},"limit":{"type":"integer","minimum":1,"maximum":500}},"additionalProperties":False}},
 {"name":"search_file_contents","description":"Fast recursive text or regex search with file names and line numbers.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"query":{"type":"string"},"regex":{"type":"boolean"},"limit":{"type":"integer","minimum":1,"maximum":500}},"required":["query"],"additionalProperties":False}},
 {"name":"recent_files","description":"List recently modified files under a folder.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":200}},"additionalProperties":False}},
 {"name":"largest_files","description":"Find the largest files under a folder to understand storage usage.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":200}},"additionalProperties":False}},
 {"name":"storage_map","description":"Summarize direct child folders by recursive size without changing anything.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"depth":{"type":"integer","minimum":1,"maximum":3}},"additionalProperties":False}},
 {"name":"duplicate_files","description":"Find exact duplicate files using size grouping and SHA-256; never deletes them.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"minimum_bytes":{"type":"integer","minimum":1},"limit":{"type":"integer","minimum":1,"maximum":100}},"additionalProperties":False}},
 {"name":"file_metadata","description":"Inspect file type, MIME, size, timestamps, checksum, media metadata, image dimensions, or PDF information.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
 {"name":"checksum","description":"Calculate SHA-256, SHA-1, or MD5 for a file.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"algorithm":{"type":"string","enum":["sha256","sha1","md5"]}},"required":["path"],"additionalProperties":False}},
 {"name":"clipboard_read","description":"Read the current Wayland clipboard text.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"clipboard_write","description":"Replace the current Wayland clipboard with supplied text.","inputSchema":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"],"additionalProperties":False}},
 {"name":"clipboard_capture","description":"Capture the current clipboard text into private durable AI Dock clipboard history, deduplicated and capped at 100 entries.","inputSchema":{"type":"object","properties":{"label":{"type":"string"}},"additionalProperties":False}},
 {"name":"clipboard_history","description":"List recent durable clipboard history entries with IDs and previews.","inputSchema":{"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":100}},"additionalProperties":False}},
 {"name":"clipboard_restore","description":"Restore a clipboard history entry by ID to the current clipboard.","inputSchema":{"type":"object","properties":{"id":{"type":"string"}},"required":["id"],"additionalProperties":False}},
 {"name":"snippet_save","description":"Save or replace a named reusable text template containing {{variable}} placeholders.","inputSchema":{"type":"object","properties":{"name":{"type":"string"},"template":{"type":"string"}},"required":["name","template"],"additionalProperties":False}},
 {"name":"snippet_list","description":"List reusable saved text templates and their required placeholders.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"snippet_render","description":"Render a saved text template with variables and optionally copy the result to clipboard.","inputSchema":{"type":"object","properties":{"name":{"type":"string"},"variables":{"type":"object"},"copy":{"type":"boolean"}},"required":["name"],"additionalProperties":False}},
 {"name":"batch_rename_preview","description":"Preview batch renaming with find/replace, prefix, suffix, and numbering; changes nothing.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"find":{"type":"string"},"replace":{"type":"string"},"prefix":{"type":"string"},"suffix":{"type":"string"},"number":{"type":"boolean"}},"required":["path"],"additionalProperties":False}},
 {"name":"batch_rename_apply","description":"Apply a reviewed batch rename plan. Requires confirm exactly RENAME and refuses collisions.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"find":{"type":"string"},"replace":{"type":"string"},"prefix":{"type":"string"},"suffix":{"type":"string"},"number":{"type":"boolean"},"confirm":{"type":"string"}},"required":["path","confirm"],"additionalProperties":False}},
 {"name":"organize_preview","description":"Preview organizing files into extension, date, or category subfolders.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"strategy":{"type":"string","enum":["extension","month","category"]}},"required":["path","strategy"],"additionalProperties":False}},
 {"name":"organize_apply","description":"Apply reviewed file organization. Requires confirm exactly ORGANIZE; moves only files directly inside the folder.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"strategy":{"type":"string","enum":["extension","month","category"]},"confirm":{"type":"string"}},"required":["path","strategy","confirm"],"additionalProperties":False}},
 {"name":"extract_pdf_text","description":"Extract searchable text from a PDF into a new TXT file.","inputSchema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"}},"required":["source","destination"],"additionalProperties":False}},
 {"name":"convert_image","description":"Convert or resize an image into a new image using ImageMagick.","inputSchema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"},"width":{"type":"integer","minimum":1,"maximum":20000},"height":{"type":"integer","minimum":1,"maximum":20000},"quality":{"type":"integer","minimum":1,"maximum":100}},"required":["source","destination"],"additionalProperties":False}},
 {"name":"convert_media","description":"Convert local audio or video into a new file with FFmpeg.","inputSchema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"},"audio_only":{"type":"boolean"}},"required":["source","destination"],"additionalProperties":False}},
 {"name":"sync_preview","description":"Preview an rsync copy/synchronization between folders without changing anything.","inputSchema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"},"delete_extra":{"type":"boolean"}},"required":["source","destination"],"additionalProperties":False}},
 {"name":"sync_apply","description":"Apply an rsync folder synchronization after review. Requires confirm exactly SYNC.","inputSchema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"},"delete_extra":{"type":"boolean"},"confirm":{"type":"string"}},"required":["source","destination","confirm"],"additionalProperties":False}},
]
def result(v): return {"content":[{"type":"text","text":str(v)}]}
def safe(v,exists=False):
 raw=str(v or Path.home()).strip();aliases={'/home/yogesh/documents':'/home/yogesh/Documents','~/documents':'/home/yogesh/Documents','/home/yogesh/downloads':'/home/yogesh/Downloads','~/downloads':'/home/yogesh/Downloads','/home/yogesh/desktop':'/home/yogesh/Desktop','~/desktop':'/home/yogesh/Desktop','/home/yogesh/pictures':'/home/yogesh/Pictures','~/pictures':'/home/yogesh/Pictures','/home/yogesh/videos':'/home/yogesh/Videos','~/videos':'/home/yogesh/Videos','/home/yogesh/music':'/home/yogesh/Music','~/music':'/home/yogesh/Music'}
 lower=raw.lower()
 for alias,real in aliases.items():
  if lower==alias or lower.startswith(alias+'/'):raw=real+raw[len(alias):];break
 p=Path(raw).expanduser().resolve(); roots=(Path.home().resolve(),Path('/mnt/shared').resolve())
 if not any(p==r or r in p.parents for r in roots): raise ValueError('Path must be under home or /mnt/shared')
 if exists and not p.exists(): raise ValueError(f'Path not found: {p}')
 return p
def run(c,timeout=120):
 p=subprocess.run(c,capture_output=True,text=True,timeout=timeout); out=(p.stdout+'\n'+p.stderr).strip()
 if p.returncode: raise RuntimeError(out or f'Command failed: {c[0]}')
 return out
def load_json(path,default):
 try:
  value=json.loads(path.read_text());return value if isinstance(value,type(default)) else default
 except (OSError,ValueError):return default
def save_json(path,value):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n');temp.replace(path)
def human(n):
 for u in ('B','KiB','MiB','GiB','TiB'):
  if n<1024:return f'{n:.1f} {u}'
  n/=1024
def items(folder): return sorted(folder.iterdir(),key=lambda p:p.name.lower())
def rename_plan(a):
 folder=safe(a['path'],True)
 if not folder.is_dir(): raise ValueError('Choose a folder')
 plan=[]
 for i,p in enumerate(items(folder),1):
  stem=p.stem.replace(a.get('find',''),a.get('replace','')) if a.get('find') else p.stem
  stem=f"{a.get('prefix','')}{i:03d}-"*(bool(a.get('number'))) + (stem if not a.get('number') else '') + a.get('suffix','')
  if a.get('number'): stem=f"{a.get('prefix','')}{i:03d}-{p.stem.replace(a.get('find',''),a.get('replace','')) if a.get('find') else p.stem}{a.get('suffix','')}"
  dest=p.with_name(stem+p.suffix)
  if dest!=p: plan.append((p,dest))
 return plan
def category(p):
 e=p.suffix.lower(); groups={'Images':{'.jpg','.jpeg','.png','.gif','.webp','.svg'},'Videos':{'.mp4','.mkv','.webm','.mov'},'Audio':{'.mp3','.wav','.flac','.ogg','.m4a'},'Documents':{'.pdf','.txt','.md','.doc','.docx','.odt'},'Data':{'.csv','.json','.jsonl','.db','.sqlite'},'Archives':{'.zip','.tar','.gz','.7z','.rar'},'Code':{'.c','.h','.cpp','.py','.js','.ts','.java','.html','.css'}}
 return next((k for k,v in groups.items() if e in v),'Other')
def organize_plan(a):
 folder=safe(a['path'],True); strategy=a['strategy']; plan=[]
 for p in items(folder):
  if not p.is_file(): continue
  target=(p.suffix.lower().lstrip('.') or 'no-extension') if strategy=='extension' else datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m') if strategy=='month' else category(p)
  plan.append((p,folder/target/p.name))
 return plan
def call(n,a):
 if n=='find_files':
  root=safe(a.get('path'),True); q=a.get('query','').lower(); ext=a.get('extension','').lower().lstrip('.'); kind=a.get('kind','any'); days=a.get('modified_days'); found=[]; now=datetime.now().timestamp()
  for p in root.rglob('*'):
   try:
    if q and q not in p.name.lower(): continue
    if ext and p.suffix.lower()!=f'.{ext}':continue
    if kind=='file' and not p.is_file():continue
    if kind=='folder' and not p.is_dir():continue
    if days is not None and now-p.stat().st_mtime>int(days)*86400:continue
    found.append(str(p))
    if len(found)>=int(a.get('limit',100)):break
   except OSError: pass
  return result('\n'.join(found) or 'No matching paths.')
 if n=='search_file_contents':
  root=safe(a.get('path'),True); cmd=['rg','--line-number','--color=never','--max-count',str(a.get('limit',100))]
  if not a.get('regex'):cmd.append('--fixed-strings')
  cmd.extend([a['query'],str(root)]); p=subprocess.run(cmd,capture_output=True,text=True,timeout=60); return result('\n'.join(p.stdout.splitlines()[:int(a.get('limit',100))]) or 'No matches.')
 if n in ('recent_files','largest_files'):
  root=safe(a.get('path'),True); values=[]
  for p in root.rglob('*'):
   try:
    if p.is_file(): values.append((p.stat().st_mtime if n=='recent_files' else p.stat().st_size,p))
   except OSError:pass
  values.sort(reverse=True); return result('\n'.join(f"{datetime.fromtimestamp(v):%Y-%m-%d %H:%M} · {p}" if n=='recent_files' else f"{human(v)} · {p}" for v,p in values[:int(a.get('limit',30))]))
 if n=='storage_map':
  root=safe(a.get('path'),True); vals=[]
  for p in items(root):
   try: size=p.stat().st_size if p.is_file() else sum(x.stat().st_size for x in p.rglob('*') if x.is_file())
   except OSError:size=0
   vals.append((size,p))
  return result('\n'.join(f'{human(s)} · {p}' for s,p in sorted(vals,reverse=True)))
 if n=='duplicate_files':
  root=safe(a.get('path'),True); groups=defaultdict(list)
  for p in root.rglob('*'):
   try:
    if p.is_file() and p.stat().st_size>=int(a.get('minimum_bytes',1)):groups[p.stat().st_size].append(p)
   except OSError:pass
  hashes=defaultdict(list)
  for size,paths in groups.items():
   if len(paths)>1:
    for p in paths:
     try: hashes[(size,hashlib.sha256(p.read_bytes()).hexdigest())].append(p)
     except OSError:pass
  dup=[v for v in hashes.values() if len(v)>1][:int(a.get('limit',50))]; return result('\n\n'.join(f'{human(g[0].stat().st_size)} each\n'+'\n'.join(map(str,g)) for g in dup) or 'No exact duplicates found.')
 if n=='file_metadata':
  p=safe(a['path'],True); st=p.stat(); info={'path':str(p),'size':st.st_size,'mime':mimetypes.guess_type(p)[0],'modified':datetime.fromtimestamp(st.st_mtime).isoformat(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None}
  if p.suffix.lower()=='.pdf': info['pdfinfo']=run(['pdfinfo',str(p)])
  elif p.is_file():
   probe=subprocess.run(['ffprobe','-v','quiet','-print_format','json','-show_format','-show_streams',str(p)],capture_output=True,text=True,timeout=30)
   if probe.returncode==0 and probe.stdout.strip():info['media']=json.loads(probe.stdout)
  return result(json.dumps(info,indent=2,ensure_ascii=False))
 if n=='checksum':
  p=safe(a['path'],True); h=hashlib.new(a.get('algorithm','sha256'))
  with p.open('rb') as f:
   for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
  return result(f'{h.name}: {h.hexdigest()}  {p}')
 if n=='clipboard_read': return result(run(['wl-paste','--no-newline']))
 if n=='clipboard_write': subprocess.run(['wl-copy'],input=a['text'],text=True,check=True); return result('Clipboard updated.')
 if n=='clipboard_capture':
  text=run(['wl-paste','--no-newline']);history=load_json(CLIPBOARD_HISTORY,[]);digest=hashlib.sha256(text.encode()).hexdigest()[:12]
  history=[x for x in history if x.get('id')!=digest];history.insert(0,{'id':digest,'time':datetime.now().isoformat(timespec='seconds'),'label':str(a.get('label',''))[:80],'text':text});save_json(CLIPBOARD_HISTORY,history[:100]);return result(f'Captured clipboard as {digest} · {len(text)} characters')
 if n=='clipboard_history':
  history=load_json(CLIPBOARD_HISTORY,[])[:int(a.get('limit',20))];return result('\n'.join(f"{x['id']} · {x.get('time','')} · {x.get('label','')} · {x.get('text','')[:100].replace(chr(10),' ')}" for x in history) or 'Clipboard history is empty.')
 if n=='clipboard_restore':
  history=load_json(CLIPBOARD_HISTORY,[]);entry=next((x for x in history if x.get('id')==a['id']),None)
  if not entry:raise ValueError('Clipboard history ID not found')
  subprocess.run(['wl-copy'],input=entry['text'],text=True,check=True);return result(f"Restored clipboard entry {a['id']}.")
 if n=='snippet_save':
  name=' '.join(a['name'].split())[:80]
  if not name:raise ValueError('Snippet needs a name')
  snippets=load_json(SNIPPETS,{});snippets[name]={'template':a['template'],'updated':datetime.now().isoformat(timespec='seconds')};save_json(SNIPPETS,snippets);return result(f'Saved text template: {name}')
 if n=='snippet_list':
  snippets=load_json(SNIPPETS,{});return result('\n'.join(f"{name} · variables: {', '.join(sorted(set(re.findall(r'{{\\s*([a-zA-Z0-9_-]+)\\s*}}',item['template'])))) or 'none'}" for name,item in sorted(snippets.items())) or 'No text templates saved.')
 if n=='snippet_render':
  snippets=load_json(SNIPPETS,{})
  if a['name'] not in snippets:raise ValueError('Text template not found')
  text=snippets[a['name']]['template']
  for key,value in a.get('variables',{}).items():text=re.sub(r'{{\s*'+re.escape(str(key))+r'\s*}}',str(value),text)
  missing=sorted(set(re.findall(r'{{\s*([a-zA-Z0-9_-]+)\s*}}',text)))
  if missing:raise ValueError('Missing template variables: '+', '.join(missing))
  if a.get('copy'):subprocess.run(['wl-copy'],input=text,text=True,check=True)
  return result(text+('\n\nCopied to clipboard.' if a.get('copy') else ''))
 if n.startswith('batch_rename_'):
  plan=rename_plan(a); preview='\n'.join(f'{x.name} → {y.name}' for x,y in plan) or 'Nothing to rename.'
  if n.endswith('preview'):return result(preview)
  if a.get('confirm')!='RENAME':raise ValueError('Preview first, then set confirm exactly RENAME')
  if any(y.exists() and y!=x for x,y in plan):raise ValueError('Rename collision detected; nothing changed')
  for x,y in plan:x.rename(y)
  return result(f'Renamed {len(plan)} items.\n{preview}')
 if n.startswith('organize_'):
  plan=organize_plan(a); preview='\n'.join(f'{x.name} → {y.parent.name}/' for x,y in plan) or 'Nothing to organize.'
  if n.endswith('preview'):return result(preview)
  if a.get('confirm')!='ORGANIZE':raise ValueError('Preview first, then set confirm exactly ORGANIZE')
  for x,y in plan:
   y.parent.mkdir(parents=True,exist_ok=True)
   if y.exists():raise ValueError(f'Collision: {y}')
   x.rename(y)
  return result(f'Organized {len(plan)} files.')
 if n in ('extract_pdf_text','convert_image','convert_media'):
  s=safe(a['source'],True);d=safe(a['destination']);d.parent.mkdir(parents=True,exist_ok=True)
  if d.exists():raise ValueError(f'Destination exists: {d}')
  if n=='extract_pdf_text':run(['pdftotext',str(s),str(d)])
  elif n=='convert_image':
   cmd=['magick',str(s)]; w,h=a.get('width'),a.get('height')
   if w or h:cmd+=['-resize',f'{w or ""}x{h or ""}']
   if a.get('quality'):cmd+=['-quality',str(a['quality'])]
   run(cmd+[str(d)])
  else:run(['ffmpeg','-nostdin','-i',str(s),'-vn']+[str(d)] if a.get('audio_only') else ['ffmpeg','-nostdin','-i',str(s),str(d)],600)
  return result(f'Created {d} · {human(d.stat().st_size)}')
 if n in ('sync_preview','sync_apply'):
  s=safe(a['source'],True);d=safe(a['destination']); cmd=['rsync','-a','--itemize-changes']
  if n=='sync_preview':cmd.append('--dry-run')
  elif a.get('confirm')!='SYNC':raise ValueError('Preview first, then set confirm exactly SYNC')
  if a.get('delete_extra'):cmd.append('--delete')
  return result(run(cmd+[str(s)+'/',str(d)+'/']) or ('No differences.' if n=='sync_preview' else 'Folders synchronized.'))
 raise ValueError(f'Unknown operations tool: {n}')
for raw in sys.stdin:
 m={}
 try:
  m=json.loads(raw);rid=m.get('id');
  if rid is None:continue
  method=m.get('method');response={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"AI Dock Operations","version":"1.0"}} if method=='initialize' else {"tools":TOOLS} if method=='tools/list' else call(m['params']['name'],m['params'].get('arguments',{})) if method=='tools/call' else (_ for _ in ()).throw(ValueError('Unsupported MCP method'))
  reply={"jsonrpc":"2.0","id":rid,"result":response}
 except Exception as e:reply={"jsonrpc":"2.0","id":m.get('id'),"error":{"code":-32000,"message":str(e)}}
 print(json.dumps(reply,separators=(',',':')),flush=True)
