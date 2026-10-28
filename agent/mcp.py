"""Small stdio MCP client: initialize → initialized → tools/list → tools/call."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


class MCPClient:
    def __init__(self, command, args, cancel=None, cwd=None):
        self.cancel = cancel or threading.Event()
        self.proc = subprocess.Popen([command, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8", cwd=cwd)
        self.inbox = queue.Queue()
        self.counter = 0
        def reader():
            try:
                for line in self.proc.stdout:
                    self.inbox.put(json.loads(line))
            except Exception as exc:
                self.inbox.put({"error": str(exc)})
            self.inbox.put(None)
        threading.Thread(target=reader, daemon=True).start()
        try:
            result = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "little-cursor", "version": "1.0.0"}})
            if result.get("protocolVersion") != "2025-06-18":
                raise ValueError("不支持 MCP server 的协议版本")
            self.notify("notifications/initialized")
            self.tools = self.request("tools/list", {}).get("tools", [])
        except Exception:
            self.close()
            raise

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params, timeout=15):
        self.counter += 1
        rid = self.counter
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n")
        self.proc.stdin.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.cancel.is_set():
                raise RuntimeError("MCP 调用已中断")
            try:
                msg = self.inbox.get(timeout=0.1)
            except queue.Empty:
                continue
            if msg is None:
                raise RuntimeError("MCP server 已断开")
            if msg.get("id") != rid:
                continue
            if "error" in msg:
                raise RuntimeError(str(msg["error"]))
            return msg["result"]
        raise TimeoutError("MCP 调用超过 15 秒")

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        for stream in (self.proc.stdin, self.proc.stdout):
            if stream:
                stream.close()


def connect(config_path, resource_root, cancel):
    config = json.loads(Path(config_path).read_text())
    clients, schemas = {}, []
    try:
        for name, cfg in config.get("mcpServers", {}).items():
            command = sys.executable if cfg["command"] == "${PYTHON}" else cfg["command"]
            args = [s.replace("${APP_ROOT}", str(resource_root)) for s in cfg.get("args", [])]
            if getattr(sys, 'frozen', False) and cfg['command'] == '${PYTHON}' and args == [str(Path(resource_root) / 'examples/mcp_server.py')]:
                args = ['--mcp-server']
            client = MCPClient(command, args, cancel, cwd=resource_root)
            clients[name] = client
            for tool in client.tools:
                schemas.append({"type": "function", "function": {"name": f"mcp__{name}__{tool['name']}",
                    "description": "[外部 MCP] " + tool.get("description", ""), "parameters": tool["inputSchema"]}})
        return clients, schemas
    except Exception:
        for client in clients.values():
            client.close()
        raise
