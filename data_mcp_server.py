#!/usr/bin/env python3
"""Structured local data inspection and transformation tools."""
import csv, hashlib, json, sqlite3, statistics, sys
from pathlib import Path

TOOLS=[
 {"name":"data_inspect","description":"Inspect CSV, JSON, JSONL, or SQLite data: shape, fields, types, and a small sample.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
 {"name":"data_validate","description":"Validate CSV, JSON, or JSONL syntax and report precise errors without changing the file.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
 {"name":"json_format","description":"Pretty-print or minify a JSON file into a new file.","inputSchema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"},"style":{"type":"string","enum":["pretty","compact"]}},"required":["source","destination"],"additionalProperties":False}},
 {"name":"data_convert","description":"Convert CSV, JSON array, or JSONL records to CSV, JSON, or JSONL in a new file.","inputSchema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"}},"required":["source","destination"],"additionalProperties":False}},
 {"name":"data_filter","description":"Filter structured records by a field and comparison into a new file.","inputSchema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"},"field":{"type":"string"},"operator":{"type":"string","enum":["equals","contains","gt","gte","lt","lte"]},"value":{}},"required":["source","destination","field","operator","value"],"additionalProperties":False}},
 {"name":"data_sort","description":"Sort structured records by a field into a new file.","inputSchema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"},"field":{"type":"string"},"descending":{"type":"boolean"}},"required":["source","destination","field"],"additionalProperties":False}},
 {"name":"data_deduplicate","description":"Remove duplicate structured records by selected fields into a new file.","inputSchema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"},"fields":{"type":"array","items":{"type":"string"}}},"required":["source","destination"],"additionalProperties":False}},
 {"name":"data_statistics","description":"Calculate count, missing values, unique values, min, max, mean, median, and standard deviation for fields.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
 {"name":"sqlite_tables","description":"List tables, columns, indexes, and row counts in a SQLite database.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
 {"name":"sqlite_query","description":"Run one read-only SELECT, WITH, EXPLAIN, or PRAGMA query against a SQLite database.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"query":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":1000}},"required":["path","query"],"additionalProperties":False}},
]
def result(x): return {"content":[{"type":"text","text":str(x)}]}
def path(value, exists=False):
 p=Path(value).expanduser().resolve(); allowed=(Path.home().resolve(),Path('/mnt/shared').resolve())
 if not any(p==root or root in p.parents for root in allowed): raise ValueError("Path must be under home or /mnt/shared")
 if exists and not p.is_file(): raise ValueError(f"File not found: {p}")
 return p
def records(p):
 s=p.suffix.lower()
 if s=='.csv':
  with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
 if s=='.json':
  value=json.loads(p.read_text()); return value if isinstance(value,list) else [value]
 if s in ('.jsonl','.ndjson'):
  return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
 raise ValueError("Supported structured formats: CSV, JSON, JSONL")
def write(rows,p):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists(): raise ValueError(f"Destination already exists: {p}")
 if p.suffix.lower()=='.csv':
  fields=list(dict.fromkeys(k for row in rows for k in row));
  with p.open('w',newline='',encoding='utf-8') as f: w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 elif p.suffix.lower()=='.json': p.write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n')
 elif p.suffix.lower() in ('.jsonl','.ndjson'): p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
 else: raise ValueError("Destination must be .csv, .json, or .jsonl")
