#!/usr/bin/env python3
"""General, bounded system capabilities for AI Dock on CachyOS/Hyprland."""
import json, os, re, shutil, subprocess, sys, tarfile, zipfile
from pathlib import Path

HOME=Path.home().resolve(); SHARED=Path('/mnt/shared').resolve()
ROOTS=(HOME,SHARED)
TOOLS=[
 {"name":"system_overview","description":"Inspect OS, kernel, CPU, memory, disks, desktop session and uptime.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"file_list","description":"List files and folders at an allowed path with sizes and modification times.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"recursive":{"type":"boolean"}},"required":["path"],"additionalProperties":False}},
 {"name":"file_read","description":"Read a local text file from home or /mnt/shared, up to 200000 characters.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
 {"name":"file_create","description":"Create a new empty or text file under home or /mnt/shared. Refuses to overwrite an existing file.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path"],"additionalProperties":False}},
 {"name":"file_write","description":"Create, replace, or append a text file under home or /mnt/shared. Creates parent folders.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"},"mode":{"type":"string","enum":["replace","append"]}},"required":["path","content"],"additionalProperties":False}},
 {"name":"file_copy_move","description":"Copy or move a file or folder between allowed locations.","inputSchema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"},"operation":{"type":"string","enum":["copy","move"]}},"required":["source","destination","operation"],"additionalProperties":False}},
 {"name":"file_trash","description":"Move a file or folder to the desktop trash so it can be restored. Never permanently deletes.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
 {"name":"archive_manage","description":"Create or extract ZIP/TAR archives at allowed paths.","inputSchema":{"type":"object","properties":{"action":{"type":"string","enum":["create_zip","extract"]},"source":{"type":"string"},"destination":{"type":"string"}},"required":["action","source","destination"],"additionalProperties":False}},
 {"name":"process_list","description":"List running user processes, optionally filtered by name.","inputSchema":{"type":"object","properties":{"filter":{"type":"string"}},"additionalProperties":False}},
 {"name":"process_stop","description":"Gracefully stop one user-owned process by numeric PID, then verify it stopped.","inputSchema":{"type":"object","properties":{"pid":{"type":"integer","minimum":2}},"required":["pid"],"additionalProperties":False}},
 {"name":"service_manage","description":"Inspect, start, stop, restart, enable or disable a named systemd user or system service. System scope may request authentication.","inputSchema":{"type":"object","properties":{"service":{"type":"string"},"action":{"type":"string","enum":["status","start","stop","restart","enable","disable"]},"scope":{"type":"string","enum":["user","system"]}},"required":["service","action"],"additionalProperties":False}},
 {"name":"git_manage","description":"Inspect status/log/diff or perform pull/fetch/add/commit in an existing Git repository under allowed paths.","inputSchema":{"type":"object","properties":{"repository":{"type":"string"},"action":{"type":"string","enum":["status","log","diff","fetch","pull","add_all","commit"]},"message":{"type":"string"}},"required":["repository","action"],"additionalProperties":False}},
 {"name":"app_discover","description":"Find installed desktop applications matching a human-friendly name and return their launch identifiers.","inputSchema":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"],"additionalProperties":False}},
 {"name":"diagnostic_command","description":"Run one read-only diagnostic command from an allowlist: ls, find, rg, cat, head, tail, du, df, free, uname, lspci, lsusb, ip, ss, systemctl, journalctl, pacman, git. No shell syntax.","inputSchema":{"type":"object","properties":{"command":{"type":"array","items":{"type":"string"},"minItems":1,"maxItems":30}},"required":["command"],"additionalProperties":False}},
 {"name":"compile_and_run_c","description":"Compile a C source file using gcc and execute the binary. Confined to home folder. Returns compilation and execution results.","inputSchema":{"type":"object","properties":{"source_file":{"type":"string","description":"Absolute or relative path to the C source file"},"compiler_flags":{"type":"array","items":{"type":"string"},"description":"Optional list of compiler flags, e.g. ['-lm', '-Wall']"}},"required":["source_file"],"additionalProperties":False}},
 {"name":"get_system_resources","description":"Retrieve live system resources including CPU load, RAM usage, CPU temperature, and uptime.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"manage_wifi","description":"Get current Wi-Fi status, scan networks, or connect to a Wi-Fi network.","inputSchema":{"type":"object","properties":{"action":{"type":"string","enum":["status","scan","connect"]},"ssid":{"type":"string","description":"SSID of network to connect to"},"password":{"type":"string","description":"Password of network to connect to"}},"required":["action"],"additionalProperties":False}},
]

def path(value,must=False):
 raw=str(value).strip()
 home_aliases={f'~/{name.lower()}':str(HOME/name) for name in ('Documents','Downloads','Desktop','Pictures','Videos','Music')}
 for name in ('Documents','Downloads','Desktop','Pictures','Videos','Music'): home_aliases[f'{str(HOME).lower()}/{name.lower()}']=str(HOME/name)
 lowered=raw.lower()
 for alias,real in home_aliases.items():
  if lowered==alias or lowered.startswith(alias+'/'):
   raw=real+raw[len(alias):]; break
 p=Path(raw).expanduser().resolve(strict=False)
 if not any(p==r or r in p.parents for r in ROOTS): raise ValueError('Path must stay inside home or /mnt/shared')
 if must and not p.exists(): raise ValueError(f'Path does not exist: {p}')
 return p
def out(cmd,timeout=60,cwd=None):
 r=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout,cwd=cwd)
 text=(r.stdout+r.stderr).strip()
 if r.returncode: raise RuntimeError(text[-5000:] or f'Command failed: {cmd[0]}')
 return text[-20000:]
def call(name,a):
 if name=='system_overview': return out(['bash','-lc','printf "OS: "; cat /etc/os-release | grep PRETTY_NAME; uname -a; uptime; free -h; df -h / /mnt/shared 2>/dev/null; printf "SESSION: %s %s\\n" "$XDG_CURRENT_DESKTOP" "$XDG_SESSION_TYPE"'])
 if name=='file_list':
  p=path(a['path'],True); depth=[] if a.get('recursive') else ['-maxdepth','1']
  return out(['find',str(p),*depth,'-printf','%y\t%s\t%TY-%Tm-%Td %TH:%TM\t%p\n'])
 if name=='file_read':
  p=path(a['path'],True)
  if not p.is_file() or p.stat().st_size>2_000_000: raise ValueError('Not a readable text-sized file')
  return p.read_text(errors='replace')[:200000]
 if name=='file_create':
  p=path(a['path'])
  if p.exists(): raise ValueError(f'File already exists; it was not overwritten: {p}')
  p.parent.mkdir(parents=True,exist_ok=True); content=str(a.get('content',''))
  p.write_text(content); return f'Created file: {p} ({len(content)} characters)'
 if name=='file_write':
  p=path(a['path']); p.parent.mkdir(parents=True,exist_ok=True); mode='a' if a.get('mode')=='append' else 'w'
  with p.open(mode) as f:f.write(str(a['content']))
  return f'Wrote {len(str(a["content"]))} characters to {p}'
 if name=='file_copy_move':
  s,d=path(a['source'],True),path(a['destination']); d.parent.mkdir(parents=True,exist_ok=True)
  if a['operation']=='move': shutil.move(str(s),str(d))
  elif s.is_dir(): shutil.copytree(s,d,dirs_exist_ok=True)
  else: shutil.copy2(s,d)
  if not d.exists(): raise RuntimeError('Destination verification failed')
  return f'{a["operation"].title()} completed: {s} -> {d}'
 if name=='file_trash':
  p=path(a['path'],True); out(['gio','trash',str(p)]); return f'Moved to Trash: {p}'
 if name=='archive_manage':
  s,d=path(a['source'],True),path(a['destination']); d.parent.mkdir(parents=True,exist_ok=True)
  if a['action']=='create_zip':
   with zipfile.ZipFile(d,'w',zipfile.ZIP_DEFLATED) as z:
    items=s.rglob('*') if s.is_dir() else [s]
    for x in items:
     if x.is_file(): z.write(x,x.relative_to(s.parent))
  else:
   d.mkdir(parents=True,exist_ok=True)
   if zipfile.is_zipfile(s):
    with zipfile.ZipFile(s) as z:z.extractall(d)
   elif tarfile.is_tarfile(s):
    with tarfile.open(s) as t:t.extractall(d,filter='data')
   else: raise ValueError('Unsupported archive')
  return f'Archive action completed: {d}'
 if name=='process_list':
  text=out(['ps','-u',str(os.getuid()),'-o','pid,etimes,%cpu,%mem,comm,args','--sort=-%cpu']); q=str(a.get('filter','')).lower()
  return '\n'.join(x for x in text.splitlines() if not q or q in x.lower())[:20000]
 if name=='process_stop':
  pid=int(a['pid']); owner=out(['ps','-o','uid=','-p',str(pid)]).strip()
  if owner!=str(os.getuid()): raise ValueError('Can stop only user-owned processes')
  os.kill(pid,15); return f'Sent graceful stop to PID {pid}'
 if name=='service_manage':
  service=str(a['service']); action=a['action']; scope=a.get('scope','user')
  if not re.fullmatch(r'[A-Za-z0-9@_.:-]+',service): raise ValueError('Invalid service name')
  cmd=['systemctl','--user'] if scope=='user' else (['systemctl'] if action=='status' else ['pkexec','systemctl'])
  return out([*cmd,action,service],180)
 if name=='git_manage':
  repo=path(a['repository'],True); action=a['action']; commands={'status':['status','--short','--branch'],'log':['log','-10','--oneline'],'diff':['diff'],'fetch':['fetch','--all','--prune'],'pull':['pull','--ff-only'],'add_all':['add','-A']}
  cmd=commands.get(action)
  if action=='commit':
   msg=str(a.get('message','')).strip()
   if not msg: raise ValueError('Commit message required')
   cmd=['commit','-m',msg]
  return out(['git',*cmd],300,repo)
 if name=='app_discover':
  q=str(a['query']).lower(); results=[]
  for root in (Path('/usr/share/applications'),HOME/'.local/share/applications'):
   for f in root.glob('*.desktop'):
    text=f.read_text(errors='ignore')
    if q in (f.name+' '+text).lower():
     title=re.search(r'^Name=(.+)$',text,re.M); results.append(f'{title.group(1) if title else f.stem} | {f.name}')
  return '\n'.join(results[:50]) or 'No matching desktop application found'
 if name=='diagnostic_command':
  cmd=[str(x) for x in a['command']]; allowed={'ls','find','rg','cat','head','tail','du','df','free','uname','lspci','lsusb','ip','ss','systemctl','journalctl','pacman','git'}
  if cmd[0] not in allowed or any(any(c in x for c in ';|&`$<>\n') for x in cmd): raise ValueError('Command is not in the read-only diagnostic allowlist')
  return out(cmd,120)
 if name=='compile_and_run_c':
  src=path(a['source_file'],True); bin=src.with_suffix('.bin')
  flags=a.get('compiler_flags',[])
  compile_out=out(['gcc',*flags,str(src),'-o',str(bin)])
  run_out=out([str(bin)])
  return f'Compilation: {compile_out}\nExecution: {run_out}'
 if name=='get_system_resources':
  load=out(['uptime']).split('load average:')[1].strip()
  mem=out(['free','-h']).splitlines()[1].split()[1:3]
  temp=out(['cat','/sys/class/thermal/thermal_zone0/temp'])
  return f'Load: {load}, RAM: {mem[1]}/{mem[0]}, Temp: {int(temp)/1000}°C'
 if name=='manage_wifi':
  act=a['action']
  if act=='status': return out(['nmcli','-t','-f','DEVICE,STATE,SSID','dev','wifi'])
  if act=='scan': return out(['nmcli','-t','-f','SSID,SIGNAL,BARS','dev','wifi','list'])
  if act=='connect':
   cmd=['nmcli','device','wifi','connect',a['ssid']]
   if a.get('password'): cmd.extend(['password',a['password']])
   return out(cmd)
 raise ValueError('Unknown system tool')
for raw in sys.stdin:
 try:
  m=json.loads(raw); i=m.get('id'); method=m.get('method')
  if i is None:continue
  if method=='initialize':r={'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'AI Dock System','version':'1.0'}}
  elif method=='tools/list':r={'tools':TOOLS}
  elif method=='tools/call':p=m.get('params',{});r={'content':[{'type':'text','text':call(p.get('name'),p.get('arguments',{}))}]}
  else:raise ValueError('Unsupported method')
  reply={'jsonrpc':'2.0','id':i,'result':r}
 except Exception as e:reply={'jsonrpc':'2.0','id':m.get('id') if 'm'in locals() else None,'error':{'code':-32000,'message':str(e)}}
 print(json.dumps(reply,separators=(',',':')),flush=True)
