import io
import json
import socket
import ssl
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from agent.model import ChatModel, request_payload, open_model_request
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
        with tempfile.TemporaryDirectory() as root, patch('agent.model.open_model_request', side_effect=provider):
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
                with patch('agent.model.open_model_request', side_effect=exc):
                    with self.assertRaises(RuntimeError) as cm:
                        ChatModel(settings, threading.Event()).reply([], [])
                self.assertIn(expected, str(cm.exception))
                self.assertNotIn('fixture-secret', str(cm.exception))

    def test_missing_key_does_not_make_request(self):
        with patch('agent.model.open_model_request') as request:
            with self.assertRaisesRegex(ValueError, '尚未配置'):
                ChatModel({'base_url': 'https://api.deepseek.com', 'api_key': ''}, threading.Event()).reply([], [])
        request.assert_not_called()

    def test_network_errors_are_classified_without_echoing_sensitive_reasons(self):
        settings = {'base_url': 'https://api.deepseek.com', 'model': 'fixture', 'api_key': 'fixture-secret'}
        cases = [(socket.gaierror(-2, 'fixture-secret'), 'DNS'),
                 (ConnectionRefusedError(61, 'fixture-secret'), '连接被拒绝'),
                 (ssl.SSLCertVerificationError(1, 'fixture-secret'), '证书验证失败'),
                 (TimeoutError('fixture-secret'), '超时'),
                 (ConnectionResetError('fixture-secret'), '重置'),
                 (OSError('fixture-secret'), '无法连接')]
        for reason, expected in cases:
            with self.subTest(expected=expected), patch('agent.model.open_model_request', side_effect=URLError(reason)) as request:
                with self.assertRaises(RuntimeError) as cm:
                    ChatModel(settings, threading.Event()).reply([], [])
                self.assertIn(expected, str(cm.exception))
                self.assertNotIn('fixture-secret', str(cm.exception))
                self.assertEqual(request.call_count, 1)  # No duplicate paid requests.

    def test_proxy_configuration_is_refreshed_for_each_request(self):
        with patch('agent.model.urllib.request.build_opener') as build:
            first, second = unittest.mock.MagicMock(), unittest.mock.MagicMock()
            build.side_effect = [first, second]
            open_model_request('https://example.test/one', 3)
            open_model_request('https://example.test/two', 5)
            self.assertEqual(build.call_count, 2)
            first.open.assert_called_once_with('https://example.test/one', timeout=3)
            second.open.assert_called_once_with('https://example.test/two', timeout=5)

    def test_cancel_stops_waiting_on_a_pending_network_request(self):
        cancel = threading.Event()
        release = threading.Event()
        entered = threading.Event()
        outcome = []
        def pending(*args, **kwargs):
            entered.set()
            release.wait(2)
            raise URLError(TimeoutError())
        def request():
            try:
                ChatModel({'base_url':'https://api.deepseek.com', 'model':'fixture', 'api_key':'fixture'}, cancel).reply([], [])
            except RuntimeError as exc:
                outcome.append(str(exc))
        with patch('agent.model.open_model_request', side_effect=pending):
            worker = threading.Thread(target=request)
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                cancel.set()
                worker.join(1)
                self.assertFalse(worker.is_alive())
                self.assertIn('已中断', outcome[0])
            finally:
                release.set()
                worker.join(2)
