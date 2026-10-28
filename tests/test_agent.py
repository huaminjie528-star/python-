import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from agent.loop import run
from agent.mcp import connect
from server.app import State, make_server
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent.parent


class AgentTests(unittest.TestCase):
    def test_live_adapter_tool_call_feedback(self):
        requests=[]
        class FakeProvider(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append(payload)
                message={'role':'assistant','content':'已阅读文件'} if len(requests)>1 else {'role':'assistant','content':None,'tool_calls':[{'id':'provider-1','type':'function','function':{'name':'read','arguments':'{"path":"stats.py"}'}}]}
                raw=json.dumps({'choices':[{'message':message}]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(raw)
        provider=ThreadingHTTPServer(('127.0.0.1',0),FakeProvider)
        threading.Thread(target=provider.serve_forever,daemon=True).start()
        events=[]
        try:
            run('读取文件',ROOT/'examples/demo_workspace',{'mode':'live','base_url':f'http://127.0.0.1:{provider.server_port}/v1','model':'fixture','api_key':'fixture','mcp_enabled':False},lambda t,d:events.append((t,d)),threading.Event(),lambda _:True,ROOT)
            self.assertEqual(len(requests),2)
            self.assertEqual(requests[1]['messages'][-1]['tool_call_id'],'provider-1')
            self.assertIn('def mean',requests[1]['messages'][-1]['content'])
            self.assertEqual(len(requests[0]['tools']),4)
        finally:
            provider.shutdown()
            provider.server_close()

    def test_real_mcp_process(self):
        clients, schemas = connect(ROOT / 'mcp.json', ROOT, threading.Event())
        try:
            self.assertEqual(schemas[0]['function']['name'],'mcp__course__describe_project')
            r = clients['course'].request('tools/call',{'name':'describe_project','arguments':{}})
            self.assertIn('验收', r['content'][0]['text'])
        finally:
            for c in clients.values(): c.close()

    def test_failure_recovery_trace(self):
        events = []
        with tempfile.TemporaryDirectory() as root:
            run('失败恢复',root,{'mode':'demo','mcp_enabled':True},lambda t,d:events.append((t,d)),threading.Event(),lambda _:True,ROOT)
            self.assertEqual((Path(root)/'recovery.txt').read_text(),'alpha = 1\nbeta = 2\n')
        failures=[d for t,d in events if t=='tool_result' and not d['ok']]
        self.assertEqual(len(failures),1)
        self.assertIn('2 次',failures[0]['error'])

    def test_bug_fix_test_before_after(self):
        events=[]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'workspace'
            shutil.copytree(ROOT/'examples/demo_workspace',root)
            run('修复 mean',root,{'mode':'demo'},lambda t,d:events.append((t,d)),threading.Event(),lambda _:True,ROOT)
        codes=[d['result']['exit_code'] for t,d in events if t=='tool_result' and d['name']=='bash']
        self.assertEqual(codes,[1,0])

    def test_repetition_guard(self):
        class Repeating:
            def reply(self,*args):
                return {'role':'assistant','tool_calls':[{'id':'id','function':{'name':'read','arguments':'{"path":"missing"}'}}]}
        with tempfile.TemporaryDirectory() as temp, patch('agent.loop.ChatModel',return_value=Repeating()):
            with self.assertRaisesRegex(RuntimeError,'重复'):
                run('重复',temp,{'mode':'live','mcp_enabled':False},lambda *a:None,threading.Event(),lambda _:True,ROOT)

    def test_http_auth_settings_no_secret_and_sse(self):
        with tempfile.TemporaryDirectory() as temp:
            state=State(ROOT,ROOT/'examples/demo_workspace',temp)
            server=make_server(state)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(base+'/api/state')
                req=urllib.request.Request(base+'/api/settings',data=json.dumps({'api_key':'secret-test-value'}).encode(),headers={'X-Agent-Token':state.token})
                urllib.request.urlopen(req).close()
                self.assertNotIn('secret-test-value',(Path(temp)/'settings.json').read_text())
                response=urllib.request.urlopen(base+'/api/state?token='+state.token).read().decode()
                self.assertNotIn('secret-test-value',response)
                jid=state.start('MCP')
                text=urllib.request.urlopen(base+'/api/events?job='+jid+'&token='+state.token).read().decode()
                self.assertIn('mcp__course__describe_project',text)
                self.assertIn('"type": "done"',text)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__': unittest.main()