def call(name,a):
 p=path(a.get('path') or a.get('source'),True) if name not in ('json_format',) else path(a['source'],True)
 if name=='data_validate': records(p); return result(f"Valid {p.suffix[1:].upper()} · {p}")
 if name=='data_inspect':
  if p.suffix.lower() in ('.db','.sqlite','.sqlite3'): return call('sqlite_tables',{'path':str(p)})
  rows=records(p); fields=list(dict.fromkeys(k for r in rows for k in r)); sample=rows[:5]
  return result(json.dumps({'path':str(p),'records':len(rows),'fields':fields,'sample':sample},indent=2,ensure_ascii=False,default=str))
 if name=='json_format':
  d=path(a['destination']); value=json.loads(p.read_text()); d.parent.mkdir(parents=True,exist_ok=True)
  if d.exists(): raise ValueError(f"Destination already exists: {d}")
  d.write_text(json.dumps(value,indent=2 if a.get('style','pretty')=='pretty' else None,separators=None if a.get('style','pretty')=='pretty' else (',',':'),ensure_ascii=False)+'\n'); return result(f"Wrote {d}")
 if name in ('data_convert','data_filter','data_sort','data_deduplicate'):
  rows=records(p); before=len(rows)
  if name=='data_filter':
   field,op,want=a['field'],a['operator'],a['value']
   def keep(r):
    got=r.get(field); 
    if op=='equals': return str(got)==str(want)
    if op=='contains': return str(want).lower() in str(got).lower()
    try: x,y=float(got),float(want); return {'gt':x>y,'gte':x>=y,'lt':x<y,'lte':x<=y}[op]
    except (TypeError,ValueError): return False
   rows=[r for r in rows if keep(r)]
  elif name=='data_sort': rows=sorted(rows,key=lambda r:(r.get(a['field']) is None,str(r.get(a['field'],'' )).lower()),reverse=bool(a.get('descending')))
  elif name=='data_deduplicate':
   fields=a.get('fields') or list(dict.fromkeys(k for r in rows for k in r)); seen=set(); out=[]
   for r in rows:
    key=tuple(json.dumps(r.get(k),sort_keys=True,default=str) for k in fields)
    if key not in seen: seen.add(key);out.append(r)
   rows=out
  d=path(a['destination']); write(rows,d); return result(f"Wrote {len(rows)} records to {d} (input {before})")
 if name=='data_statistics':
  rows=records(p); fields=list(dict.fromkeys(k for r in rows for k in r)); out={}
  for f in fields:
   vals=[r.get(f) for r in rows]; nums=[]
   for v in vals:
    try: nums.append(float(v))
    except (TypeError,ValueError): pass
   item={'count':len(vals),'missing':sum(v in (None,'') for v in vals),'unique':len({str(v) for v in vals})}
   if nums: item.update(min=min(nums),max=max(nums),mean=statistics.fmean(nums),median=statistics.median(nums),stdev=statistics.stdev(nums) if len(nums)>1 else 0)
   out[f]=item
  return result(json.dumps(out,indent=2,ensure_ascii=False))
 if name=='sqlite_tables':
  con=sqlite3.connect(f'file:{p}?mode=ro',uri=True); names=[r[0] for r in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]; out={}
  for table in names: out[table]={'columns':[{'name':r[1],'type':r[2]} for r in con.execute(f'pragma table_info("{table.replace(chr(34),chr(34)*2)}")')],'rows':con.execute(f'select count(*) from "{table.replace(chr(34),chr(34)*2)}"').fetchone()[0]}
  con.close(); return result(json.dumps(out,indent=2))
 if name=='sqlite_query':
  q=a['query'].strip();
  if not q.lower().startswith(('select','with','explain','pragma')) or ';' in q.rstrip(';'): raise ValueError('Only one read-only query is allowed')
  con=sqlite3.connect(f'file:{p}?mode=ro',uri=True); con.row_factory=sqlite3.Row; rows=[dict(r) for r in con.execute(q).fetchmany(int(a.get('limit',200)))]; con.close(); return result(json.dumps(rows,indent=2,ensure_ascii=False,default=str))
 raise ValueError(f'Unknown data tool: {name}')
for raw in sys.stdin:
 m={}
 try:
  m=json.loads(raw); rid=m.get('id');
  if rid is None: continue
  method=m.get('method'); response={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"AI Dock Data","version":"1.0"}} if method=='initialize' else {"tools":TOOLS} if method=='tools/list' else call(m['params']['name'],m['params'].get('arguments',{})) if method=='tools/call' else (_ for _ in ()).throw(ValueError('Unsupported MCP method'))
  reply={"jsonrpc":"2.0","id":rid,"result":response}
 except Exception as e: reply={"jsonrpc":"2.0","id":m.get('id'),"error":{"code":-32000,"message":str(e)}}
 print(json.dumps(reply,separators=(',',':')),flush=True)
