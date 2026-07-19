#!/usr/bin/env python3
"""Repeatable, non-destructive regression suite for AI Dock's power layer."""
import json
import py_compile
import sys
import tempfile
from unittest.mock import patch
from collections import Counter
from pathlib import Path

from mcp_client import McpConnections
from ai_dock import McpPanel, FlowPanel, first_json_object
from agent_runtime import CapabilityIndex, TaskJournal, completion_report, validate_plan, semantic_similarity

ROOT=Path(__file__).resolve().parent
CONFIG=Path.home()/".config/ai-dock/mcp_servers.json"
MODULES=("ai_dock.py","agent_runtime.py","feature_center.py","mcp_client.py","automation_mcp_server.py","brain_mcp_server.py","developer_mcp_server.py","workspace_mcp_server.py","media_mcp_server.py","data_mcp_server.py","operations_mcp_server.py","monitor_mcp_server.py","desktop_mcp_server.py","system_mcp_server.py","browser_mcp_server.py","document_mcp_server.py","package_mcp_server.py","mission_mcp_server.py","research_mcp_server.py","knowledge_mcp_server.py")

def main():
 checks=[]
 def check(name,function):
  try:
   detail=function(); checks.append({"name":name,"passed":True,"detail":str(detail)[:1200]})
  except Exception as error: checks.append({"name":name,"passed":False,"detail":f"{type(error).__name__}: {error}"})
 check("Python syntax",lambda:[py_compile.compile(str(ROOT/name),doraise=True) for name in MODULES] and f"{len(MODULES)} modules")
 check("MCP JSON",lambda:len(json.loads(CONFIG.read_text()).get("servers",{})))
 def flexible_routes():
  panel=McpPanel.__new__(McpPanel);panel.memory=[]
  expected={
   "tell me the version of my vs code":("packages__package_version",{"package":"vs code"}),
   "what is my vs code version":("packages__package_version",{"package":"vs code"}),
   "bro could ya please check whether vscode is up to date for me":("packages__package_version",{"package":"vscode"}),
   "version of antigravity ide":("packages__package_version",{"package":"antigravity ide"}),
  }
  for prompt,want in expected.items():
   got=panel.trusted_fast_action(prompt)
   if got!=want:raise AssertionError(f"{prompt!r}: {got!r} != {want!r}")
  cleaned,planner=panel.parse_planner_directive("use chat gpt to and tell me the version of my vs code")
  if (cleaned,planner)!=("tell me the version of my vs code","chatgpt"):raise AssertionError((cleaned,planner))
  simple=("open w2","open youtube","install vlc","show system resources")
  if any(panel.trusted_fast_action(prompt) is None for prompt in simple):raise AssertionError("A safe deterministic route was lost")
  compound="close all windows in w3 and open gmail.google.com or directly gmail in it"
  compound_want=("desktop__prepare_workspace_and_open_url",{"workspace":"3","url":"https://mail.google.com"})
  if panel.trusted_fast_action(compound)!=compound_want:raise AssertionError((compound,panel.trusted_fast_action(compound)))
  if panel.choose_planner("build an application and publish it")!="council":raise AssertionError("complex mission did not select AI Council")
  council_samples=("open the website, inspect it and then save a report", "figure this out and handle it", "close all windows and then open gmail in w3")
  if any(panel.choose_planner(prompt)!="council" for prompt in council_samples):raise AssertionError("ambiguous or compound work did not escalate to council")
  cloud_samples=("could you sort out that browser thing for me","please figure out what I meant and handle it","debug this code","make a weather table")
  if any(panel.choose_planner(prompt)=="local" for prompt in cloud_samples):raise AssertionError("Auto planner delegated interpretation to local Qwen")
  if any(key=="local" for key,_label in panel.PLANNERS):raise AssertionError("Local Qwen is still selectable as an MCP planner")
  semantic=("open instagram in w3 and then search for tiger","move it to w2","close that thing","install something","open youtube but use the same previous tab")
  bad={prompt:panel.trusted_fast_action(prompt) for prompt in semantic if panel.trusted_fast_action(prompt) is not None}
  if bad:raise AssertionError(f"Complex/ambiguous requests bypassed semantics: {bad}")
  panel.conversation_state={"version":1,"slots":{"last_opened":{"type":"application","value":"dolphin"}},"events":[]}
  if '"dolphin"' not in panel.state_packet():raise AssertionError("Persistent action entity missing from context packet")
  followups={"close that thing":("desktop__close_application",{"application":"dolphin"}),"move it to w4":("desktop__move_windows",{"application":"dolphin","destination":"4"})}
  for prompt,want in followups.items():
   got=panel.state_followup_action(prompt)
   if got!=want:raise AssertionError(f"Follow-up {prompt!r}: {got!r} != {want!r}")
  return f"{len(expected)} tone variants + {len(simple)} deterministic domains + {len(semantic)} semantic fallbacks + {len(council_samples)} consensus escalations + cloud-only interpretation"
 check("Flexible natural-language routes",flexible_routes)
 def adaptive_provider_routing():
  panel=McpPanel.__new__(McpPanel)
  panel.provider_stats={
   "gemini":{"success":0,"failure":8,"bridge_failure":4,"invalid":2,"streak":-3,"domains":{"general":{"success":0,"failure":8}},"latency_total":180,"latency_samples":4},
   "chatgpt":{"success":18,"failure":1,"bridge_failure":0,"invalid":0,"streak":3,"domains":{"general":{"success":12,"failure":0}},"latency_total":80,"latency_samples":10},
  }
  if panel.choose_planner("explain the meaning of this request")!="chatgpt":raise AssertionError("real provider reliability did not influence Auto routing")
  if panel.task_domain("audit this project for vulnerabilities")!="security":raise AssertionError("security specialty classification failed")
  if panel.task_domain("update this system package")!="system":raise AssertionError("system specialty classification failed")
  panel.provider_stats["chatgpt"]["cooldown_until"]=__import__("time").time()+300
  if not panel.provider_in_cooldown("chatgpt") or panel.provider_adaptive_score("chatgpt","explain this")>-50:raise AssertionError("failed bridge circuit breaker did not suppress provider")
  ranked=panel.ranked_cloud_providers("explain this")
  if "chatgpt" in ranked or not ranked:raise AssertionError("cooling provider remained in learned candidate ranking")
  return "Bayesian reliability, task specialty, latency and recent streak alter future Auto routing"
 check("Adaptive provider intelligence",adaptive_provider_routing)
 def deterministic_world_model():
  panel=McpPanel.__new__(McpPanel)
  before={"desktop":{"active_workspace":"1","windows":[{"workspace":"1","application":"kitty","title":"Terminal"}]},"paths":{"/tmp/report.txt":{"exists":False}}}
  moved={"desktop":{"active_workspace":"3","windows":[{"workspace":"3","application":"kitty","title":"Terminal"}]},"paths":{"/tmp/report.txt":{"exists":True,"directory":False,"size":12}}}
  cases=[
   ("desktop__open_workspace",{"workspace":"3"},True),
   ("desktop__move_windows",{"application":"kitty","destination":"3"},True),
   ("desktop__close_application",{"application":"kitty","workspace":"1"},True),
   ("system__file_create",{"path":"/tmp/report.txt"},True),
   ("system__file_trash",{"path":"/tmp/report.txt"},False),
   ("desktop__launch_application",{"application":"terminal","workspace":"3"},True),
  ]
  for tool,args,want in cases:
   got,_=panel.verify_observed_effect(tool,args,before,moved)
   if got is not want:raise AssertionError((tool,got,want))
  unknown,_=panel.verify_observed_effect("research__web_search",{"query":"test"},before,moved)
  if unknown is not None:raise AssertionError("ambiguous web effect was falsely enforced")
  return "workspace activation, moves, closure and files are locally asserted; ambiguous effects remain non-failing"
 check("Deterministic world-state verification",deterministic_world_model)
 def recovery_idempotency():
  first={"tool":"system__file_create","arguments":{"path":"/tmp/a.txt","content":"x"}}
  reordered={"arguments":{"content":"x","path":"/tmp/a.txt"},"tool":"system__file_create"}
  different={"tool":"system__file_create","arguments":{"path":"/tmp/b.txt","content":"x"}}
  if McpPanel.action_fingerprint(first)!=McpPanel.action_fingerprint(reordered):raise AssertionError("argument order changed action identity")
  if McpPanel.action_fingerprint(first)==McpPanel.action_fingerprint(different):raise AssertionError("different mutation collided")
  return "canonical fingerprints prevent recovery from repeating an already-completed mutation"
 check("Recovery idempotency guard",recovery_idempotency)
 def intent_contracts():
  panel=McpPanel.__new__(McpPanel);obligations=panel.request_obligations("close all windows in w3 and open gmail there and then search for invoices")
  if len(obligations)!=3:raise AssertionError(obligations)
  complete={"actions":[{"tool":"desktop__close_workspace_windows","arguments":{"workspace":"3"},"covers":["intent_1"]},{"tool":"desktop__open_url","arguments":{"url":"https://mail.google.com","workspace":"3"},"covers":["intent_2","intent_3"]}],"answered_intents":[]}
  panel.validate_intent_coverage(obligations,complete)
  incomplete={"actions":complete["actions"][:1],"answered_intents":[]}
  try:panel.validate_intent_coverage(obligations,incomplete)
  except ValueError:pass
  else:raise AssertionError("plan silently dropped explicit clauses")
  return "three explicit clauses become mandatory intent IDs; incomplete plans are rejected before execution"
 check("Multi-clause intent contract",intent_contracts)
 def contaminated_planner_json():
  payload='preface {"actions":[{"tool":"desktop__open_workspace","arguments":{"workspace":"2"}}],"answered_intents":[]} verify-human-overlay garbage'
  parsed=first_json_object(payload)
  if parsed["actions"][0]["arguments"]["workspace"]!="2":raise AssertionError(parsed)
  return "the first complete JSON object survives website text appended by a cloud bridge"
 check("Contaminated planner JSON recovery",contaminated_planner_json)
 def twisted_obligation_contract():
  command="Inside Documents make a folder called Twisted Test Lab and put a note named proof.txt in it saying the maze worked, meanwhile merge both Brave windows from w8 into w9, finally go back to w2"
  got=[item["request"] for item in McpPanel.request_obligations(command)]
  want=["Inside Documents make a folder called Twisted Test Lab","put a note named proof.txt in it saying the maze worked","merge both Brave windows from w8 into w9","go back to w2"]
  if got!=want:raise AssertionError(got)
  if any(item.endswith(" and") for item in got):raise AssertionError(got)
  return "twisted folder, file, merge and workspace clauses remain four clean mandatory intents"
 check("Twisted multi-command splitting",twisted_obligation_contract)
 def flexible_merge_routes():
  panel=McpPanel.__new__(McpPanel);panel.memory=[]
  cases={
   "merge both browser windows":{},
   "take brave windows from w2 to w3 and merge both":{"source":"2","destination":"3"},
   "move brave windows from workspace 4 into workspace 7 then merge":{"source":"4","destination":"7"},
  }
  for prompt,args in cases.items():
   got=panel.trusted_fast_action(prompt)
   if got!=("desktop__merge_brave_windows",args):raise AssertionError((prompt,got))
  return "three differently ordered merge requests use the same deterministic normal-Brave action"
 check("Flexible normal-Brave merge routes",flexible_merge_routes)
 def complete_action_sequences():
  panel=McpPanel.__new__(McpPanel)
  twelve=[{"tool":"research__web_search","arguments":{"query":str(index)}} for index in range(12)]
  panel.validate_action_sequence(twelve)
  try:panel.validate_action_sequence(twelve+[twelve[0]])
  except ValueError:pass
  else:raise AssertionError("executor would silently truncate a long plan")
  duplicate={"tool":"system__file_trash","arguments":{"path":"/tmp/a"}}
  try:panel.validate_action_sequence([duplicate,duplicate])
  except ValueError:pass
  else:raise AssertionError("duplicate sensitive mutation was accepted")
  return "all validated actions execute; overlong plans and duplicate sensitive mutations fail before side effects"
 check("Complete bounded action execution",complete_action_sequences)
 def semantic_family_routing():
  panel=McpPanel.__new__(McpPanel)
  tools=[
   {"name":"research__scholarly_search","server":"research","description":"Search scholarly papers","inputSchema":{"type":"object"}},
   {"name":"packages__software_install_product","server":"packages","description":"Install resolved software","inputSchema":{"type":"object"}},
   {"name":"brain__brain_remember","server":"brain","description":"Remember a durable note","inputSchema":{"type":"object"}},
   {"name":"desktop__launch_application","server":"desktop","description":"Launch application","inputSchema":{"type":"object"}},
  ]
  cases={"reserch lattest scolar papers":"research","instal this softwere":"packages","remeber this in my brian":"brain"}
  for prompt,family in cases.items():
   selected=panel.select_tools(prompt,tools)
   if not any(item["server"]==family for item in selected):raise AssertionError((prompt,[item["server"] for item in selected]))
  return "fuzzy semantic routing reaches research, packages and Brain despite heavily misspelled intent"
 check("Semantic MCP family routing",semantic_family_routing)
 def adaptive_tool_reliability():
  panel=McpPanel.__new__(McpPanel);panel.tool_stats={"browser__browser_click":{"success":1,"failure":4,"streak":-3,"cooldown_until":__import__("time").time()+120,"latency_total":12,"latency_samples":5}}
  if not panel.tool_in_cooldown("browser__browser_click"):raise AssertionError("repeatedly broken tool was not circuit-broken")
  context=panel.tool_health_context([{"name":"browser__browser_click"}])
  if '"failure": 4' not in context or '"streak": -3' not in context:raise AssertionError(context)
  panel.tool_stats["browser__browser_click"]["cooldown_until"]=0
  if panel.tool_in_cooldown("browser__browser_click"):raise AssertionError("expired tool cooldown remained active")
  return "tool success, failure, latency and streak evidence drive temporary backend circuit breaking"
 check("Adaptive MCP tool reliability",adaptive_tool_reliability)
 def idempotent_preflight():
  panel=McpPanel.__new__(McpPanel)
  checkpoint={"desktop":{"active_workspace":"3","windows":[]},"paths":{}}
  yes,_=panel.effect_already_satisfied("desktop__open_workspace",{"workspace":"w3"},checkpoint)
  closed,_=panel.effect_already_satisfied("desktop__close_application",{"application":"brave"},checkpoint)
  if not yes or not closed:raise AssertionError("already-satisfied desktop state was not recognized")
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/"note.txt";path.write_text("same")
   same,_=panel.effect_already_satisfied("system__file_create",{"path":str(path),"content":"same"},checkpoint)
   changed,_=panel.effect_already_satisfied("system__file_create",{"path":str(path),"content":"different"},checkpoint)
   directory=Path(folder)/"ready";directory.mkdir();exists,_=panel.effect_already_satisfied("desktop__create_folder",{"destination":folder,"name":"ready"},checkpoint)
  if not same or changed or not exists:raise AssertionError("filesystem idempotency decision was wrong")
  return "already-satisfied workspace, closure, file-content and folder goals skip duplicate side effects"
 check("Idempotent action preflight",idempotent_preflight)
 def semantic_memory_retrieval():
  panel=McpPanel.__new__(McpPanel)
  target={"command":"launch vscode in workspace three","result":"Visual Studio Code opened in w3","time":"old"}
  panel.memory=[target]+[{"command":f"unrelated filler {index}","result":"done","time":str(index)} for index in range(10)]
  found=panel.relevant_memory("open the code editor on workspace 3")
  if target not in found:raise AssertionError("semantically equivalent old success was not recalled")
  if semantic_similarity("remeber this note","remember this in memory")<=0:raise AssertionError("typo-tolerant semantic similarity failed")
  return "semantic aliases and fuzzy terms recall differently phrased verified behavior beyond the recent-turn window"
 check("Semantic long-term memory retrieval",semantic_memory_retrieval)
 def brave_workspace_isolation():
  import desktop_mcp_server as desktop
  w2={"address":"0x2","class":"brave-browser","pid":222,"workspace":{"name":"2"},"focusHistoryID":0,"title":"Existing W2"}
  w3={"address":"0x3","class":"brave-browser","pid":333,"workspace":{"name":"3"},"focusHistoryID":0,"title":"New W3"}
  snapshots=[[w2],[w2],[w2],[w2,w3],[w2,w3]]
  moved=[]
  with patch.object(desktop,"clients",side_effect=lambda:snapshots.pop(0) if snapshots else [w2,w3]), \
       patch.object(desktop,"is_regular_brave_window",return_value=True), \
       patch.object(desktop,"active_workspace",return_value="1"), \
       patch.object(desktop,"move_window",side_effect=lambda window,workspace:moved.append((window["address"],workspace))), \
       patch.object(desktop.subprocess,"Popen") as launched, \
       patch.object(desktop.subprocess,"run"), patch.object(desktop.time,"sleep"):
   result=desktop.open_normal_brave("https://mail.google.com","3")
  if result["address"]!="0x3" or moved:raise AssertionError((result,moved))
  if "--new-window" not in launched.call_args.args[0]:raise AssertionError("Brave was not forced to create an isolated window")
  return "existing W2 window preserved; only newly-created W3 window selected and moved"
 check("Brave workspace isolation",brave_workspace_isolation)
 def immediate_cancellation():
  class Process:
   def __init__(self):self.terminated=False
   def terminate(self):self.terminated=True
   def wait(self,timeout=None):return 0
  process=Process(); flow=FlowPanel.__new__(FlowPanel)
  flow.external_lock=__import__("threading").Lock();flow.external_processes={process};flow.dock=type("Dock",(),{"pages":{}})()
  flow.cancel_external_requests()
  if not process.terminated:raise AssertionError("active cloud bridge was not terminated")
  return "active cloud bridge terminated synchronously; stale callbacks are epoch-gated"
 check("Immediate cancellation",immediate_cancellation)
 def correction_learning():
  import ai_dock as dock_module
  panel=McpPanel.__new__(McpPanel);panel.memory=[{"command":"open gmail in w3","result":"moved the W2 browser","time":"now"}];panel.feedback=[];panel.conversation_state={"slots":{"last_workspace":{"value":"3"}},"events":[]}
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   with patch.object(dock_module,"MCP_MEMORY",root/"memory.json"),patch.object(dock_module,"MCP_FEEDBACK",root/"feedback.json"),patch.object(dock_module,"BRAIN_VAULT",root/"brain"):
    note=panel.record_user_feedback("no bro, do not move the W2 browser; create a new one")
    context=panel.learned_context("open gmail in another workspace")
  if not note or not panel.memory[0].get("rejected"):raise AssertionError("correction did not invalidate the wrong example")
  if "DO NOT REPEAT" not in context or "create a new one" not in context:raise AssertionError("cloud planner did not receive negative evidence")
  if panel.relevant_memory("gmail"):raise AssertionError("rejected example remained in positive memory")
  return "natural correction invalidates prior result and becomes cloud-planner negative evidence"
 check("Correction learning",correction_learning)
 def cloud_plan_validation():
  tool={"name":"desktop__open_url","inputSchema":{"type":"object","properties":{"url":{"type":"string"},"workspace":{"type":"string"}},"required":["url"],"additionalProperties":False}}
  McpPanel.validate_cloud_arguments(tool,{"url":"https://example.com","workspace":"3"})
  rejected=0
  for bad in ({"workspace":"3"},{"url":"https://example.com","invented":True},{"url":55}):
   try:McpPanel.validate_cloud_arguments(tool,bad)
   except ValueError:rejected+=1
  if rejected!=3:raise AssertionError(f"accepted {3-rejected} malformed cloud action(s)")
  nested={"name":"missions__project_build","inputSchema":{"type":"object","properties":{"files":{"type":"array","minItems":1,"maxItems":2,"items":{"type":"object","properties":{"path":{"type":"string","minLength":1},"content":{"type":"string"}},"required":["path","content"],"additionalProperties":False}}},"required":["files"],"additionalProperties":False}}
  McpPanel.validate_cloud_arguments(nested,{"files":[{"path":"app.py","content":"print(1)"}]})
  malformed=({"files":[]},{"files":[{"path":"app.py"}]},{"files":[{"path":"app.py","content":"x","shell":"bad"}]},{"files":[{"path":"a","content":"x"},{"path":"b","content":"x"},{"path":"c","content":"x"}]})
  for payload in malformed:
   try:McpPanel.validate_cloud_arguments(nested,payload)
   except ValueError:pass
   else:raise AssertionError(f"nested malformed payload passed: {payload}")
  return "recursive schemas enforce required fields, types, enums, bounds, nested arrays and closed objects before execution"
 check("Cloud plan validation",cloud_plan_validation)
 def intent_guard():
  McpPanel.validate_plan_intent("open gmail in w3",[{"tool":"desktop__open_url","arguments":{"url":"https://mail.google.com","workspace":"3"}}])
  bad=0
  cases=[("open gmail in w3",[{"tool":"desktop__open_url","arguments":{"url":"https://mail.google.com","workspace":"2"}}]),("open gmail in w3",[{"tool":"desktop__move_windows","arguments":{"destination":"3"}}]),("check vscode version",[{"tool":"packages__package_install_or_update","arguments":{"package":"code"}}])]
  for command,actions in cases:
   try:McpPanel.validate_plan_intent(command,actions)
   except ValueError:bad+=1
  if bad!=len(cases):raise AssertionError("contradictory or unauthorized plan passed intent guard")
  return "explicit workspace and move/install authority preserved from original wording"
 check("Cloud intent guard",intent_guard)
 def adaptive_verification():
  one=[{"tool":"desktop__open_url","arguments":{"url":"https://example.com"}}]
  two=one+[{"tool":"browser__browser_search","arguments":{"site":"google","query":"test"}}]
  if McpPanel.needs_post_verification("open example.com",one):raise AssertionError("single obvious action was slowed by verification")
  if not McpPanel.needs_post_verification("open it and then search for loops",one):raise AssertionError("compound wording skipped verification")
  if not McpPanel.needs_post_verification("do these actions",two):raise AssertionError("multi-action plan skipped verification")
  return "single actions stay fast; compound and multi-action plans require evidence-based verification"
 check("Adaptive result verification",adaptive_verification)
 def independent_plan_critic():
  panel=McpPanel.__new__(McpPanel)
  simple=[{"tool":"desktop__open_url","arguments":{"url":"https://example.com"}}]
  complex_plan=simple+[{"tool":"browser__browser_search","arguments":{"site":"google","query":"test"}},{"tool":"documents__create_text","arguments":{"path":"report.txt","content":"done"}}]
  risky=[{"tool":"packages__software_install_product","arguments":{"product":"vlc"}}]
  if panel.needs_plan_critic("open example.com",simple):raise AssertionError("simple safe action was slowed by critic")
  if not panel.needs_plan_critic("research this, save it and open it",complex_plan):raise AssertionError("three-step plan skipped critic")
  if not panel.needs_plan_critic("install vlc",risky):raise AssertionError("high-impact plan skipped critic")
  return "simple action remains instant; multi-step and high-impact plans require independent cloud review"
 check("Independent cloud plan critic",independent_plan_critic)
 def cloud_authored_missions():
  import mission_mcp_server as mission
  tools={item["name"]:item for item in mission.TOOLS}
  project_required=set(tools["project_build"]["inputSchema"]["required"])
  video_required=set(tools["video_create"]["inputSchema"]["required"])
  source=(ROOT/"mission_mcp_server.py").read_text()
  if not {"name","specification","files"}<=project_required:raise AssertionError(project_required)
  if not {"topic","narration","scenes"}<=video_required:raise AssertionError(video_required)
  if not {"output_folder","output_filename"}<=set(tools["video_create"]["inputSchema"]["properties"]):raise AssertionError("video destination controls missing")
  if "ollama_json" in source or "11434/api/chat" in source:raise AssertionError("hidden local-model reasoning remains in mission executor")
  return "cloud planner must supply project files and video script/scenes; local executor only validates and renders"
 check("Cloud-authored high-level missions",cloud_authored_missions)
 def deterministic_video_delivery():
  panel=McpPanel.__new__(McpPanel);panel.active_obligations=panel.request_obligations("create a folder name AI video inside the document and create a video of a monkey eating banana and save that video inside that folder")
  actions=panel.deterministic_compound_fallback("create a folder name AI video inside the document and create a video of a monkey eating banana and save that video inside that folder")
  if not actions or len(actions)!=1:raise AssertionError(actions)
  args=actions[0]["arguments"]
  if args.get("output_folder")!=str(Path.home()/"Documents/AI video") or args.get("output_filename")!="a-monkey-eating-banana.mp4":raise AssertionError(args)
  if set(actions[0].get("covers",[]))!={"intent_1","intent_2","intent_3"}:raise AssertionError(actions[0].get("covers"))
  return "the user's exact failed sentence maps instantly to one verified video mission with explicit folder and filename"
 check("Deterministic video delivery route",deterministic_video_delivery)
 def procedural_learning():
  import ai_dock as dock_module
  panel=McpPanel.__new__(McpPanel);panel.procedures={};panel.tools=[
   {"name":"desktop__open_url","inputSchema":{"type":"object","properties":{"url":{"type":"string"},"workspace":{"type":"string"}},"required":["url"],"additionalProperties":False}},
   {"name":"browser__browser_search","inputSchema":{"type":"object","properties":{"site":{"type":"string"},"query":{"type":"string"}},"required":["query"],"additionalProperties":False}},
  ]
  actions=[{"tool":"desktop__open_url","arguments":{"url":"https://example.com","workspace":"3"}},{"tool":"browser__browser_search","arguments":{"site":"google","query":"loops"}}]
  with tempfile.TemporaryDirectory() as folder:
   with patch.object(dock_module,"LEARNED_PROCEDURES",Path(folder)/"procedures.json"):
    panel.learn_procedure("open example in w3 and then search loops",actions,"verified complete")
    panel.learn_procedure("open example in w3 and then search loops",actions,"verified complete again")
    context=panel.procedure_context("search loops after opening example in workspace 3")
    reusable=panel.trusted_learned_procedure("open example in w3 and then search loops")
  if len(panel.procedures)!=1 or "verified_actions" not in context or reusable!=actions:raise AssertionError("repeatedly verified procedure was not executable")
  return "two verified successes promote an exact workflow from context example to schema-revalidated executable skill"
 check("Procedural learning",procedural_learning)
 def universal_runtime():
  sample=[{"name":"desktop__open_url","server":"desktop","description":"Open website in normal browser","inputSchema":{"type":"object"}},
          {"name":"documents__create_pdf","server":"documents","description":"Create a PDF report","inputSchema":{"type":"object"}}]
  found=CapabilityIndex(sample).search("make a pdf document",limit=3)
  if not found or found[0]["name"]!="documents__create_pdf":raise AssertionError(found)
  typo_sample=sample+[{"name":"desktop__launch_application","server":"desktop","description":"Launch an installed application","inputSchema":{"type":"object"}}]
  typo_found=CapabilityIndex(typo_sample).search("lauch teh applicaton",limit=2)
  if not typo_found or typo_found[0]["name"]!="desktop__launch_application":raise AssertionError("typo-tolerant capability search failed")
  plan=validate_plan([{"id":"inspect","goal":"Inspect state","verification":"State captured"},{"id":"act","goal":"Apply change","depends_on":["inspect"],"verification":"Result confirmed"}])
  if plan[1]["depends_on"]!=["inspect"]:raise AssertionError("plan dependency validation failed")
  with tempfile.TemporaryDirectory() as folder:
   journal=TaskJournal(folder);task=journal.start("open gmail",{"token":"must-not-leak"})
   planned=[{"tool":"desktop__open_url","arguments":{"url":"https://mail.google.com"}},{"tool":"browser__browser_search","arguments":{"site":"gmail","query":"invoice"}}]
   journal.set_execution_plan(task,planned,"gemini");journal.complete_action(task,planned[0],"opened")
   recovered=TaskJournal(folder).recoverable();remaining=TaskJournal(folder).remaining_actions(recovered)
   if len(remaining)!=1 or remaining[0]["tool"]!="browser__browser_search":raise AssertionError("crash-safe ledger repeated or lost an action")
   secret_action={"tool":"system__service_manage","arguments":{"service":"demo","token":"sensitive"}}
   journal.set_execution_plan(task,[secret_action],"gemini");journal.complete_action(task,secret_action,"done")
   if TaskJournal(folder).remaining_actions(TaskJournal(folder).recoverable()):raise AssertionError("redaction changed resumed action identity")
   journal.event(task,"tool_completed",tool="desktop__open_url",arguments={"url":"https://mail.google.com"})
   if "must-not-leak" in (journal.root/f"{task['id']}.json").read_text():raise AssertionError("journal secret redaction failed")
   if journal.recoverable()["command"]!="open gmail":raise AssertionError("task recovery failed")
   journal.finish(task,"completed","done")
   if journal.recoverable() is not None or journal.recent(1)[0]["status"]!="completed":raise AssertionError("task finalization failed")
  report=completion_report("open gmail",[{"status":"completed"}],"done")
  if not report["verified"]:raise AssertionError(report)
  return "dynamic capability search + redacted per-action crash recovery + completion verifier"
 check("Universal agent runtime",universal_runtime)
 with McpConnections(CONFIG) as connections:
  tools=connections.discover(); by={tool["name"]:tool for tool in tools}; counts=Counter(tool["server"] for tool in tools)
  check("MCP discovery",lambda:f"{len(tools)} tools · {dict(counts)}")
  def mission_routing():
   panel=McpPanel.__new__(McpPanel)
   cases=("bro go through this website code and tell me what is broken","make me a video about C loops","build an application and prepare its github repo")
   for prompt in cases:
    selected=panel.select_tools(prompt,tools)
    if not any(item.get("server")=="missions" for item in selected):raise AssertionError(f"Mission tools missing for: {prompt}")
   required={"missions__website_investigate","missions__project_build","missions__github_publish","missions__video_create"}
   if not required<=set(by):raise AssertionError(required-set(by))
   return f"{len(cases)} twisted high-level prompts + {len(required)} vertical mission tools"
  check("Mission intent routing",mission_routing)
  def research_routing():
   panel=McpPanel.__new__(McpPanel)
   prompts=("bro find reliable information about quantum computing online","check recent papers about local AI agents","fetch this public JSON API and explain it","read the latest entries from this RSS feed","crawl this website and map its pages","show me the historical versions from the wayback machine")
   for prompt in prompts:
    if not any(item.get("server")=="research" for item in panel.select_tools(prompt,tools)):raise AssertionError(f"research tools missing for {prompt}")
   required={"research__web_search","research__webpage_extract","research__research_bundle","research__knowledge_lookup","research__scholarly_search","research__json_api_get","research__download_verified","research__site_crawl","research__compare_webpages","research__wayback_history"}
   if not required<=set(by):raise AssertionError(required-set(by))
   return f"{len(prompts)} natural internet intents + {len(required)} evidence tools"
  check("Internet research routing",research_routing)
  def knowledge_routing():
   panel=McpPanel.__new__(McpPanel);prompts=("index my Documents folder privately","search my files for the armstrong code","reindex my local knowledge base","find this idea in my PDFs")
   for prompt in prompts:
    if not any(item.get("server")=="knowledge" for item in panel.select_tools(prompt,tools)):raise AssertionError(f"knowledge tools missing for {prompt}")
   required={"knowledge__knowledge_index_path","knowledge__knowledge_search","knowledge__knowledge_context","knowledge__knowledge_status","knowledge__knowledge_reindex_changed"}
   if not required<=set(by):raise AssertionError(required-set(by))
   return f"{len(prompts)} private knowledge intents + {len(required)} index/retrieval tools"
  check("Local knowledge routing",knowledge_routing)
  def call(name,args):
   response=connections.call(by[name],args); return "\n".join(item.get("text","") for item in response.get("content",[]) if item.get("type")=="text")
  check("Full health",lambda:call("automation__automation_health_check",{}))
  check("Live knowledge lookup",lambda:call("research__knowledge_lookup",{"topic":"C programming language","language":"en"}))
  check("Live webpage extraction",lambda:call("research__webpage_extract",{"url":"https://example.com","max_chars":4000}))
  check("Live webpage comparison",lambda:call("research__compare_webpages",{"urls":["https://example.com","https://www.iana.org/help/example-domains"],"max_chars_each":3000}))
  check("Live scholarly search",lambda:call("research__scholarly_search",{"query":"large language model tool use","limit":3}))
  check("Local knowledge status",lambda:call("knowledge__knowledge_status",{}))
  check("Cloud-approved knowledge context",lambda:call("knowledge__knowledge_context",{"query":"AI Dock automation memory","max_chars":2500,"cloud_only":True}))
  check("Private source policy",lambda:call("knowledge__knowledge_sources",{"limit":10}))
  check("Learned procedure registry",lambda:call("automation__learned_procedure_list",{"limit":10}))
  check("Brain graph",lambda:call("brain__brain_stats",{}))
  check("Brain context",lambda:call("brain__brain_context",{"query":"AI Dock memory automation","max_chars":1800}))
  check("Developer map",lambda:call("developer__project_overview",{"path":str(ROOT),"depth":1}))
  check("C diagnostics",lambda:call("developer__analyze_c_file",{"path":str(ROOT/"examples/hello.c"),"standard":"c17"}))
  check("Workspace map",lambda:call("workspace__workspace_summary",{}))
  check("Media state",lambda:call("media__media_status",{}))
  check("Network state",lambda:call("media__network_status",{}))
  check("Recording safety",lambda:call("media__screen_record_status",{}))
  check("Data validation",lambda:call("data__data_validate",{"path":str(CONFIG)}))
  check("Fast file search",lambda:call("operations__find_files",{"path":str(ROOT),"query":"mcp_server","kind":"file","limit":20}))
  check("Storage map",lambda:call("operations__storage_map",{"path":str(ROOT)}))
  check("Resource snapshot",lambda:call("monitor__resource_snapshot",{}))
  check("Monitor rules",lambda:call("monitor__monitor_rule_list",{}))
  check("System-aware software profile",lambda:call("packages__system_software_profile",{}))
  check("Exact Antigravity identity",lambda:call("packages__software_resolve",{"product":"Antigravity IDE","vendor":"Google","kind":"IDE"}))
 passed=sum(item["passed"] for item in checks); report={"passed":passed,"total":len(checks),"checks":checks}
 print(json.dumps(report,indent=2,ensure_ascii=False)); return 0 if passed==len(checks) else 1
if __name__=="__main__": raise SystemExit(main())
