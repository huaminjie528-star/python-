"""Four tools. File operations stay under the selected workspace."""
import base64
import difflib
import mimetypes
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time


def schema(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required,
                           "additionalProperties": False}}}


S = lambda description: {"type": "string", "description": description}
SCHEMAS = [
    schema("read", "读取工作区文本（1 起始行号、分页）或图片。先读再编辑。", {"path": S("相对路径"), "offset": {"type": "integer"}, "limit": {"type": "integer"}}, ["path"]),
    schema("write", "新建或完整写入文件。先展示 diff 并等待用户批准，自动建父目录。", {"path": S("相对路径"), "content": S("完整文本")}, ["path", "content"]),
    schema("edit", "仅当 old 精确出现一次时替换为 new。重复或找不到须补读上下文。先展示 diff 供批准。", {"path": S("相对路径"), "old": S("唯一原文"), "new": S("替换文本")}, ["path", "old", "new"]),
    schema("bash", "在工作区运行 shell 命令（需用户批准）。用于搜索、Git、测试。返回输出、退出码，支持超时与截断。", {"command": S("shell 命令"), "timeout": {"type": "number"}}, ["command"]),
]


class Tools:
    def __init__(self, root, cancel=None, approve=None):
        self.root = Path(root).resolve()
        self.cancel = cancel or threading.Event()
        self.approve = approve or (lambda proposal: False)

    def path(self, path):
        p = (self.root / path).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError("路径越界：只能访问选定工作区")
        if any(part in {".git", ".ssh", ".agent"} or part.startswith('.env') for part in p.relative_to(self.root).parts):
            raise ValueError("禁止访问密钥或内部目录")
        return p

    def read(self, path, offset=1, limit=200):
        p = self.path(path)
        if not p.is_file():
            raise ValueError(f"文件不存在：{path}。请用 bash 查看目录。")
        mime = mimetypes.guess_type(str(p))[0] or ""
        if mime in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
            if p.stat().st_size > 4_000_000:
                raise ValueError("图片超过 4 MB，请先缩小")
            return {"content": [{"type": "image", "mimeType": mime, "data": base64.b64encode(p.read_bytes()).decode()}]}
        if not isinstance(offset, int) or not isinstance(limit, int) or offset < 1 or not 1 <= limit <= 500:
            raise ValueError("offset >= 1，limit 为 1–500 的整数")
        lines = []
        total = 0
        used = 0
        shortened = False
        final_newline = False
        with p.open(encoding="utf-8") as f:
            for total, line in enumerate(f, 1):
                final_newline = line.endswith('\n')
                if total >= offset and len(lines) < limit and used < 24000:
                    fragment = line.rstrip('\n')[:4000]
                    shortened |= len(line.rstrip('\n')) > 4000
                    lines.append(f"{total:4d} | {fragment}")
                    used += len(fragment)
        end = offset + len(lines) - 1
        return {"path": path, "text": "\n".join(lines), "total_lines": total,
                "remaining_lines": max(0, total - max(end, offset - 1)), "next_offset": end + 1,
                "shortened_lines": shortened, "final_newline": final_newline,
                "note": "单行最多显示 4000 字符，页最多约 24000 字符"}

    def _change(self, path, old, new):
        if len(new.encode()) > 2_000_000:
            raise ValueError("写入文件超过 2 MB")
        p = self.path(path)
        diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=path, tofile=path))
        if old == new:
            return {"path": path, "changed": False, "diff": ""}
        if not self.approve({"kind": "change", "path": path, "diff": diff[:40000]}):
            raise ValueError("用户拒绝或中断了修改")
        if self.cancel.is_set():
            raise ValueError("任务已中断")
        if (p.read_text(encoding="utf-8") if p.exists() else "") != old:
            raise ValueError("批准期间文件发生变化，请重新读取")
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".agent-write-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new)
                f.flush()
                os.fsync(f.fileno())
            if p.exists():
                os.chmod(tmp, p.stat().st_mode)
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return {"path": path, "old_lines": len(old.splitlines()), "new_lines": len(new.splitlines()), "diff": diff[:40000]}

    def write(self, path, content):
        p = self.path(path)
        old = p.read_text(encoding="utf-8") if p.exists() else ""
        return self._change(path, old, content)

    def edit(self, path, old, new):
        text = self.path(path).read_text(encoding="utf-8")
        count = text.count(old) if old else 0
        if count != 1:
            raise ValueError(f"old 精确出现 {count} 次，需要且只能出现 1 次。请 read 后扩大上下文。")
        return self._change(path, text, text.replace(old, new, 1))

    def bash(self, command, timeout=30):
        timeout = max(0.1, min(float(timeout), 120))
        if not self.approve({"kind": "command", "command": command, "timeout": timeout}):
            raise ValueError("用户拒绝或中断了命令")
        if self.cancel.is_set():
            raise ValueError("任务已中断")
        # Temporary files bound RAM even when the child emits unbounded output.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(command, shell=True, cwd=self.root, stdout=out, stderr=err,
                                    start_new_session=True, executable="/bin/bash" if os.name != "nt" else None)
            start = time.monotonic()
            reason = None
            while proc.poll() is None:
                if self.cancel.is_set() or time.monotonic() - start >= timeout or out.tell() + err.tell() > 8_000_000:
                    reason = "cancelled" if self.cancel.is_set() else ("output_limit" if out.tell() + err.tell() > 8_000_000 else "timeout")
                    break
                time.sleep(0.04)
            # Kill the process group, including descendants, even if the shell exited.
            try:
                if os.name != "nt":
                    os.killpg(proc.pid, signal.SIGKILL)
                elif proc.poll() is None:
                    proc.kill()
            except ProcessLookupError:
                pass
            proc.wait()
            values = []
            truncated = False
            for stream in (out, err):
                stream.seek(0)
                raw = stream.read(16001)
                truncated |= len(raw) > 16000
                values.append(raw[:16000].decode("utf-8", "replace"))
            return {"stdout": values[0], "stderr": values[1], "exit_code": proc.returncode,
                    "reason": reason, "truncated": truncated, "seconds": round(time.monotonic() - start, 3)}

    def call(self, name, args):
        try:
            if name not in {"read", "write", "edit", "bash"}:
                raise ValueError(f"未知工具：{name}")
            if self.cancel.is_set():
                raise ValueError("任务已中断")
            result = getattr(self, name)(**args)
            if name == 'bash' and (result['exit_code'] != 0 or result['reason']):
                return {"ok": False, "result": result, "error": f"命令未成功：exit={result['exit_code']}，原因={result['reason'] or 'nonzero_exit'}"}
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
