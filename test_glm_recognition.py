import io
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import glm_recognition as glm
from recognition import recognize


class GLMTests(unittest.TestCase):
    def test_stalled_model_does_not_hold_preview_for_twenty_seconds(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                time.sleep(4)
                try:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps({'choices':[{'message':{'content':'{"role":"算法工程师"}'}}]}).encode())
                except (BrokenPipeError, ConnectionResetError): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            started = time.monotonic()
            with patch.object(glm, 'ENDPOINT', 'http://127.0.0.1:'+str(server.server_port)), \
                 self.assertRaises(glm.ModelError):
                glm.extract_fields({'text':'算法工程师'}, {'fields':{}}, 'test-key')
            self.assertLess(time.monotonic()-started, 4)
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_title_with_company_and_role_is_ready_without_waiting_for_optional_fields(self):
        html = '<title>【27届校招】交易体验运营-逆向交易 - 示例App招聘</title>'
        stages = []
        with patch('recognition.fetch_public_page', return_value=(html,'https://example.com/job/123')), \
             patch('glm_recognition.load_key', return_value='test-key'), \
             patch('glm_recognition.extract_fields', side_effect=AssertionError('basic fields already available')):
            result = recognize({'url':'https://example.com/job/123'}, progress=stages.append, use_ai=True)
        self.assertEqual(result['fields'], {'company':'示例App','role':'【27届校招】交易体验运营-逆向交易'})
        self.assertEqual(result['ai_status'], 'not_needed')
        self.assertNotIn('model_seconds', result)
        self.assertEqual([s['stage'] for s in stages], ['reading'])

    def test_first_visit_with_complete_job_data_does_not_wait_for_model(self):
        page = {'url':'https://example.com/job/123', 'title':'测试公司招聘', 'html':'', 'text':'',
                'responses':[{'url':'https://example.com/api/detail','method':'POST','data':{
                    'id':123, 'name':'算法工程师', 'description':'开发算法', 'workLocations':['上海']}}]}
        with patch('recognition.fetch_public_page',return_value=('<div id="app"></div>',page['url'])), \
             patch('browser_reader.read_rendered_page',return_value=page), \
             patch('glm_recognition.load_key',return_value='test-key'), \
             patch('glm_recognition.extract_fields',side_effect=AssertionError('complete job already received')):
            result=recognize({'url':page['url']},use_ai=True)
        self.assertEqual(result['fields']['role'],'算法工程师')
        self.assertEqual(result['fields']['city'],'上海')
        self.assertEqual(result['ai_status'],'not_needed')

    def test_learned_source_skips_browser_and_icon_download_is_deferred(self):
        page={'url':'https://example.com/job/123','title':'测试公司招聘','text':'',
              'icon_url':'https://example.com/favicon.ico', 'responses':[{'url':'https://example.com/api/123',
              'data':{'positionId':123,'positionName':'算法工程师','duty':'研发'}}]}
        with patch('job_sources.SOURCES.read', return_value=page), \
             patch('recognition.fetch_public_page', side_effect=AssertionError('should not download HTML or icon')), \
             patch('glm_recognition.load_key', return_value='test-key'), \
             patch('glm_recognition.extract_fields', side_effect=AssertionError('structured job should not wait on model')):
            result=recognize({'url':page['url']},use_ai=True)
        self.assertEqual(result['read_method'],'api')
        self.assertEqual(result['ai_status'],'not_needed')
        self.assertEqual(result['company_logo']['logo']['icon_url'],'https://example.com/favicon.ico')
        self.assertNotIn('data_url',result['company_logo']['logo'])

    def test_local_key_is_literal_and_environment_takes_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / '.env.local'
            path.write_text('# comment\nZHIPU_API_KEY="local.example"\n')
            with patch.dict('os.environ', {}, clear=True):
                self.assertEqual(glm.load_key(path), 'local.example')
            with patch.dict('os.environ', {'ZHIPU_API_KEY': 'env.example'}):
                self.assertEqual(glm.load_key(path), 'env.example')

    def test_model_fields_require_source_text_and_cannot_set_personal_progress(self):
        fields = glm.parse_fields(json.dumps({'fields': {'company': '示例公司', 'role': '算法工程师',
            'city': '不存在的城市', 'job_code': '0012', 'applied_on': '2026-09-17', 'status': '已投递'}}),
            '示例公司\n算法工程师\n职位编号 0012')
        self.assertEqual(fields, {'company': '示例公司', 'role': '算法工程师', 'job_code': '0012'})

    def test_malformed_or_empty_model_output_is_not_success(self):
        for raw in ('not json', '[]', '{}', '{"role":true}', '{"role":"杜撰岗位"}'):
            with self.assertRaises(glm.ModelError):
                glm.parse_fields(raw, '公司 岗位')

    def test_request_uses_free_model_and_excludes_private_record_fields(self):
        captured = {}
        class Opener:
            def open(self, req, timeout):
                captured.update(json.loads(req.data))
                return io.BytesIO(json.dumps({'choices': [{'message': {'content': '{"role":"算法工程师"}'}}]}).encode())
        with patch('glm_recognition.build_opener', return_value=Opener()):
            fields = glm.extract_fields({'title':'示例公司招聘', 'text':'算法工程师',
                'html':'secret-cookie', 'responses': [{'data': {'token':'secret-token'}}]},
                {'fields':{'status':'已投递','note':'私人笔记'}}, 'test-key')
        self.assertEqual(fields, {'role':'算法工程师'})
        self.assertEqual(captured['model'], 'glm-4.7-flash')
        self.assertEqual(captured['thinking'], {'type':'disabled'})
        self.assertNotIn('secret', str(captured))
        self.assertNotIn('私人笔记', str(captured))

    def test_rate_limit_has_safe_message_without_provider_body(self):
        error = HTTPError('https://open.bigmodel.cn/', 429, 'rate limit', {}, io.BytesIO(b'secret'))
        with patch('glm_recognition.build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(glm.ModelError) as caught:
                glm.extract_fields({'text':'算法工程师'}, {'fields':{}}, 'test-key')
        self.assertIn('繁忙', str(caught.exception))
        self.assertNotIn('secret', str(caught.exception))

    def test_partial_page_uses_model_when_enabled_and_emits_real_stages(self):
        html = '<title>示例公司</title><p>公司：示例公司</p>'
        page = {'url':'https://example.com/job','title':'示例公司招聘','html':html,'text':'岗位职责：参与算法研发'}
        stages = []
        with patch('glm_recognition.load_key', return_value='test-key'), \
             patch('recognition.fetch_public_page', return_value=(html,'https://example.com/job')), \
             patch('browser_reader.read_rendered_page', return_value=page), \
             patch('glm_recognition.extract_fields', return_value={'company':'示例公司','role':'算法工程师'}):
            result = recognize({'url':'https://example.com/job'}, progress=stages.append, use_ai=True)
        self.assertEqual(result['ai_status'], 'success')
        self.assertEqual(result['fields']['role'], '算法工程师')
        self.assertEqual([s['stage'] for s in stages], ['reading', 'browser', 'model'])

    def test_rate_limited_model_keeps_rule_results_and_is_not_labelled_ai_success(self):
        html = '<p>公司：示例公司</p>'
        page = {'url':'https://example.com/job','title':'示例公司招聘','html':html,'text':'岗位职责：参与算法研发'}
        with patch('glm_recognition.load_key', return_value='test-key'), \
             patch('recognition.fetch_public_page', return_value=(html,'https://example.com/job')), \
             patch('browser_reader.read_rendered_page', return_value=page), \
             patch('glm_recognition.extract_fields', side_effect=glm.ModelError('免费模型繁忙')):
            result = recognize({'url':'https://example.com/job'}, use_ai=True)
        self.assertEqual(result['ai_status'], 'fallback')
        self.assertEqual(result['fields']['company'], '示例公司')
        self.assertIn('免费模型繁忙', str(result['facts']))

    def test_dynamic_page_model_uses_loaded_text(self):
        snapshot = {'url':'https://example.com/job','title':'示例公司招聘','html':'',
                    'text':'岗位职责：需要算法工程师参与研发','headings':[], 'responses':[]}
        seen = []
        def extract(page, result, key):
            seen.append(page['text'])
            return {'role':'算法工程师'}
        with patch('glm_recognition.load_key', return_value='test-key'), \
             patch('recognition.fetch_public_page', return_value=('<div id="app"></div>',snapshot['url'])), \
             patch('browser_reader.read_rendered_page', return_value=snapshot), \
             patch('glm_recognition.extract_fields', side_effect=extract):
            result = recognize({'url':snapshot['url']}, use_ai=True)
        self.assertEqual(seen, ['岗位职责：需要算法工程师参与研发'])
        self.assertEqual(result['ai_status'], 'success')
        self.assertEqual(result['read_method'], 'browser')
        self.assertFalse(any('暂未找到' in fact['value'] for fact in result['facts']))
