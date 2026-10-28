"""Independent demo server. stdout contains protocol messages only."""
import json
import sys


def main():
    initialized = False
    for line in sys.stdin:
        rid = None
        try:
            req = json.loads(line)
            rid, method = req.get("id"), req.get("method")
            if method == "notifications/initialized":
                initialized = True
                continue
            if rid is None:
                continue
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                          "serverInfo": {"name": "course-helper", "version": "1.0.0"}}
            elif not initialized:
                raise ValueError("请先初始化")
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [{"name": "describe_project", "description": "获取本课程项目的验收清单。用户询问作业验收时使用。",
                    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}]}
            elif method == "tools/call":
                params = req.get("params", {})
                if params.get("name") != "describe_project" or params.get("arguments", {}):
                    result = {"isError": True, "content": [{"type": "text", "text": "未知工具或参数"}]}
                else:
                    result = {"content": [{"type": "text", "text": "验收：桌面窗口、read/write/edit/bash、diff 审批、中断、真实 MCP、公开仓库与安装包。"}]}
            else:
                print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}), flush=True)
                continue
            print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": str(exc)}}), flush=True)


if __name__ == "__main__":
    main()
