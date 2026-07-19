#!/usr/bin/env python3
"""Source-backed internet research tools for AI Dock."""
import hashlib,json,re,socket,sys,time,urllib.parse,urllib.request
from datetime import datetime,timezone
from html.parser import HTMLParser
from ipaddress import ip_address
from pathlib import Path

ROOT=Path.home()/"Documents"/"AI Research";ROOT.mkdir(parents=True,exist_ok=True)
BRAIN=Path.home()/"Documents"/"Connected Brain"
UA="AI-Dock-Research/1.0 (+local source-backed research)"
TOOLS=[
 {"name":"web_search","description":"Search the public web and return titles, URLs and snippets from multiple no-key search endpoints.","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":20}},"required":["query"],"additionalProperties":False}},
 {"name":"webpage_extract","description":"Fetch an HTTP/HTTPS webpage safely and extract title, description, canonical URL, readable text, links, response metadata and content hash.","inputSchema":{"type":"object","properties":{"url":{"type":"string"},"max_chars":{"type":"integer","minimum":1000,"maximum":100000}},"required":["url"],"additionalProperties":False}},
 {"name":"research_bundle","description":"Research a question across multiple independent webpages, save raw evidence and a Markdown source ledger, and return excerpts with URLs for cloud synthesis.","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"urls":{"type":"array","items":{"type":"string"},"maxItems":12},"max_sources":{"type":"integer","minimum":2,"maximum":10}},"required":["query"],"additionalProperties":False}},
 {"name":"knowledge_lookup","description":"Look up a topic using Wikipedia's official API and return a summary, canonical page, modification timestamp and related pages.","inputSchema":{"type":"object","properties":{"topic":{"type":"string"},"language":{"type":"string"}},"required":["topic"],"additionalProperties":False}},
 {"name":"scholarly_search","description":"Search scholarly works through the public Crossref API with DOI, authors, venue, date, citation count and URL.","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":20}},"required":["query"],"additionalProperties":False}},
 {"name":"github_repository_search","description":"Search public GitHub repositories through the official API and return repository, description, language, stars, update time and URL.","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":20}},"required":["query"],"additionalProperties":False}},
 {"name":"rss_read","description":"Read a public RSS or Atom feed and return recent entry titles, links, dates and summaries.","inputSchema":{"type":"object","properties":{"url":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":50}},"required":["url"],"additionalProperties":False}},
 {"name":"json_api_get","description":"GET a public JSON API endpoint safely and return status, headers and bounded parsed JSON. Private/local network targets are blocked.","inputSchema":{"type":"object","properties":{"url":{"type":"string"},"max_chars":{"type":"integer","minimum":1000,"maximum":200000}},"required":["url"],"additionalProperties":False}},
 {"name":"source_freshness","description":"Inspect a public URL's status, final URL, content type, Last-Modified, ETag, retrieval time and hash without trusting stale memory.","inputSchema":{"type":"object","properties":{"url":{"type":"string"}},"required":["url"],"additionalProperties":False}},
 {"name":"download_verified","description":"Download a public file to Documents/AI Research or an explicit path under home, enforce a size limit, and save SHA-256 plus URL provenance. Refuses overwrite.","inputSchema":{"type":"object","properties":{"url":{"type":"string"},"destination":{"type":"string"},"max_megabytes":{"type":"integer","minimum":1,"maximum":200}},"required":["url","destination"],"additionalProperties":False}},
 {"name":"site_crawl","description":"Crawl a bounded number of same-domain pages from a public website, extracting titles, text, links, status and hashes into a local site map artifact.","inputSchema":{"type":"object","properties":{"url":{"type":"string"},"max_pages":{"type":"integer","minimum":1,"maximum":30}},"required":["url"],"additionalProperties":False}},
 {"name":"compare_webpages","description":"Fetch 2-8 supplied webpages and return aligned source metadata and readable excerpts for evidence-based comparison.","inputSchema":{"type":"object","properties":{"urls":{"type":"array","items":{"type":"string"},"minItems":2,"maxItems":8},"max_chars_each":{"type":"integer","minimum":1000,"maximum":30000}},"required":["urls"],"additionalProperties":False}},
 {"name":"wayback_history","description":"Query the Internet Archive CDX API for historical snapshots of a public URL with timestamps, status, MIME type, digest and archived URL.","inputSchema":{"type":"object","properties":{"url":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":50}},"required":["url"],"additionalProperties":False}},
]

class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.title=[];self.links=[];self.skip=0;self.meta={}
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag in ("script","style","noscript","svg"):self.skip+=1
  if tag=="title":self.meta["in_title"]=True
  if tag=="a" and a.get("href"):self.links.append(a["href"])
  if tag=="meta" and a.get("content") and (a.get("name") or a.get("property")) in ("description","og:description"):self.meta["description"]=a["content"]
  if tag=="link" and a.get("rel")=="canonical":self.meta["canonical"]=a.get("href")
 def handle_endtag(self,tag):
  if tag in ("script","style","noscript","svg") and self.skip:self.skip-=1
  if tag=="title":self.meta["in_title"]=False
 def handle_data(self,data):
  if self.skip:return
  clean=" ".join(data.split())
  if clean:self.parts.append(clean)
  if clean and self.meta.get("in_title"):self.title.append(clean)

def safe(url):
 p=urllib.parse.urlparse(str(url).strip())
 if p.scheme not in ("http","https") or not p.hostname:raise ValueError("Only public HTTP/HTTPS URLs are allowed")
 if p.username or p.password:raise ValueError("Credentials in URLs are not allowed")
 for info in socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=="https" else 80),type=socket.SOCK_STREAM):
  ip=ip_address(info[4][0])
  if not ip.is_global:raise ValueError("Private, loopback and link-local network targets are blocked")
 return p.geturl()
def request(url,limit=5_000_000,accept="*/*"):
 url=safe(url);req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":accept})
 with urllib.request.urlopen(req,timeout=25) as r:
  data=r.read(limit+1)
  if len(data)>limit:raise ValueError(f"Response exceeds {limit} bytes")
  return data,dict(r.headers),r.status,r.url
def hget(headers,name):return next((value for key,value in headers.items() if key.lower()==name.lower()),None)
def clean_html(value):return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",str(value))).strip()
def extract(url,max_chars=30000):
 data,headers,status,final=request(url);ctype=hget(headers,"Content-Type") or ""
 if "html" not in ctype.lower():raise ValueError(f"Expected HTML but received {ctype}")
 encoding=re.search(r"charset=([^; ]+)",ctype,re.I);html=data.decode(encoding.group(1) if encoding else "utf-8",errors="replace")
 parser=Text();parser.feed(html);text="\n".join(parser.parts);links=[]
 for href in parser.links[:300]:
  absolute=urllib.parse.urljoin(final,href)
  if urllib.parse.urlparse(absolute).scheme in ("http","https") and absolute not in links:links.append(absolute)
 return {"url":url,"final_url":final,"status":status,"retrieved_at":datetime.now(timezone.utc).isoformat(),"content_type":ctype,"title":" ".join(parser.title)[:500],"description":parser.meta.get("description",""),"canonical":urllib.parse.urljoin(final,parser.meta.get("canonical","")) if parser.meta.get("canonical") else final,"text":text[:max_chars],"links":links[:100],"sha256":hashlib.sha256(data).hexdigest(),"headers":{k:v for k,v in headers.items() if k.lower() in ("date","last-modified","etag","content-type","content-length")}}
def search(query,limit=10):
 results=[];seen=set();q=urllib.parse.quote_plus(query)
 for endpoint,kind in ((f"https://html.duckduckgo.com/html/?q={q}","ddg"),(f"https://www.bing.com/search?format=rss&q={q}","bing-rss")):
  try:
   raw,_,_,_=request(endpoint,2_000_000);body=raw.decode(errors="replace")
   if kind=="ddg":matches=re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</',body,re.S)
   else:matches=re.findall(r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<description>(.*?)</description>.*?</item>",body,re.S);matches=[(u,t,s) for t,u,s in matches]
   for url,title,snippet in matches:
    url=urllib.parse.unquote(re.search(r"uddg=([^&]+)",url).group(1)) if "uddg=" in url else clean_html(url)
    if url.startswith("http") and url not in seen:seen.add(url);results.append({"title":clean_html(title),"url":url,"snippet":clean_html(snippet),"engine":kind})
  except Exception:pass
 return results[:limit]
def bundle(a):
 query=str(a["query"]);maximum=max(2,min(int(a.get("max_sources",5)),10));urls=list(a.get("urls") or [])
 if not urls:urls=[x["url"] for x in search(query,min(maximum*3,20))]
 evidence=[];failures=[]
 for url in urls:
  if len(evidence)>=maximum:break
  try:evidence.append(extract(url,18000))
  except Exception as error:failures.append({"url":url,"error":str(error)})
 stamp=datetime.now().strftime("%Y%m%d-%H%M%S");folder=ROOT/f"{stamp}-{re.sub(r'[^a-z0-9]+','-',query.lower()).strip('-')[:50]}";folder.mkdir()
 (folder/"evidence.json").write_text(json.dumps({"query":query,"evidence":evidence,"failed_sources":failures},indent=2,ensure_ascii=False)+"\n")
 lines=[f"# Research evidence: {query}","",f"Retrieved: {datetime.now(timezone.utc).isoformat()}",""]
 for i,item in enumerate(evidence,1):lines += [f"## {i}. {item.get('title') or item.get('url')}","",f"Source: {item.get('final_url') or item.get('url')}","",item.get("text",item.get("error",""))[:3500],""]
 (folder/"sources.md").write_text("\n".join(lines))
 if BRAIN.is_dir():
  research=BRAIN/"Research";research.mkdir(parents=True,exist_ok=True);note=research/(folder.name+".md")
  brain_lines=[f"# Research: {query}","","Connected to [[Home]] · [[Research/Index|Research Index]]","",f"Evidence folder: `{folder}`","",*lines[3:]]
  note.write_text("\n".join(brain_lines));index=research/"Index.md"
  existing=index.read_text(errors="replace") if index.exists() else "# Research Index\n\nConnected to [[Home]] · [[Brain Map]]\n\n"
  link=f"- [[Research/{note.stem}|{query}]]"
  if link not in existing:index.write_text(existing+link+"\n")
 return {"query":query,"artifact_folder":str(folder),"successful_sources":len(evidence),"sources":evidence,"failed_sources":failures}
def crawl(a):
 start=safe(a["url"]);maximum=min(int(a.get("max_pages",10)),30);host=urllib.parse.urlparse(start).hostname;queue=[start];seen=set();pages=[];failures=[]
 while queue and len(pages)<maximum:
  url=queue.pop(0)
  if url in seen:continue
  seen.add(url)
  try:
   page=extract(url,8000);pages.append({k:page[k] for k in ("url","final_url","status","title","description","text","sha256","retrieved_at")})
   for link in page["links"]:
    parsed=urllib.parse.urlparse(link);clean=parsed._replace(fragment="").geturl()
    if parsed.hostname==host and clean not in seen and clean not in queue:queue.append(clean)
  except Exception as error:failures.append({"url":url,"error":str(error)})
 stamp=datetime.now().strftime("%Y%m%d-%H%M%S");folder=ROOT/f"{stamp}-site-crawl-{re.sub(r'[^a-z0-9]+','-',host or 'site')}";folder.mkdir();payload={"start_url":start,"pages":pages,"failures":failures};(folder/"site-map.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n")
 (folder/"site-map.md").write_text("# Site crawl: "+start+"\n\n"+"\n\n".join(f"## [{p['title'] or p['final_url']}]({p['final_url']})\n\n{p['text'][:1800]}" for p in pages))
 return {"artifact_folder":str(folder),"pages_crawled":len(pages),"failures":failures,"pages":pages}
def wayback(a):
 original=safe(a["url"]);limit=min(int(a.get("limit",20)),50);endpoint="https://web.archive.org/cdx/search/cdx?"+urllib.parse.urlencode({"url":original,"output":"json","filter":"statuscode:200","fl":"timestamp,original,statuscode,mimetype,digest","collapse":"digest","limit":limit,"from":"1996"});raw,_,_,_=request(endpoint,5_000_000,"application/json");rows=json.loads(raw);header=rows[0] if rows else []
 return [{**dict(zip(header,row)),"archive_url":f"https://web.archive.org/web/{row[0]}/{row[1]}"} for row in rows[1:]]
def knowledge(a):
 lang=re.sub(r"[^a-z]","",str(a.get("language","en")).lower()) or "en";topic=urllib.parse.quote(str(a["topic"]));base=f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{topic}"
 raw,_,_,_=request(base,2_000_000,"application/json");d=json.loads(raw);return {"title":d.get("title"),"description":d.get("description"),"summary":d.get("extract"),"url":d.get("content_urls",{}).get("desktop",{}).get("page"),"modified":d.get("timestamp"),"source":"Wikipedia"}
def scholarly(a):
 url="https://api.crossref.org/works?"+urllib.parse.urlencode({"query":a["query"],"rows":min(int(a.get("limit",10)),20),"select":"DOI,title,author,published,container-title,is-referenced-by-count,URL"});raw,_,_,_=request(url,5_000_000,"application/json");items=json.loads(raw)["message"]["items"]
 return [{"title":"; ".join(x.get("title",[])),"doi":x.get("DOI"),"authors":[" ".join(filter(None,(y.get("given"),y.get("family")))) for y in x.get("author",[])[:8]],"venue":"; ".join(x.get("container-title",[])),"published":x.get("published",{}).get("date-parts",[[None]])[0],"citations":x.get("is-referenced-by-count"),"url":x.get("URL")} for x in items]
def github(a):
 url="https://api.github.com/search/repositories?"+urllib.parse.urlencode({"q":a["query"],"per_page":min(int(a.get("limit",10)),20)});raw,_,_,_=request(url,5_000_000,"application/vnd.github+json");return [{"name":x["full_name"],"description":x.get("description"),"language":x.get("language"),"stars":x.get("stargazers_count"),"updated":x.get("updated_at"),"url":x.get("html_url")} for x in json.loads(raw).get("items",[])]
def rss(a):
 import xml.etree.ElementTree as ET
 raw,_,_,_=request(a["url"],5_000_000,"application/rss+xml, application/atom+xml, application/xml");root=ET.fromstring(raw);items=[]
 for node in list(root.findall(".//item"))+list(root.findall(".//{*}entry")):
  def val(name):
   child=node.find(name) or node.find("{*}"+name);return clean_html(child.text or "") if child is not None else ""
  link=val("link");linknode=node.find("{*}link");link=link or (linknode.get("href","") if linknode is not None else "")
  items.append({"title":val("title"),"link":link,"date":val("pubDate") or val("updated") or val("published"),"summary":val("description") or val("summary")})
 return items[:min(int(a.get("limit",15)),50)]
def call(name,a):
 if name=="web_search":return search(str(a["query"]),min(int(a.get("limit",10)),20))
 if name=="webpage_extract":return extract(a["url"],int(a.get("max_chars",30000)))
 if name=="research_bundle":return bundle(a)
 if name=="knowledge_lookup":return knowledge(a)
 if name=="scholarly_search":return scholarly(a)
 if name=="github_repository_search":return github(a)
 if name=="rss_read":return rss(a)
 if name=="json_api_get":
  raw,h,s,u=request(a["url"],int(a.get("max_chars",100000)),"application/json");return {"status":s,"url":u,"headers":h,"data":json.loads(raw)}
 if name=="source_freshness":
  raw,h,s,u=request(a["url"],2_000_000);return {"status":s,"url":u,"retrieved_at":datetime.now(timezone.utc).isoformat(),"last_modified":hget(h,"Last-Modified"),"etag":hget(h,"ETag"),"content_type":hget(h,"Content-Type"),"sha256":hashlib.sha256(raw).hexdigest()}
 if name=="download_verified":
  url=a["url"];dest=Path(a["destination"]).expanduser();dest=(ROOT/dest if not dest.is_absolute() else dest).resolve();home=Path.home().resolve()
  if dest!=home and home not in dest.parents:raise ValueError("Destination must be under your home folder")
  if dest.exists():raise FileExistsError(f"Refusing to overwrite {dest}")
  raw,h,s,u=request(url,min(int(a.get("max_megabytes",50)),200)*1024*1024);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();prov=dest.with_suffix(dest.suffix+".provenance.json");prov.write_text(json.dumps({"source":u,"retrieved_at":datetime.now(timezone.utc).isoformat(),"status":s,"content_type":hget(h,"Content-Type"),"bytes":len(raw),"sha256":sha},indent=2)+"\n");return {"file":str(dest),"provenance":str(prov),"sha256":sha,"bytes":len(raw)}
 if name=="site_crawl":return crawl(a)
 if name=="compare_webpages":
  successes=[];failures=[]
  for url in a["urls"]:
   try:successes.append(extract(url,int(a.get("max_chars_each",12000))))
   except Exception as error:failures.append({"url":url,"error":str(error)})
  return {"successful_sources":len(successes),"sources":successes,"failures":failures}
 if name=="wayback_history":return wayback(a)
 raise ValueError(f"Unknown tool {name}")
for line in sys.stdin:
 try:
  m=json.loads(line);rid=m.get("id")
  if rid is None:continue
  method=m.get("method");out={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"AI Dock Internet Research","version":"1.0"}} if method=="initialize" else {"tools":TOOLS} if method=="tools/list" else {"content":[{"type":"text","text":json.dumps(call(m["params"]["name"],m["params"].get("arguments",{})),indent=2,ensure_ascii=False)}]} if method=="tools/call" else (_ for _ in ()).throw(ValueError("Unsupported method"));reply={"jsonrpc":"2.0","id":rid,"result":out}
 except Exception as error:reply={"jsonrpc":"2.0","id":m.get("id") if "m" in locals() else None,"error":{"code":-32000,"message":str(error)}}
 print(json.dumps(reply,separators=(",",":")),flush=True)
