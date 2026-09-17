import asyncio
import importlib.util
import json
import io
import gzip
import zlib
import os
import time
from pathlib import Path
import unittest
from unittest.mock import patch
from recognition import validate_public_url, RecognitionError, fetch_public_page


class PublicResourceTests(unittest.TestCase):
    def test_browser_session_preserves_anonymous_cookie_on_wire(self):
        class Socket:
            wire=b''
            def sendall(self,value): self.wire+=value
            def makefile(self,*args): return io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nSet-Cookie: visitor=next; Path=/\r\n\r\n{}')
            def settimeout(self,value): pass
            def close(self): pass
        sock=Socket()
        with patch('recognition.socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',80))]), patch('recognition.socket.create_connection',return_value=sock):
            result=fetch_public_page('http://example.com/jobs',resource=True,browser_session=True,headers={'cookie':'visitor=temporary'})
        self.assertIn(b'cookie: visitor=temporary',sock.wire)
        self.assertEqual(result['headers']['set-cookie'],'visitor=next; Path=/')

    def compressed_resource(self, body, encoding='gzip', resource=True):
        raw = gzip.compress(body) if encoding == 'gzip' else zlib.compress(body)
        class Socket:
            def sendall(self, value): pass
            def makefile(self, *args):
                return io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(raw)).encode()+
                    b'\r\nContent-Type: text/html\r\nContent-Encoding: '+encoding.encode()+b'\r\n\r\n'+raw)
            def settimeout(self, value): pass
            def close(self): pass
        with patch('recognition.socket.getaddrinfo', return_value=[(2,1,6,'',('8.8.8.8',80))]), patch('recognition.socket.create_connection', return_value=Socket()):
            return fetch_public_page('http://example.com/main.js', resource=resource)

    def test_compressed_seven_mb_script_can_load(self):
        body = b'/* bundle */' + b' ' * (7 * 1024 * 1024)
        self.assertEqual(self.compressed_resource(body)['body'], body)

    def test_deflate_html_is_decoded(self):
        self.assertEqual(self.compressed_resource(b'<h1>Job</h1>', 'deflate', False)[0], '<h1>Job</h1>')

    def test_compression_does_not_bypass_decoded_size_budget(self):
        with self.assertRaisesRegex(RecognitionError, '过大'):
            self.compressed_resource(b' ' * (9 * 1024 * 1024))
        with self.assertRaisesRegex(RecognitionError, '过大'):
            self.compressed_resource(b' ' * (3 * 1024 * 1024), resource=False)

    def test_browser_json_accept_replaces_html_default_on_wire(self):
        class Socket:
            wire=b''
            def sendall(self,value):self.wire+=value
            def makefile(self,*args):return io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}')
            def settimeout(self,value):pass
            def close(self):pass
        sock=Socket()
        with patch('recognition.socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',80))]),patch('recognition.socket.create_connection',return_value=sock):
            fetch_public_page('http://example.com/jobs',resource=True,headers={'accept':'application/json'})
        accepts=[line for line in sock.wire.decode().split('\r\n') if line.lower().startswith('accept:')]
        self.assertEqual(accepts,['accept: application/json'])

    def test_browser_transport_rejects_private_targets_and_mutating_methods(self):
        for url in ('http://127.0.0.1/secret','http://169.254.169.254/','file:///etc/passwd'):
            with self.assertRaises(RecognitionError):fetch_public_page(url,resource=True)
        for method in ('DELETE','PUT','PATCH'):
            with self.assertRaises(RecognitionError):fetch_public_page('https://example.com',resource=True,method=method)


