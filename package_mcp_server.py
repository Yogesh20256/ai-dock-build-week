#!/usr/bin/env python3
"""System-aware CachyOS software identity resolution and verified installation."""
import json, os, platform, re, shutil, subprocess, sys, time, urllib.parse, urllib.request, uuid
from pathlib import Path

DATA=Path.home()/'.local/share/ai-dock/packages';DATA.mkdir(parents=True,exist_ok=True)
RESOLUTIONS=DATA/'resolutions.json'
# Product identity overrides are deliberately about products, not arbitrary
# package aliases. They prevent famous names from resolving to unrelated AUR
# packages which happen to own the shortest name.
PRODUCTS={
 'antigravity':{'package':'antigravity-ide','names':['antigravity','antigravity ide','google antigravity'],'vendor':'Google','kind':'IDE'},
 'visual-studio-code-bin':{'package':'visual-studio-code-bin','names':['vs code','vscode','visual studio code'],'vendor':'Microsoft','kind':'IDE'},
 'google-chrome':{'package':'google-chrome','names':['chrome','google chrome'],'vendor':'Google','kind':'browser'},
 'brave-bin':{'package':'brave-bin','names':['brave','brave browser'],'vendor':'Brave','kind':'browser'},
 'obsidian':{'package':'obsidian','names':['obsidian'],'vendor':'Dynalist','kind':'notes'},
 'firefox':{'package':'firefox','names':['firefox'],'vendor':'Mozilla','kind':'browser'},
 'vlc':{'package':'vlc','names':['vlc','vlc media player'],'vendor':'VideoLAN','kind':'media player'},
}
TOOLS=[
 {"name":"system_software_profile","description":"Detect the actual operating system, architecture, desktop/session, package managers, repositories, sandbox formats, and installed-package counts before choosing software.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"software_discover","description":"Discover an installed application or package across desktop entries, pacman, AUR, Flatpak and executable paths using a human product name.","inputSchema":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"],"additionalProperties":False}},
 {"name":"software_research","description":"Research candidate packages for this exact CachyOS/Arch system using official repository metadata and the official AUR RPC, including descriptions, URLs, maintainers and installed state. Does not install.","inputSchema":{"type":"object","properties":{"product":{"type":"string"},"vendor":{"type":"string"},"website":{"type":"string"},"kind":{"type":"string"}},"required":["product"],"additionalProperties":False}},
 {"name":"software_resolve","description":"Resolve a human product request to one exact compatible package using system facts, installed apps, product identity, vendor/category hints and repository metadata. Produces a short-lived resolution ID; refuses ambiguous guesses.","inputSchema":{"type":"object","properties":{"product":{"type":"string"},"vendor":{"type":"string"},"website":{"type":"string"},"kind":{"type":"string"}},"required":["product"],"additionalProperties":False}},
 {"name":"software_install_resolved","description":"Install or update only the exact package from a previously reviewed software_resolve result, then verify package ownership, version, executables and desktop entries. A graphical authentication prompt may appear.","inputSchema":{"type":"object","properties":{"resolution_id":{"type":"string"}},"required":["resolution_id"],"additionalProperties":False}},
 {"name":"software_install_product","description":"System-aware one-command product installation/update: detect CachyOS and architecture, research identities and repositories, refuse ambiguity, select the exact product package, install after UI confirmation, and verify ownership/version/executables/desktop entries.","inputSchema":{"type":"object","properties":{"product":{"type":"string"},"vendor":{"type":"string"},"website":{"type":"string"},"kind":{"type":"string"}},"required":["product"],"additionalProperties":False}},
 {"name":"package_info","description":"Inspect an exact package identifier or known product and compare installed and available versions, source, URL, description, files and desktop entries.","inputSchema":{"type":"object","properties":{"package":{"type":"string"}},"required":["package"],"additionalProperties":False}},
 {"name":"package_version","description":"Return a concise installed and available version answer for an exact package identifier or known human product name.","inputSchema":{"type":"object","properties":{"package":{"type":"string"}},"required":["package"],"additionalProperties":False}},
 {"name":"package_search","description":"Search official CachyOS/Arch repositories and AUR metadata for candidates. For product installation, use software_resolve instead of choosing the shortest name.","inputSchema":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"],"additionalProperties":False}},
 {"name":"package_install_or_update","description":"Install/update one explicit package identifier or a built-in verified product identity. Human product requests should use software_resolve first. Verifies the result.","inputSchema":{"type":"object","properties":{"package":{"type":"string"}},"required":["package"],"additionalProperties":False}},
]
def run(cmd,timeout=60):return subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
def clean(v):
 value=' '.join(str(v).strip().split())
 if not value or len(value)>140 or any(c in value for c in ';|&`$<>\n'):raise ValueError('Invalid software name')
 return value
