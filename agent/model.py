"""OpenAI-compatible tool calling, plus an explicitly scripted offline fixture."""
import json
import queue
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def request_payload(settings, messages, schemas):
    """Keep provider-specific parameters out of the shared agent loop."""
    payload = {"model": settings['model'], "messages": messages, "tools": schemas,
               "tool_choice": "auto"}
    if urlsplit(settings['base_url']).hostname == 'api.deepseek.com':
        payload.update(max_tokens=2048, thinking={"type": "disabled"})
    else:
        payload['max_completion_tokens'] = 2048
    return payload


def api_error(exc):
    """Classify bounded provider error codes without echoing response bodies or keys."""
    code = ''
    try:
        details = json.loads(exc.read(65536)).get('error', {})
        if isinstance(details, dict):
            code = str(details.get('code') or details.get('type') or '')
    except (ValueError, OSError, AttributeError):
        pass
    if exc.code == 401:
        hint = 'API Key 无效或已失效，请重新填写对应服务商的密钥'
    elif exc.code == 402 or code in {'insufficient_quota', 'credit_balance_exhausted', 'insufficient_balance'}:
        hint = 'API 可用额度不足，请检查服务商平台的 API 余额或额度'
    elif code in {'organization_spend_limit_exceeded', 'project_spend_limit_exceeded', 'organization_usage_limit_exceeded'}:
        hint = '已达到 API 账户或项目的用量上限，请检查平台 Limits'
    elif exc.code == 429:
        hint = '请求受限：可能是频率限制或账户额度限制，请检查 API 平台的余额与 Limits，避免连续重试'
    elif exc.code == 403:
        hint = 'API 访问被拒绝，请检查账户、模型权限及服务可用地区'
    elif exc.code == 404:
        hint = '模型或接口不存在，请检查模型名称和 API Base URL'
    elif exc.code == 400:
        hint = '请求参数不兼容，请检查模型是否支持当前工具调用接口'
    elif exc.code >= 500:
        hint = '模型服务暂时不可用，请稍后重试'
    else:
        hint = '请求未成功，请检查 API 配置和账户状态'
    return f'模型 API HTTP {exc.code}：{hint}'


class ChatModel:
    def __init__(self, settings, cancel):
        self.settings, self.cancel = settings, cancel

    def reply(self, messages, schemas):
        settings = self.settings
        url = settings['base_url'].rstrip('/') + '/chat/completions'
        if not url.startswith('https://') and not url.startswith(('http://127.0.0.1:', 'http://localhost:')):
            raise ValueError('远程 API 必须使用 HTTPS')
        if not settings.get('api_key', '').strip():
            raise ValueError('尚未配置 API Key，请在模型设置中填写')
        payload = request_payload(settings, messages, schemas)
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
                inbox.put((False, api_error(exc)))
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
