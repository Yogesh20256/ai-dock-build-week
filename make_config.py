#!/usr/bin/env python3
import json, sys
from pathlib import Path

root=Path(sys.argv[1]).resolve(); output=Path(sys.argv[2]).expanduser()
venv=root/'.venv/bin/python'; system=Path(sys.executable)
servers={}
for name,script in {
 'desktop':'desktop_mcp_server.py','brain':'brain_mcp_server.py','packages':'package_mcp_server.py',
 'system':'system_mcp_server.py','documents':'document_mcp_server.py','automation':'automation_mcp_server.py',
 'developer':'developer_mcp_server.py','workspace':'workspace_mcp_server.py','media':'media_mcp_server.py',
 'data':'data_mcp_server.py','operations':'operations_mcp_server.py','monitor':'monitor_mcp_server.py',
 'missions':'mission_mcp_server.py','research':'research_mcp_server.py','knowledge':'knowledge_mcp_server.py',
}.items():
 servers[name]={'command':str(venv if name=='missions' else system),'args':[str(root/script)],'enabled':True}
servers['browser']={'command':str(venv),'args':[str(root/'browser_mcp_server.py')],'enabled':False}
if Path('/usr/bin/uvx').exists():servers['web']={'command':'/usr/bin/uvx','args':['mcp-server-fetch'],'enabled':True}
output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps({'servers':servers},indent=2)+'\n')
print(output)