@unittest.skipUnless(importlib.util.find_spec('playwright') and (Path(__file__).parent/'.browser-runtime').exists(), 'optional browser runtime not installed')
class BrowserRuntimeTests(unittest.TestCase):
    def test_generic_name_job_response_is_available_before_page_finishes(self):
        from browser_reader import render_page
        from rendered_extraction import extract_rendered_page
        html = '''<html><title>测试企业招聘</title><body>加载中<script>
        fetch('/api/detail', {method:'POST', body:'{}'}).then(r=>r.json()).then(j=>{
          setTimeout(()=>document.body.textContent=j.content.name,1500);
        });</script></body></html>'''
        job = {'content': {'id': 123, 'name': '应用算法工程师', 'description': '开发算法',
                           'workLocations': ['北京', '杭州'], 'batchName': '2027 校招'}}
        def resource(url, **kwargs):
            return {'body': json.dumps(job).encode(), 'status': 200,
                    'headers': {'content-type': 'application/json'}, 'url': url}
        with patch.dict(os.environ, {'PLAYWRIGHT_BROWSERS_PATH': str(Path(__file__).parent/'.browser-runtime')}), patch('recognition.fetch_public_page', side_effect=resource):
            page = asyncio.run(render_page('https://fixture.example/position/123', initial_document=html))
        fields = extract_rendered_page(page)['fields']
        self.assertEqual(fields.get('role'), '应用算法工程师')
        self.assertEqual(fields.get('city'), '北京 / 杭州')
        self.assertNotIn('应用算法工程师', page['text'])

    def test_initial_response_cookies_are_used_only_in_fresh_browser_session(self):
        from browser_reader import render_page
        from rendered_extraction import extract_rendered_page
        html='<html><title>测试企业招聘</title><body><script>fetch("/api/role").then(r=>r.json()).then(j=>document.body.textContent=j.positionName)</script></body></html>'
        def resource(url,**kwargs):
            if 'visitor=temporary' not in kwargs.get('headers',{}).get('cookie',''):
                return {'body':b'{}','headers':{},'status':403,'url':url}
            return {'body':json.dumps({'positionId':123,'positionName':'算法工程师','duty':'研发'}).encode(),'headers':{},'status':200,'url':url}
        with patch.dict(os.environ,{'PLAYWRIGHT_BROWSERS_PATH':str(Path(__file__).parent/'.browser-runtime')}), patch('recognition.fetch_public_page',side_effect=resource):
            page=asyncio.run(render_page('https://fixture.example/position/123',initial_document={'html':html,'set_cookie':'visitor=temporary; Path=/; Secure'}))
        self.assertEqual(extract_rendered_page(page)['fields'].get('role'),'算法工程师')

    def test_failed_main_script_does_not_wait_for_full_page_deadline(self):
        from browser_reader import render_page
        html='<html><head><title>测试企业招聘</title></head><body><script src="/main.js"></script></body></html>'
        start=time.monotonic()
        with patch.dict(os.environ,{'PLAYWRIGHT_BROWSERS_PATH':str(Path(__file__).parent/'.browser-runtime')}), patch('recognition.fetch_public_page',side_effect=RecognitionError('脚本加载失败')):
            snapshot=asyncio.run(render_page('https://fixture.example/position/123',initial_document=html))
        self.assertLess(time.monotonic()-start,5)
        self.assertTrue(snapshot['diagnostics']['failures'])

    def test_reuses_initial_html_and_does_not_wait_for_decorative_styles(self):
        from browser_reader import render_page
        from rendered_extraction import extract_rendered_page
        job={'positionId':123,'positionName':'测试算法工程师','workplace':'杭州','duty':'岗位职责：'+('开发算法。'*30)}
        html='''<html><head><title>测试企业校园招聘</title><link rel="stylesheet" href="/theme.css"></head>
        <body><div id="app">加载中</div><script>fetch('/api/role').then(r=>r.json()).then(j=>{
        document.querySelector('#app').innerHTML='<h1>'+j.positionName+'</h1><p>'+j.duty+'</p>';
        setTimeout(()=>document.body.append('UNRELATED_LATE_UI'),2200);
        });</script></body></html>'''
        requests=[]
        def resource(url, **kwargs):
            requests.append(url)
            return {'body':json.dumps(job).encode(),'headers':{'content-type':'application/json'},'status':200,'url':url}
        with patch.dict(os.environ,{'PLAYWRIGHT_BROWSERS_PATH':str(Path(__file__).parent/'.browser-runtime')}),patch('recognition.fetch_public_page',side_effect=resource):
            snapshot=asyncio.run(render_page('https://fixture.example/position/123', initial_document=html))
        self.assertEqual(requests, ['https://fixture.example/api/role'])
        self.assertNotIn('UNRELATED_LATE_UI',snapshot['text'])
        self.assertEqual(extract_rendered_page(snapshot)['fields']['role'],'测试算法工程师')

    def test_delayed_public_content_is_rendered_without_company_specific_adapter(self):
        from browser_reader import render_page
        from rendered_extraction import extract_rendered_page
        job={'positionId':123,'positionName':'测试算法工程师','workplace':'杭州','duty':'岗位职责：'+('开发算法。'*30)}
        html='''<html><head><title>测试企业校园招聘</title></head><body><div id="app">加载中</div>
        <script>setTimeout(async()=>{const r=await fetch('/api/role');const j=await r.json();
        document.querySelector('#app').innerHTML='<h1>'+j.positionName+'</h1><p>'+j.duty+'</p>';},150);</script></body></html>'''
        def resource(url,**kwargs):
            validate_public_url(url)
            if url=='https://fixture.example/api/role':body=json.dumps(job).encode();kind='application/json'
            elif url=='https://fixture.example/position/123':body=html.encode();kind='text/html; charset=utf-8'
            else:raise RecognitionError('Unexpected fixture URL')
            return {'body':body,'headers':{'content-type':kind},'status':200,'url':url}
        with patch.dict(os.environ,{'PLAYWRIGHT_BROWSERS_PATH':str(Path(__file__).parent/'.browser-runtime')}),patch('recognition.fetch_public_page',side_effect=resource):
            snapshot=asyncio.run(render_page('https://fixture.example/position/123'))
        result=extract_rendered_page(snapshot)
        self.assertIn('测试算法工程师',snapshot['text'])
        self.assertEqual(result['fields']['role'],'测试算法工程师')
        self.assertEqual(result['fields']['company'],'测试企业')
        self.assertEqual(result['fields']['city'],'杭州')
