#!/usr/bin/env python3
"""Launch an isolated AI Dock window on a requested page for screenshots."""
import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from gi.repository import GLib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser()
parser.add_argument("page",choices=("flow","flow-review","mcp","control","qwen","ai-menu","web-menu"))
args=parser.parse_args()

spec=importlib.util.spec_from_file_location("ai_dock_demo",ROOT/"ai_dock.py")
dock=importlib.util.module_from_spec(spec);spec.loader.exec_module(dock)
base=Path(tempfile.gettempdir())/"ai-dock-build-week-demo";config=base/"config";data=base/"data"
config.mkdir(parents=True,exist_ok=True);data.mkdir(parents=True,exist_ok=True)

dock.APP_ID=f"io.github.yogesh.AIDockDemo.{args.page.replace('-', '')}"
dock.CONFIG=config;dock.DATA=data;dock.MCP_CONFIG=config/"mcp_servers.json"
dock.SETTINGS=config/"settings.json";dock.MCP_MEMORY=data/"mcp_memory.json"
dock.MCP_FEEDBACK=data/"intent_feedback.json";dock.MCP_STATE=data/"conversation_state.json"
dock.MCP_SESSIONS=data/"mcp_sessions.json"
if not dock.MCP_CONFIG.exists():
    source=Path.home()/".config/ai-dock/mcp_servers.json"
    dock.MCP_CONFIG.write_text(source.read_text() if source.exists() else '{"servers":{}}\n')

class DemoApp(dock.App):
    def do_activate(self):
        super().do_activate()
        page="flow" if args.page=="flow-review" else "mcp" if args.page in ("ai-menu","web-menu") else args.page
        if page in self.dock.pages:self.dock.select(None,page)
        self.expand()
        if args.page=="flow-review":
            self.dock.pages["flow"].mode.set_selected(1)
        elif args.page=="ai-menu":
            GLib.timeout_add(700,lambda: self.dock.nav_menu.set_active(True) or False)
        elif args.page=="web-menu":
            GLib.timeout_add(700,lambda: self.dock.cloud_menu.set_active(True) or False)

raise SystemExit(DemoApp().run([os.fspath(Path(__file__)),"--show"]))