def norm(v):return re.sub(r'[^a-z0-9]+',' ',str(v).lower()).strip()
def product(v):
 n=norm(v)
 for item in PRODUCTS.values():
  if n in {norm(x) for x in item['names']} or n==norm(item['package']):return item
 return None
def source(pkg):
 if run(['pacman','-Si',pkg]).returncode==0:return 'official'
 if shutil.which('paru') and run(['paru','-Si',pkg],90).returncode==0:return 'AUR'
 return None
def pkg_info(pkg,src=None):
 src=src or source(pkg); cmd=['pacman','-Si',pkg] if src=='official' else ['paru','-Si',pkg] if src=='AUR' else None
 text=run(cmd,90).stdout if cmd else ''
 def field(name):
  m=re.search(rf'^{re.escape(name)}\s*:\s*(.+(?:\n\s+.+)*)$',text,re.M);return ' '.join(x.strip() for x in m.group(1).splitlines()) if m else ''
 local=run(['pacman','-Q',pkg]); files=run(['pacman','-Ql',pkg]).stdout.splitlines() if local.returncode==0 else []
 desktops=[line.split(None,1)[1] for line in files if line.endswith('.desktop')][:10]
 binaries=[line.split(None,1)[1] for line in files if '/usr/bin/' in line and not line.endswith('/')][:15]
 return {'package':pkg,'source':src or 'not found','installed':local.stdout.strip() if local.returncode==0 else 'not installed','available_version':field('Version') or 'unknown','description':field('Description'),'url':field('URL'),'maintainer':field('Maintainer'),'desktop_entries':desktops,'executables':binaries}
def candidates(query,limit=20):
 q=clean(query);names=[]
 for cmd,src in ((['pacman','-Ssq',q],'official'),(['paru','-Ssa',q],'AUR')):
  if cmd[0]=='paru' and not shutil.which('paru'):continue
  response=run(cmd,90)
  for line in response.stdout.splitlines():
   name=line.strip().split('/')[-1].split()[0]
   if re.fullmatch(r'[a-z0-9@._+:-]+',name) and (name,src) not in names:names.append((name,src))
 result=[]
 for name,src in names[:limit]:
  info=pkg_info(name,src);result.append(info)
 return result
def desktop_matches(query):
 q=norm(query);found=[]
 for root in (Path('/usr/share/applications'),Path.home()/'.local/share/applications'):
  if not root.is_dir():continue
  for p in root.glob('*.desktop'):
   text=p.read_text(errors='ignore');name=re.search(r'^Name=(.+)$',text,re.M);exe=re.search(r'^Exec=([^\n]+)',text,re.M);hay=norm((name.group(1) if name else '')+' '+p.stem)
   if all(word in hay for word in q.split()):found.append({'name':name.group(1) if name else p.stem,'desktop':str(p),'exec':exe.group(1) if exe else ''})
 return found[:30]
def os_profile():
 values={}
 for line in Path('/etc/os-release').read_text().splitlines():
  if '=' in line:
   k,v=line.split('=',1);values[k]=v.strip('"')
 return {'os':values.get('PRETTY_NAME'),'id':values.get('ID'),'id_like':values.get('ID_LIKE'),'architecture':platform.machine(),'kernel':platform.release(),'desktop':os.environ.get('XDG_CURRENT_DESKTOP'),'session':os.environ.get('XDG_SESSION_TYPE'),'package_managers':[x for x in ('pacman','paru','flatpak','snap') if shutil.which(x)],'installed_pacman_packages':len(run(['pacman','-Qq']).stdout.splitlines()),'foreign_packages':len(run(['pacman','-Qmq']).stdout.splitlines())}
