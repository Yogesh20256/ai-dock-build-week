#!/usr/bin/env python3
"""Private local full-text knowledge index for AI Dock."""
import csv,hashlib,json,re,sqlite3,subprocess,sys,time,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

DATA=Path.home()/".local/share/ai-dock";DB=DATA/"knowledge.sqlite3";DATA.mkdir(parents=True,exist_ok=True)
ALLOWED=(Path.home().resolve(),Path("/mnt/shared").resolve())
TEXT={".txt",".md",".rst",".c",".h",".cc",".cpp",".hpp",".py",".js",".ts",".tsx",".jsx",".java",".go",".rs",".sh",".fish",".html",".css",".json",".jsonl",".csv",".yaml",".yml",".toml",".xml",".sql",".http"}
SKIP={".git",".venv","node_modules","__pycache__","Trash","Cache","Caches","Cookies","Local Storage","Session Storage"}
TOOLS=[
 {"name":"knowledge_index_path","description":"Index readable documents, code, PDFs and DOCX files under home or /mnt/shared into the private local full-text knowledge base. Incremental and provenance-preserving. cloud_context defaults false.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"recursive":{"type":"boolean"},"max_files":{"type":"integer","minimum":1,"maximum":10000},"cloud_context":{"type":"boolean"}},"required":["path"],"additionalProperties":False}},
 {"name":"knowledge_search","description":"Search the private local knowledge index with FTS5/BM25 and return matching source paths, titles, excerpts, hashes and modification times.","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":50},"path_prefix":{"type":"string"}},"required":["query"],"additionalProperties":False}},
 {"name":"knowledge_context","description":"Build a compact evidence packet from locally indexed files. Can include private entries for local display; cloud planners receive only entries explicitly indexed with cloud_context true.","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"max_chars":{"type":"integer","minimum":1000,"maximum":50000},"cloud_only":{"type":"boolean"}},"required":["query"],"additionalProperties":False}},
 {"name":"knowledge_status","description":"Show local knowledge database size, sources, chunks, cloud-shareable chunks, formats and last indexed files.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
 {"name":"knowledge_sources","description":"List indexed source roots and their privacy/cloud-context status, file counts and newest modification time.","inputSchema":{"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":200}},"additionalProperties":False}},
 {"name":"knowledge_remove_source","description":"Remove one source path or path prefix from the knowledge index only; never deletes original files. Requires confirm exactly REMOVE INDEX.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"confirm":{"type":"string"}},"required":["path","confirm"],"additionalProperties":False}},
 {"name":"knowledge_reindex_changed","description":"Refresh changed/missing files for all previously indexed roots while preserving each root's cloud-context privacy setting.","inputSchema":{"type":"object","properties":{"max_files":{"type":"integer","minimum":1,"maximum":20000}},"additionalProperties":False}},
]
def db():
 c=sqlite3.connect(DB);c.execute("PRAGMA journal_mode=WAL");c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(path UNINDEXED,title,content,mtime UNINDEXED,sha256 UNINDEXED,cloud UNINDEXED,root UNINDEXED)");c.execute("CREATE TABLE IF NOT EXISTS roots(path TEXT PRIMARY KEY,recursive INTEGER,cloud INTEGER,indexed_at REAL,file_count INTEGER)");return c
def allowed(value):
 p=Path(value).expanduser().resolve()
 if not any(p==root or root in p.parents for root in ALLOWED):raise ValueError("Path must be under home or /mnt/shared")
 if any(part.startswith(".") or part in SKIP for part in p.parts[len(Path.home().parts):]):raise ValueError("Hidden, cache and credential-bearing paths are not indexable")
 return p
def read(path):
 if path.stat().st_size>5_000_000:raise ValueError("file exceeds 5 MB indexing limit")
 suffix=path.suffix.lower()
 if suffix in TEXT:return path.read_text(errors="replace")
 if suffix==".pdf":
  result=subprocess.run(["pdftotext",str(path),"-"],capture_output=True,text=True,timeout=30);return result.stdout if result.returncode==0 else ""
 if suffix==".docx":
  with zipfile.ZipFile(path) as z:root=ET.fromstring(z.read("word/document.xml"));return " ".join(x.text or "" for x in root.iter() if x.tag.endswith("}t"))
 return ""
def chunks(text,size=3600,overlap=300):
 text=re.sub(r"\x00","",text);return [text[i:i+size] for i in range(0,len(text),size-overlap) if text[i:i+size].strip()]
def files(root,recursive,max_files):
 source=[root] if root.is_file() else (root.rglob("*") if recursive else root.glob("*"));out=[]
 for p in source:
  if len(out)>=max_files:break
  try:
   relative=p.relative_to(root) if p!=root else Path(p.name)
   if p.is_file() and not any(part.startswith(".") or part in SKIP for part in relative.parts) and p.suffix.lower() in TEXT|{".pdf",".docx"}:out.append(p)
  except OSError:pass
 return out
