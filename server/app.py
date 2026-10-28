"""Local SSE backend. Independent of the desktop webview."""
import argparse
import json
import os
from pathlib import Path
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from agent.loop import run
from agent.tools import Tools


class State:
    def __init__(self, resource_root, workspace, data_dir):
        self.resource_root, self.workspace = Path(resource_root), Path(workspace).resolve()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.token = secrets.token_urlsafe(32)
        self.settings = {'mode': 'demo', 'base_url': 'https://api.openai.com/v1', 'model': '',
                         'api_key': os.environ.get('AGENT_API_KEY', ''), 'mcp_enabled': True, 'max_steps': 20}
        config = self.data_dir / 'settings.json'
        if config.exists():
            self.settings.update(json.loads(config.read_text()))
        self.jobs = {}
        self.lock = threading.RLock()
        self.history = []

    def save_settings(self, values):
        allowed = {'mode', 'base_url', 'model', 'api_key', 'mcp_enabled', 'mcp_config', 'max_steps'}
        self.settings.update({k: v for k, v in values.items() if k in allowed})
        safe = {k: v for k, v in self.settings.items() if k != 'api_key'}
        (self.data_dir / 'settings.json').write_text(json.dumps(safe, ensure_ascii=False, indent=2))

    def start(self, task):
        with self.lock:
            if any(not j['done'] for j in self.jobs.values()):
                raise ValueError('任务运行中，请先中断或等待完成')
            # Bound in-memory event history.
            if len(self.jobs) >= 20:
                self.jobs.pop(next(iter(self.jobs)))
            jid = uuid.uuid4().hex
            job = {'events': [], 'cancel': threading.Event(), 'done': False, 'pending': {}, 'condition': threading.Condition()}
            self.jobs[jid] = job
            settings = dict(self.settings)
            workspace = self.workspace
            history = list(self.history) if settings['mode'] == 'live' else []
        trace_path = self.data_dir / f'{jid}.jsonl'
        def emit(kind, data):
            # Keys are never placed in events or the history.
            event = {'type': kind, 'time': time.strftime('%Y-%m-%dT%H:%M:%S'), **data}
            with job['condition']:
                job['events'].append(event)
                with trace_path.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(event, ensure_ascii=False) + '\n')
                job['condition'].notify_all()
        job['emit'] = emit
        deadline = time.monotonic() + 240
        def approve(proposal):
            aid = uuid.uuid4().hex
            decision = {'event': threading.Event(), 'allow': False}
            job['pending'][aid] = decision
            emit('approval', {'approval_id': aid, **proposal})
            while not decision['event'].wait(0.1):
                if job['cancel'].is_set() or time.monotonic() > deadline:
                    job['cancel'].set()
                    break
            job['pending'].pop(aid, None)
            allowed = decision['allow'] and not job['cancel'].is_set()
            emit('approval_resolved', {'approval_id': aid, 'allow': allowed})
            return allowed
        def worker():
            emit('task', {'task': task, 'workspace': str(workspace), 'mode': settings['mode']})
            try:
                result = run(task, workspace, settings, emit, job['cancel'], approve, self.resource_root, history)
                if settings['mode'] == 'live':
                    self.history = result
                emit('done', {'text': '已中断' if job['cancel'].is_set() else '本轮结束'})
            except Exception as exc:
                emit('error', {'text': str(exc)})
                emit('done', {'text': '已中断' if job['cancel'].is_set() else '任务停止，请查看错误'})
            finally:
                with job['condition']:
                    job['done'] = True
                    job['condition'].notify_all()
        def watchdog():
            while not job['done']:
                if time.monotonic() > deadline:
                    job['cancel'].set()
                    return
                time.sleep(0.1)
        threading.Thread(target=worker, daemon=True).start()
        threading.Thread(target=watchdog, daemon=True).start()
        return jid