def research(a):
 request=clean(a['product']);known=product(request);search=known['package'] if known else request
 exact=pkg_info(search) if known else None
 items=[exact] if exact and exact['source']!='not found' else candidates(search,30)
 # Official AUR RPC provides independent metadata and exact popularity/vote data.
 try:
  url='https://aur.archlinux.org/rpc/v5/search/'+urllib.parse.quote(search)
  with urllib.request.urlopen(url,timeout=12) as r:aur=json.load(r).get('results',[])[:15]
 except Exception as e:aur=[{'lookup_error':str(e)}]
 return {'system':os_profile(),'request':request,'known_identity':known,'installed_desktop_matches':desktop_matches(request),'repository_candidates':items,'aur_rpc':aur,'hints':{k:a.get(k,'') for k in ('vendor','website','kind')}}
def score(item,request,hints,known):
 n,p=norm(request),norm(item['package']);hay=norm(item['package']+' '+item.get('description','')+' '+item.get('url','')+' '+item.get('maintainer',''))
 value=0;reasons=[]
 if known and item['package']==known['package']:value+=1000;reasons.append('verified product identity mapping')
 if p==n:value+=120;reasons.append('exact package-name match')
 words=n.split();value+=sum(18 for w in words if w in p);value+=sum(5 for w in words if w in hay)
 for key,weight in (('vendor',40),('website',50),('kind',25)):
  hint=norm(hints.get(key,''))
  if hint and all(w in hay for w in hint.split()):value+=weight;reasons.append(f'{key} metadata match')
 if item.get('installed')!='not installed':value+=80;reasons.append('already installed')
 if item['source']=='official':value+=8
 return value,reasons
def resolve(a):
 report=research(a);request=report['request'];known=report['known_identity'];items=report['repository_candidates']
 if known and not any(x['package']==known['package'] for x in items):
  info=pkg_info(known['package']);
  if info['source']!='not found':items.insert(0,info)
 ranked=[]
 for item in items:
  points,reasons=score(item,request,a,known);ranked.append((points,item,reasons))
 ranked.sort(key=lambda x:x[0],reverse=True);top=ranked[0] if ranked else None;second=ranked[1] if len(ranked)>1 else None
 supplied_hint=any(str(a.get(key,'')).strip() for key in ('vendor','website','kind'))
 confident=bool(top and (
  'verified product identity mapping' in top[2]
  or 'already installed' in top[2]
  or ('exact package-name match' in top[2] and top[1]['source']=='official')
  or (supplied_hint and top[0]>=150 and (not second or top[0]-second[0]>=30))
 ))
 if not confident:
  summary=[{'score':s,'package':i['package'],'source':i['source'],'description':i['description'],'url':i['url']} for s,i,_r in ranked[:10]]
  return {'status':'ambiguous','request':request,'system':report['system'],'message':'No installation was selected. Add vendor, official website, category, or the exact package identifier.','candidates':summary}
 points,item,reasons=top;rid=uuid.uuid4().hex[:12];all_plans=load();all_plans[rid]={'created':time.time(),'request':request,'package':item['package'],'source':item['source'],'score':points,'reasons':reasons,'metadata':item};save(all_plans)
 return {'status':'resolved','resolution_id':rid,'expires_in_minutes':30,'request':request,'exact_package':item['package'],'source':item['source'],'installed':item['installed'],'available_version':item['available_version'],'description':item['description'],'url':item['url'],'evidence':reasons,'system':report['system'],'next_step':f'Review this identity, then call software_install_resolved with resolution_id {rid}.'}
def load():
 try:return json.loads(RESOLUTIONS.read_text())
 except (OSError,ValueError):return {}
def save(v):
 temp=RESOLUTIONS.with_suffix('.tmp');temp.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n');temp.replace(RESOLUTIONS)
def install(pkg,src):
 if source(pkg)!=src:raise ValueError('Package source changed or disappeared; resolve it again')
 if src=='official':cmd=['pkexec','pacman','-S','--needed','--noconfirm',pkg]
 else:cmd=['paru','--sudo','/usr/bin/pkexec','--sudoflags','','--skipreview','-S','--needed','--noconfirm',pkg]
 env=dict(os.environ);env.update({'NO_COLOR':'1','TERM':'dumb'});r=subprocess.run(cmd,text=True,capture_output=True,timeout=1800,env=env)
 if r.returncode:
  raw=re.sub(r'\x1b\[[0-9;?]*[A-Za-z]','',r.stderr or r.stdout);lines=[x for x in raw.splitlines() if x.strip() and not re.match(r'^\s*\d+\s+\d',x)];raise RuntimeError('\n'.join(lines[-25:]) or 'Package transaction failed or authentication was cancelled')
 info=pkg_info(pkg,src)
 if info['installed']=='not installed':raise RuntimeError('Post-install verification failed: pacman does not own the package')
 return info