def index(a):
 root=allowed(a["path"]);recursive=bool(a.get("recursive",True));maximum=min(int(a.get("max_files",3000)),10000);cloud=1 if a.get("cloud_context",False) else 0;paths=files(root,recursive,maximum);c=db();done=skipped=0
 for path in paths:
  try:
   stat=path.stat();raw=path.read_bytes() if path.stat().st_size<=5_000_000 else b"";sha=hashlib.sha256(raw).hexdigest();existing=c.execute("SELECT sha256 FROM chunks WHERE path=? LIMIT 1",(str(path),)).fetchone()
   if existing and existing[0]==sha:
    c.execute("UPDATE chunks SET cloud=?,root=? WHERE path=?",(cloud,str(root),str(path)));skipped+=1;continue
   text=read(path);c.execute("DELETE FROM chunks WHERE path=?",(str(path),))
   for part in chunks(text):c.execute("INSERT INTO chunks(path,title,content,mtime,sha256,cloud,root) VALUES(?,?,?,?,?,?,?)",(str(path),path.name,part,str(stat.st_mtime),sha,str(cloud),str(root)))
   done+=1
  except Exception:skipped+=1
 c.execute("INSERT OR REPLACE INTO roots VALUES(?,?,?,?,?)",(str(root),int(recursive),cloud,time.time(),len(paths)));c.commit();count=c.execute("SELECT count(*) FROM chunks WHERE root=?",(str(root),)).fetchone()[0];c.close();return {"root":str(root),"files_seen":len(paths),"files_updated":done,"files_unchanged_or_skipped":skipped,"chunks":count,"cloud_context":bool(cloud),"database":str(DB)}
def terms(query):return " OR ".join('"'+x.replace('"','')+'"' for x in re.findall(r"[a-zA-Z0-9_]{2,}",query)[:20])
def search(a,cloud_only=False):
 q=terms(str(a["query"]));limit=min(int(a.get("limit",12)),50);prefix=str(a.get("path_prefix","")).strip();c=db()
 if not q:return []
 sql="SELECT path,title,snippet(chunks,2,'[[',']]', ' … ',35),mtime,sha256,cloud,bm25(chunks) FROM chunks WHERE chunks MATCH ?";args=[q]
 if cloud_only:sql+=" AND cloud='1'"
 if prefix:sql+=" AND path LIKE ?";args.append(str(allowed(prefix))+"%")
 sql+=" ORDER BY bm25(chunks) LIMIT ?";args.append(limit);rows=c.execute(sql,args).fetchall();c.close();return [{"path":x[0],"title":x[1],"excerpt":x[2],"modified":float(x[3]),"sha256":x[4],"cloud_context":x[5]=="1","score":x[6]} for x in rows]
def context(a):
 items=search({"query":a["query"],"limit":30},bool(a.get("cloud_only",False)));limit=min(int(a.get("max_chars",12000)),50000);parts=[]
 for item in items:
  block=f"SOURCE: {item['path']}\nHASH: {item['sha256']}\nEXCERPT: {item['excerpt']}"
  if sum(map(len,parts))+len(block)>limit:break
  parts.append(block)
 return {"query":a["query"],"cloud_only":bool(a.get("cloud_only",False)),"sources":len(parts),"context":"\n\n".join(parts)}
def status():
 c=db();chunks_n=c.execute("SELECT count(*) FROM chunks").fetchone()[0];sources=c.execute("SELECT count(DISTINCT path) FROM chunks").fetchone()[0];shared=c.execute("SELECT count(*) FROM chunks WHERE cloud='1'").fetchone()[0];roots=c.execute("SELECT count(*) FROM roots").fetchone()[0];recent=c.execute("SELECT DISTINCT path FROM chunks ORDER BY CAST(mtime AS REAL) DESC LIMIT 10").fetchall();c.close();return {"database":str(DB),"bytes":DB.stat().st_size if DB.exists() else 0,"roots":roots,"source_files":sources,"chunks":chunks_n,"cloud_shareable_chunks":shared,"recent_sources":[x[0] for x in recent]}
def call(name,a):
 if name=="knowledge_index_path":return index(a)
 if name=="knowledge_search":return search(a)
 if name=="knowledge_context":return context(a)
 if name=="knowledge_status":return status()
 if name=="knowledge_sources":
  c=db();rows=c.execute("SELECT path,recursive,cloud,indexed_at,file_count FROM roots ORDER BY indexed_at DESC LIMIT ?",(min(int(a.get("limit",50)),200),)).fetchall();c.close();return [{"path":x[0],"recursive":bool(x[1]),"cloud_context":bool(x[2]),"indexed_at":x[3],"file_count":x[4]} for x in rows]
 if name=="knowledge_remove_source":
  if a.get("confirm")!="REMOVE INDEX":raise ValueError("confirm must be exactly REMOVE INDEX")
  path=str(allowed(a["path"]));c=db();before=c.execute("SELECT count(*) FROM chunks WHERE path=? OR path LIKE ?",(path,path+"/%")).fetchone()[0];c.execute("DELETE FROM chunks WHERE path=? OR path LIKE ?",(path,path+"/%"));c.execute("DELETE FROM roots WHERE path=? OR path LIKE ?",(path,path+"/%"));c.commit();c.close();return {"removed_chunks":before,"original_files_deleted":False}
 if name=="knowledge_reindex_changed":
  c=db();roots=c.execute("SELECT path,recursive,cloud FROM roots ORDER BY indexed_at").fetchall();c.close();return [index({"path":p,"recursive":bool(r),"cloud_context":bool(cloud),"max_files":a.get("max_files",5000)}) for p,r,cloud in roots]
 raise ValueError(name)
for line in sys.stdin:
 try:
  m=json.loads(line);rid=m.get("id")
  if rid is None:continue
  method=m.get("method");out={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"AI Dock Local Knowledge","version":"1.0"}} if method=="initialize" else {"tools":TOOLS} if method=="tools/list" else {"content":[{"type":"text","text":json.dumps(call(m["params"]["name"],m["params"].get("arguments",{})),indent=2,ensure_ascii=False)}]} if method=="tools/call" else (_ for _ in ()).throw(ValueError("Unsupported method"));reply={"jsonrpc":"2.0","id":rid,"result":out}
 except Exception as error:reply={"jsonrpc":"2.0","id":m.get("id") if "m" in locals() else None,"error":{"code":-32000,"message":str(error)}}
 print(json.dumps(reply,separators=(",",":")),flush=True)
