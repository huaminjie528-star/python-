"""Reproducible tool traces without a model key; approvals auto-granted in temp fixtures only."""
import json
from pathlib import Path
import shutil
import tempfile
import threading
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.loop import run

ROOT=Path(__file__).resolve().parent.parent


def main():
    lines=['# 实际运行记录\n', '以下由 `python3 scripts/collect_trace.py` 实际生成。决策为离线固定脚本，工具、子进程、测试和 MCP 均真实执行。仅临时验收目录自动批准，桌面使用逐次审批。\n']
    for task in ['修复 mean', '失败恢复', 'MCP']:
        lines.append('## '+task+'\n')
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp)/'workspace'
            shutil.copytree(ROOT/'examples/demo_workspace',workspace)
            def emit(kind,data):
                lines.extend(['### '+kind+'\n','```json\n'+json.dumps(data,ensure_ascii=False,indent=2)+'\n```\n'])
            run(task,workspace,{'mode':'demo','mcp_enabled':True},emit,threading.Event(),lambda _:True,ROOT)
    (ROOT/'docs/trace.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':main()