def render(value):return value if isinstance(value,str) else json.dumps(value,indent=2,ensure_ascii=False)
def call(name,a):
 if name=='system_software_profile':return os_profile()
 if name=='software_discover':
  q=clean(a['query']);known=product(q);pkg=known['package'] if known else q;return {'system':os_profile(),'known_identity':known,'desktop_matches':desktop_matches(q),'exact_package':pkg_info(pkg),'repository_candidates':candidates(q,12),'executable':shutil.which(q)}
 if name=='software_research':return research(a)
 if name=='software_resolve':return resolve(a)
 if name=='software_install_resolved':
  plans=load();rid=str(a['resolution_id']);plan=plans.get(rid)
  if not plan:raise ValueError('Resolution ID not found; resolve the product again')
  if time.time()-float(plan['created'])>1800:raise ValueError('Resolution expired after 30 minutes; resolve the product again')
  before=plan['metadata'];after=install(plan['package'],plan['source']);plans.pop(rid,None);save(plans);return {'status':'installed_and_verified','requested_product':plan['request'],'exact_package':plan['package'],'source':plan['source'],'before':before['installed'],'after':after['installed'],'desktop_entries':after['desktop_entries'],'executables':after['executables'],'url':after['url']}
 if name=='software_install_product':
  decision=resolve(a)
  if decision.get('status')!='resolved':return decision
  plans=load();rid=decision['resolution_id'];plan=plans[rid];after=install(plan['package'],plan['source']);plans.pop(rid,None);save(plans)
  return {'status':'installed_and_verified','requested_product':plan['request'],'exact_package':plan['package'],'source':plan['source'],'identity_evidence':plan['reasons'],'before':plan['metadata']['installed'],'after':after['installed'],'description':after['description'],'url':after['url'],'desktop_entries':after['desktop_entries'],'executables':after['executables'],'system':os_profile()}
 if name=='package_info':
  raw=clean(a['package']);known=product(raw);return pkg_info(known['package'] if known else raw)
 if name=='package_version':
  raw=clean(a['package']);known=product(raw);info=pkg_info(known['package'] if known else raw)
  installed_version=info['installed'].split(' ',1)[1] if info['installed']!='not installed' and ' ' in info['installed'] else info['installed'];current=info['installed']!='not installed' and info['available_version']!='unknown' and info['installed'].endswith(' '+info['available_version'])
  return f"{raw}: installed version {installed_version}. Exact package: {info['package']} ({info['source']}). Available version: {info['available_version']}. {'It is up to date.' if current else 'It is not confirmed up to date.'}"
 if name=='package_search':return candidates(clean(a['query']),30)
 if name=='package_install_or_update':
  raw=clean(a['package']);known=product(raw);pkg=known['package'] if known else raw
  if not known and not re.fullmatch(r'[a-z0-9@._+:-]+',raw):raise ValueError('Human product names must use software_resolve first')
  src=source(pkg)
  if not src:raise ValueError(f'Exact package not found: {pkg}')
  return {'status':'installed_and_verified','requested':raw,**install(pkg,src)}
 raise ValueError('Unknown package tool')
for raw in sys.stdin:
 m={}
 try:
  m=json.loads(raw);rid=m.get('id')
  if rid is None:continue
  method=m.get('method');response={'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'AI Dock System-Aware Software','version':'2.0'}} if method=='initialize' else {'tools':TOOLS} if method=='tools/list' else {'content':[{'type':'text','text':render(call(m['params']['name'],m['params'].get('arguments',{})))}]} if method=='tools/call' else (_ for _ in ()).throw(ValueError('Unsupported MCP method'))
  reply={'jsonrpc':'2.0','id':rid,'result':response}
 except Exception as e:reply={'jsonrpc':'2.0','id':m.get('id'),'error':{'code':-32000,'message':str(e)}}
 print(json.dumps(reply,separators=(',',':')),flush=True)
