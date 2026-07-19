#!/usr/bin/env python3
"""Persistent conditions, monitoring, notifications, and recipe triggers."""
import argparse, json, os, socket, subprocess, sys, urllib.request
from datetime import datetime
from pathlib import Path

DATA=Path.home()/'.local/share/ai-dock/monitor';DATA.mkdir(parents=True,exist_ok=True)
RULES=DATA/'rules.json';ACTIVITY=DATA/'activity.jsonl'
TOOLS=[
 {"name":"resource_snapshot","description":"Read CPU load, memory, disk, battery, temperatures, uptime, and top processes.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"network_diagnostics","description":"Inspect interfaces, routes, DNS, listening ports, established connections, and optional host reachability.","inputSchema":{"type":"object","properties":{"host":{"type":"string"}},"additionalProperties":False}},
 {"name":"process_find","description":"Find processes by fuzzy command/name with PID, CPU, memory, state, and elapsed time.","inputSchema":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"],"additionalProperties":False}},
 {"name":"service_failures","description":"List failed user and system services plus recent high-priority errors.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"disk_health","description":"Read SMART health for accessible physical disks and filesystem capacity without changing anything.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"website_check","description":"Check a URL status, latency, content type, final URL, and optional expected text.","inputSchema":{"type":"object","properties":{"url":{"type":"string"},"expected_text":{"type":"string"},"timeout":{"type":"integer","minimum":1,"maximum":30}},"required":["url"],"additionalProperties":False}},
 {"name":"monitor_rule_create","description":"Create an automatic background trigger for new files, folder changes, low disk space, high memory, process state, or website availability. It can notify and optionally run a saved recipe.","inputSchema":{"type":"object","properties":{"name":{"type":"string"},"kind":{"type":"string","enum":["new_file","folder_changed","disk_free_below_gb","memory_above_percent","process_missing","process_running","website_down"]},"target":{"type":"string"},"threshold":{"type":"number"},"recipe":{"type":"string"},"notify":{"type":"boolean"},"cooldown_minutes":{"type":"integer","minimum":1,"maximum":10080}},"required":["name","kind","target"],"additionalProperties":False}},
 {"name":"monitor_rule_list","description":"List persistent background triggers and their latest state/result.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"monitor_rule_enable","description":"Enable or disable an existing background trigger.","inputSchema":{"type":"object","properties":{"name":{"type":"string"},"enabled":{"type":"boolean"}},"required":["name","enabled"],"additionalProperties":False}},
 {"name":"monitor_rule_delete","description":"Delete a persistent background trigger.","inputSchema":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"],"additionalProperties":False}},
 {"name":"monitor_check_now","description":"Evaluate every enabled background trigger immediately and run due actions.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"monitor_activity","description":"Read recent background trigger events and actions.","inputSchema":{"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":200}},"additionalProperties":False}},
]
def result(v):return {'content':[{'type':'text','text':str(v)}]}
def load():
 try:return json.loads(RULES.read_text())
 except (OSError,ValueError):return {}
def save(v):
 t=RULES.with_suffix('.tmp');t.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n');t.replace(RULES)
def log(name,status,detail):
 with ACTIVITY.open('a') as f:f.write(json.dumps({'time':datetime.now().isoformat(timespec='seconds'),'name':name,'status':status,'detail':str(detail)[:2000]},ensure_ascii=False)+'\n')
def run(cmd,timeout=30):
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout);return p.returncode,(p.stdout+'\n'+p.stderr).strip()
def safe(v):
 p=Path(v).expanduser().resolve();roots=(Path.home().resolve(),Path('/mnt/shared').resolve())
 if not any(p==r or r in p.parents for r in roots):raise ValueError('Path must be under home or /mnt/shared')
 return p
def web(url,expected='',timeout=10):
 if not url.startswith(('http://','https://')):url='https://'+url
 started=datetime.now();req=urllib.request.Request(url,headers={'User-Agent':'AI-Dock-Monitor/1.0'})
 try:
  with urllib.request.urlopen(req,timeout=timeout) as r:body=r.read(1024*1024).decode(errors='ignore');elapsed=(datetime.now()-started).total_seconds();ok=200<=r.status<400 and (not expected or expected.lower() in body.lower());return ok,f'{r.status} · {elapsed:.2f}s · {r.url} · {r.headers.get("Content-Type","")}'+(' · expected text found' if expected and ok else '')
 except Exception as e:return False,str(e)
def snapshot(rule):
 kind,target=rule['kind'],rule['target']
 if kind in ('new_file','folder_changed'):
  p=safe(target);current={str(x.relative_to(p)):x.stat().st_mtime_ns for x in p.rglob('*') if x.is_file()} if p.is_dir() else {}
  old=rule.get('snapshot',{});trigger=bool(old) and (set(current)-set(old) if kind=='new_file' else current!=old);detail=f'{len(current)} files; '+(f'{len(set(current)-set(old))} new' if kind=='new_file' else 'folder changed')
  return bool(trigger),detail,current
 if kind=='disk_free_below_gb':free=os.statvfs(safe(target));gb=free.f_bavail*free.f_frsize/1024**3;return gb<float(rule.get('threshold',5)),f'{gb:.2f} GiB free',gb
 if kind=='memory_above_percent':
  lines=Path('/proc/meminfo').read_text().splitlines();m={x.split(':')[0]:int(x.split()[1]) for x in lines};pct=(1-m['MemAvailable']/m['MemTotal'])*100;return pct>float(rule.get('threshold',90)),f'{pct:.1f}% memory used',pct
 if kind in ('process_missing','process_running'):
  code,out=run(['pgrep','-af',target]);present=code==0;return (not present if kind=='process_missing' else present),('running' if present else 'not running'),present
 if kind=='website_down':ok,detail=web(target,timeout=10);return not ok,detail,ok
 raise ValueError(f'Unknown rule kind: {kind}')
def check_all():
 rules=load();outputs=[];now=datetime.now()
 for name,rule in rules.items():
  if not rule.get('enabled',True):continue
  try:
   active,detail,state=snapshot(rule);was=rule.get('active',False);rule['snapshot']=state;rule['active']=active;rule['last_check']=now.isoformat(timespec='seconds');rule['last_result']=detail
   last=datetime.fromisoformat(rule['last_trigger']) if rule.get('last_trigger') else None;cooled=not last or (now-last).total_seconds()>=int(rule.get('cooldown_minutes',15))*60
   if active and (not was or cooled):
    rule['last_trigger']=now.isoformat(timespec='seconds');actions=[]
    if rule.get('notify',True):subprocess.run(['notify-send','-a','AI Dock Monitor',f'Trigger: {name}',detail]);actions.append('notified')
    if rule.get('recipe'):
     script=Path(__file__).with_name('automation_mcp_server.py');p=subprocess.run([sys.executable,str(script),'--run-recipe',rule['recipe']],capture_output=True,text=True,timeout=600);actions.append(('recipe completed' if p.returncode==0 else 'recipe failed')+': '+(p.stdout+p.stderr)[-1000:])
    log(name,'triggered',detail+' · '+'; '.join(actions));outputs.append(f'{name}: TRIGGERED · {detail}')
   else:outputs.append(f'{name}: {"ACTIVE" if active else "OK"} · {detail}')
  except Exception as e:rule['last_result']=f'error: {e}';log(name,'failed',e);outputs.append(f'{name}: FAILED · {e}')
 save(rules);return '\n'.join(outputs) or 'No monitor rules configured.'
def call(n,a):
 if n=='resource_snapshot':
  parts=[]
  for title,cmd in [('UPTIME',['uptime']),('MEMORY',['free','-h']),('FILESYSTEMS',['df','-h','-x','tmpfs','-x','devtmpfs']),('TEMPERATURES',['sensors']),('BATTERY',['upower','-i',subprocess.run(['upower','-e'],capture_output=True,text=True).stdout.splitlines()[-1] if subprocess.run(['upower','-e'],capture_output=True,text=True).stdout.splitlines() else '/']),('TOP PROCESSES',['ps','-eo','pid,comm,%cpu,%mem,etime','--sort=-%cpu'])]:
   _c,out=run(cmd);parts.append(title+'\n'+'\n'.join(out.splitlines()[:15]))
  return result('\n\n'.join(parts))
 if n=='network_diagnostics':
  parts=[]
  for title,cmd in [('INTERFACES',['ip','-brief','address']),('ROUTES',['ip','route']),('DNS',['resolvectl','status']),('LISTENING',['ss','-lntup']),('CONNECTIONS',['ss','-ntp','state','established'])]:_c,out=run(cmd);parts.append(title+'\n'+'\n'.join(out.splitlines()[:60]))
  if a.get('host'):_c,out=run(['ping','-c','2','-W','2',a['host']]);parts.append('REACHABILITY\n'+out)
  return result('\n\n'.join(parts))
 if n=='process_find':_c,out=run(['ps','-eo','pid,user,comm,%cpu,%mem,state,etime,args']);q=a['query'].lower();return result('\n'.join(x for x in out.splitlines() if q in x.lower()) or 'No matching process.')
 if n=='service_failures':
  parts=[]
  for cmd in (['systemctl','--failed','--no-pager'],['systemctl','--user','--failed','--no-pager'],['journalctl','-p','err','-n','50','--no-pager']):_c,out=run(cmd);parts.append(out)
  return result('\n\n'.join(parts))
 if n=='disk_health':
  _c,df=run(['df','-h']);_c,ls=run(['lsblk','-dn','-o','NAME,TYPE']);parts=[df]
  for line in ls.splitlines():
   name,typ=(line.split()+[''])[:2]
   if typ=='disk':_c,out=run(['smartctl','-H',f'/dev/{name}']);parts.append(f'/dev/{name}\n{out}')
  return result('\n\n'.join(parts))
 if n=='website_check':ok,detail=web(a['url'],a.get('expected_text',''),int(a.get('timeout',10)));return result(('PASS' if ok else 'FAIL')+' · '+detail)
 rules=load()
 if n=='monitor_rule_create':
  name=' '.join(a['name'].split())[:80]
  if not name:raise ValueError('Rule needs a name')
  if a['kind'] in ('new_file','folder_changed','disk_free_below_gb'):safe(a['target'])
  rules[name]={'kind':a['kind'],'target':a['target'],'threshold':a.get('threshold'),'recipe':a.get('recipe',''),'notify':a.get('notify',True),'cooldown_minutes':int(a.get('cooldown_minutes',15)),'enabled':True,'created':datetime.now().isoformat(timespec='seconds')};save(rules);check_all();return result(f'Created and initialized monitor rule: {name}')
 if n=='monitor_rule_list':return result(json.dumps(rules,indent=2,ensure_ascii=False) if rules else 'No monitor rules configured.')
 if n=='monitor_rule_enable':
  if a['name'] not in rules:raise ValueError('Rule not found')
  rules[a['name']]['enabled']=bool(a['enabled']);save(rules);return result(f"{a['name']} is {'enabled' if a['enabled'] else 'disabled'}.")
 if n=='monitor_rule_delete':
  if a['name'] not in rules:raise ValueError('Rule not found')
  del rules[a['name']];save(rules);return result(f"Deleted monitor rule: {a['name']}")
 if n=='monitor_check_now':return result(check_all())
 if n=='monitor_activity':
  try:lines=ACTIVITY.read_text().splitlines()[-int(a.get('limit',50)):]
  except OSError:lines=[]
  return result('\n'.join(lines) or 'No monitor activity.')
 raise ValueError(f'Unknown monitor tool: {n}')
def main():
 parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--check',action='store_true');args,_=parser.parse_known_args()
 if args.check:print(check_all());return
 for raw in sys.stdin:
  m={}
  try:
   m=json.loads(raw);rid=m.get('id');
   if rid is None:continue
   method=m.get('method');response={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"AI Dock Monitor","version":"1.0"}} if method=='initialize' else {"tools":TOOLS} if method=='tools/list' else call(m['params']['name'],m['params'].get('arguments',{})) if method=='tools/call' else (_ for _ in ()).throw(ValueError('Unsupported MCP method'))
   reply={"jsonrpc":"2.0","id":rid,"result":response}
  except Exception as e:reply={"jsonrpc":"2.0","id":m.get('id'),"error":{"code":-32000,"message":str(e)}}
  print(json.dumps(reply,separators=(',',':')),flush=True)
if __name__=='__main__':main()
