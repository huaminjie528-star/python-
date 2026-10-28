"""OpenAI-compatible tool calling, plus an explicitly scripted offline fixture."""
import json
import queue
import threading
import time
import urllib.error
import urllib.request


class ChatModel:
    def __init__(self, settings, cancel):
        self.settings, self.cancel = settings, cancel

    def reply(self, messages, schemas):
        settings = self.settings
        url = settings['base_url'].rstrip('/') + '/chat/completions'
        if not url.startswith('https://') and not url.startswith(('http://127.0.0.1:', 'http://localhost:')):
            raise ValueError('远程 API 必须使用 HTTPS')
        payload = {"model": settings['model'], "messages": messages, "tools": schemas,
                   "tool_choice": "auto", "max_completion_tokens": 2048}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
              headers={"Authorization": "Bearer " + settings['api_key'], "Content-Type": "application/json"})
        inbox = queue.Queue()
        def request():
            try:
                with urllib.request.urlopen(req, timeout=45) as response:
                    raw = response.read(4_000_001)
                    if len(raw) > 4_000_000:
                        raise ValueError('模型响应超过 4 MB')
                    inbox.put((True, json.loads(raw)['choices'][0]['message']))
            except urllib.error.HTTPError as exc:
                inbox.put((False, f'模型 API HTTP {exc.code}，请检查 Key、模型名和服务地址'))
            except Exception as exc:
                inbox.put((False, f'模型请求失败：{type(exc).__name__}'))
        threading.Thread(target=request, daemon=True).start()
        end = time.monotonic() + 50
        while time.monotonic() < end:
            if self.cancel.is_set():
                raise RuntimeError('模型等待已中断，未继续执行工具；已发出的请求可能仍由服务方计费')
            try:
                ok, value = inbox.get(timeout=0.1)
            except queue.Empty:
                continue
            if not ok:
                raise RuntimeError(value)
            return value
        raise TimeoutError('模型响应超时')


class DemoModel:
    """Deterministic test scenario. Never presented as real LLM inference."""
    def __init__(self, task):
        self.index = 0
        if '中断' in task:
            self.actions = [('bash', {'command': "python3 -c 'import time; time.sleep(60)'", 'timeout': 90})]
        elif 'MCP' in task.upper():
            self.actions = [('mcp__course__describe_project', {})]
        elif '失败' in task or '恢复' in task:
            self.actions = [('write', {'path': 'recovery.txt', 'content': 'alpha = 1\nbeta = 1\n'}),
                ('edit', {'path': 'recovery.txt', 'old': '1', 'new': '2'}),
                ('read', {'path': 'recovery.txt'}),
                ('edit', {'path': 'recovery.txt', 'old': 'beta = 1', 'new': 'beta = 2'})]
        else:
            self.actions = [('read', {'path': 'stats.py'}),
                ('bash', {'command': 'python3 -m unittest -v test_stats.py', 'timeout': 15}),
                ('edit', {'path': 'stats.py', 'old': 'if not nums:\n        return 0',
                          'new': 'if not nums:\n        raise ValueError("nums must not be empty")'}),
                ('bash', {'command': 'python3 -m unittest -v test_stats.py', 'timeout': 15})]

    def reply(self, messages, schemas):
        if self.index >= len(self.actions):
            failures = [m for m in messages if m['role'] == 'tool' and '"ok": false' in str(m.get('content'))]
            return {'role': 'assistant', 'content': '离线脚本已结束。请查看上方真实工具输出与测试退出码。' + ('过程中有失败，已展示后续恢复步骤。' if failures else '')}
        name, args = self.actions[self.index]
        self.index += 1
        return {'role': 'assistant', 'content': '离线验收脚本：执行下一步。', 'tool_calls': [
            {'id': f'demo-{self.index}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}