def make_server(state, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, data, code=200):
            raw = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            q = parse_qs(urlsplit(self.path).query)
            return secrets.compare_digest(self.headers.get('X-Agent-Token', q.get('token', [''])[0]), state.token)

        def do_GET(self):
            path = urlsplit(self.path).path
            q = parse_qs(urlsplit(self.path).query)
            if not self.authorized():
                self.send_json({'error': '缺少本地会话令牌'}, 403)
                return
            try:
                if path == '/api/state':
                    self.send_json({'workspace': str(state.workspace), 'settings': {k: v for k, v in state.settings.items() if k != 'api_key'},
                                    'has_key': bool(state.settings['api_key'])})
                elif path == '/api/tree':
                    files = []
                    for directory, dirs, names in os.walk(state.workspace, followlinks=False):
                        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in {'node_modules', '__pycache__', 'dist', 'build'})
                        for name in sorted(names):
                            if name.startswith('.'):
                                continue
                            p = Path(directory) / name
                            if p.is_symlink():
                                continue
                            files.append(str(p.relative_to(state.workspace)))
                            if len(files) >= 300:
                                break
                        if len(files) >= 300:
                            break
                    self.send_json({'files': files})
                elif path == '/api/file':
                    self.send_json(Tools(state.workspace).read(q['path'][0], int(q.get('offset', ['1'])[0]), 500))
                elif path == '/api/events':
                    job = state.jobs[q['job'][0]]
                    index = int(self.headers.get('Last-Event-ID', '-1')) + 1
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    while True:
                        with job['condition']:
                            if index >= len(job['events']) and not job['done']:
                                job['condition'].wait(1)
                            events = job['events'][index:]
                            done = job['done']
                        for event in events:
                            self.wfile.write(f'id: {index}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n'.encode())
                            index += 1
                        self.wfile.write(b': heartbeat\n\n')
                        self.wfile.flush()
                        if done and index >= len(job['events']):
                            break
                else:
                    p = state.resource_root / 'ui' / ('index.html' if path == '/' else path.lstrip('/'))
                    if p.parent != state.resource_root / 'ui' or p.suffix not in {'.html', '.css', '.js'}:
                        raise ValueError('未知资源')
                    raw = p.read_bytes()
                    if p.suffix == '.html':
                        raw = raw.replace(b'__SESSION_TOKEN__', state.token.encode())
                    self.send_response(200)
                    self.send_header('Content-Type', {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css'}[p.suffix] + '; charset=utf-8')
                    self.send_header('Content-Length', str(len(raw)))
                    self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
                    self.end_headers()
                    self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                self.send_json({'error': str(exc)}, 400)

        def do_POST(self):
            if not self.authorized():
                self.send_json({'error': '本地鉴权失败'}, 403)
                return
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 <= length <= 2_000_000:
                    raise ValueError('请求过大')
                data = json.loads(self.rfile.read(length) or b'{}')
                path = urlsplit(self.path).path
                if path == '/api/task':
                    if not data.get('task', '').strip():
                        raise ValueError('请输入任务')
                    self.send_json({'job': state.start(data['task'][:20000])})
                elif path == '/api/settings':
                    if any(not j['done'] for j in state.jobs.values()):
                        raise ValueError('运行期间不能修改配置')
                    state.save_settings(data)
                    self.send_json({'ok': True})
                elif path == '/api/approve':
                    decision = state.jobs[data['job']]['pending'][data['approval_id']]
                    decision['allow'] = data.get('allow') is True
                    decision['event'].set()
                    self.send_json({'ok': True})
                elif path == '/api/cancel':
                    state.jobs[data['job']]['cancel'].set()
                    self.send_json({'ok': True})
                elif path == '/api/save':
                    if any(not j['done'] for j in state.jobs.values()):
                        raise ValueError('请先结束任务，再手动保存文件')
                    self.send_json(Tools(state.workspace, approve=lambda _: True).write(data['path'], data['content']))
                elif path == '/api/new':
                    if any(not j['done'] for j in state.jobs.values()):
                        raise ValueError('请先结束任务')
                    state.history = []
                    self.send_json({'ok': True})
                else:
                    self.send_json({'error': '未知接口'}, 404)
            except Exception as exc:
                self.send_json({'error': str(exc)}, 400)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', default='examples/demo_workspace')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', default='.local-data')
    args = parser.parse_args()
    state = State(Path(__file__).resolve().parent.parent, args.workspace, args.data_dir)
    server = make_server(state, args.port)
    print(f'Little Cursor backend: http://127.0.0.1:{server.server_port}/?token={state.token}', flush=True)
    try:
        server.serve_forever()
    finally:
        for job in state.jobs.values():
            job['cancel'].set()
        server.server_close()


if __name__ == '__main__':
    main()
