import io
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from agent.model import ChatModel, request_payload
from agent.loop import run
from pathlib import Path
import tempfile


class ModelTests(unittest.TestCase):
    def test_deepseek_tool_roundtrip_uses_documented_parameters(self):
        requests = []
        def provider(req, timeout):
            data = json.loads(req.data)
            requests.append(data)
            self.assertEqual(req.full_url, 'https://api.deepseek.com/chat/completions')
            self.assertEqual(data['thinking'], {'type': 'disabled'})
            self.assertEqual(data['max_tokens'], 2048)
            self.assertNotIn('max_completion_tokens', data)
            message = {'role': 'assistant', 'content': '已读取'} if len(requests) > 1 else {
                'role': 'assistant', 'content': None, 'tool_calls': [{
                    'id': 'deepseek-call-1', 'type': 'function',
                    'function': {'name': 'read', 'arguments': '{"path":"example.py"}'}}]}
            return io.BytesIO(json.dumps({'choices': [{'message': message}]}).encode())
        with tempfile.TemporaryDirectory() as root, patch('agent.model.urllib.request.urlopen', side_effect=provider):
            Path(root, 'example.py').write_text('print(42)\n')
            run('读文件', root, {'mode': 'live', 'base_url': 'https://api.deepseek.com',
                'model': 'deepseek-flash', 'api_key': 'fixture-only', 'mcp_enabled': False},
                lambda *args: None, threading.Event(), lambda _: False, Path(root))
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1]['messages'][-1]['tool_call_id'], 'deepseek-call-1')
        self.assertIn('print(42)', requests[1]['messages'][-1]['content'])

    def test_openai_keeps_own_parameters(self):
        data = request_payload({'model': 'fixture', 'base_url': 'https://api.openai.com/v1'}, [], [])
        self.assertEqual(data['max_completion_tokens'], 2048)
        self.assertNotIn('thinking', data)
        self.assertNotIn('max_tokens', data)

    def test_deepseek_v1_and_lookalike_host(self):
        data = request_payload({'model': 'fixture', 'base_url': 'https://api.deepseek.com/v1/'}, [], [])
        self.assertIn('max_tokens', data)
        data = request_payload({'model': 'fixture', 'base_url': 'https://api.deepseek.com.example.org'}, [], [])
        self.assertNotIn('thinking', data)

    def test_credits_and_frequency_have_distinct_errors_without_secrets(self):
        settings = {'base_url': 'https://api.deepseek.com', 'model': 'fixture', 'api_key': 'fixture-secret'}
        cases = [(429, 'insufficient_quota', '额度不足'), (429, 'rate_limit_exceeded', '请求受限'),
                 (402, 'insufficient_balance', '额度不足'), (401, 'invalid_api_key', 'Key 无效')]
        for status, code, expected in cases:
            with self.subTest(status=status, code=code):
                exc = HTTPError('https://api.deepseek.com/chat/completions', status, 'error', {},
                    io.BytesIO(json.dumps({'error': {'code': code, 'message': 'fixture-secret'}}).encode()))
                with patch('agent.model.urllib.request.urlopen', side_effect=exc):
                    with self.assertRaises(RuntimeError) as cm:
                        ChatModel(settings, threading.Event()).reply([], [])
                self.assertIn(expected, str(cm.exception))
                self.assertNotIn('fixture-secret', str(cm.exception))

    def test_missing_key_does_not_make_request(self):
        with patch('agent.model.urllib.request.urlopen') as request:
            with self.assertRaisesRegex(ValueError, '尚未配置'):
                ChatModel({'base_url': 'https://api.deepseek.com', 'api_key': ''}, threading.Event()).reply([], [])
        request.assert_not_called()
