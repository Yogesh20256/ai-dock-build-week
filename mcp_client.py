"""Small synchronous MCP stdio client used by AI Dock.

MCP stdio messages are JSON-RPC objects separated by newlines. Each connection
is short-lived and closed after discovery or an agent run.
"""
import json
import os
import subprocess
import threading


class McpError(RuntimeError):
    pass


class McpServer:
    def __init__(self, name, config):
        self.name, self.config, self.next_id = name, config, 1
        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in config.get("env", {}).items()})
        try:
            self.process = subprocess.Popen(
                [config["command"], *config.get("args", [])],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, env=env, cwd=config.get("cwd") or None,
            )
        except (KeyError, OSError) as error:
            raise McpError(f"Could not start MCP server {name}: {error}") from error
        self.stderr_lines = []
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "AI Dock", "version": "1.0"},
        })
        self.notify("notifications/initialized", {})

    def _read_stderr(self):
        for line in self.process.stderr:
            self.stderr_lines.append(line.rstrip())
            self.stderr_lines = self.stderr_lines[-20:]

    def _send(self, message):
        if self.process.poll() is not None:
            detail = "\n".join(self.stderr_lines[-5:])
            raise McpError(f"MCP server {self.name} exited unexpectedly. {detail}")
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def request(self, method, params=None):
        request_id = self.next_id; self.next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        while True:
            line = self.process.stdout.readline()
            if not line:
                detail = "\n".join(self.stderr_lines[-5:])
                raise McpError(f"MCP server {self.name} closed its output. {detail}")
            try: message = json.loads(line)
            except json.JSONDecodeError: continue
            if message.get("id") != request_id: continue
            if "error" in message:
                error = message["error"]
                raise McpError(f"{self.name}: {error.get('message', error)}")
            return message.get("result", {})

    def tools(self):
        return self.request("tools/list").get("tools", [])

    def call(self, tool_name, arguments):
        return self.request("tools/call", {"name": tool_name, "arguments": arguments})

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired: self.process.kill()


class McpConnections:
    def __init__(self, config_path):
        config = json.loads(config_path.read_text())
        self.servers = {}
        try:
            for name, item in config.get("servers", {}).items():
                if item.get("enabled", True): self.servers[name] = McpServer(name, item)
        except Exception:
            self.close(); raise

    def discover(self):
        discovered = []
        for server_name, server in self.servers.items():
            for tool in server.tools():
                public_name = f"{server_name}__{tool['name']}"
                discovered.append({
                    "server": server_name,
                    "original_name": tool["name"],
                    "name": public_name,
                    "description": f"[{server_name}] {tool.get('description', '')}",
                    "inputSchema": tool.get("inputSchema", {"type": "object", "properties": {}}),
                })
        return discovered

    def call(self, tool, arguments):
        return self.servers[tool["server"]].call(tool["original_name"], arguments)

    def close(self):
        for server in self.servers.values(): server.close()

    def __enter__(self): return self
    def __exit__(self, *_): self.close()
