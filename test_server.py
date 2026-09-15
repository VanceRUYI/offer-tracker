import csv
import io
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from server import make_server
from store import Store


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'db.sqlite3')
        self.server = make_server(self.store, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        con = HTTPConnection('127.0.0.1', self.server.server_port)
        h = {'Content-Type': 'application/json', 'X-Workbench': '1'}
        h.update(headers or {})
        try:
            try:
                con.request(method, path, json.dumps(body, ensure_ascii=False).encode() if body is not None else None, h)
            except BrokenPipeError:
                self.fail('Server closed the connection before accepting the valid backup')
            response = con.getresponse()
            return response.status, response.read()
        finally:
            con.close()

    def test_full_application_flow_and_csv_formula_escaping(self):
        status, body = self.request('POST', '/api/applications', {'company': '=1+1', 'role': '算法岗', 'company_type':'央企', 'industry':'制造业'})
        self.assertEqual(status, 201)
        app = json.loads(body)
        status, _ = self.request('POST', '/api/applications/' + app['id'] + '/events', {'status': '一面', 'note': '收到通知'})
        self.assertEqual(status, 200)
        status, body = self.request('GET', '/api/export.csv')
        self.assertEqual(status, 200)
        rows = list(csv.reader(io.StringIO(body.decode('utf-8-sig'))))
        self.assertEqual(rows[1][0], "'=1+1")
        self.assertEqual(rows[0][-2:], ['企业性质','所属行业'])
        self.assertEqual(rows[1][-2:], ['央企','制造业'])
        self.assertEqual(self.request('DELETE', '/api/applications/' + app['id'])[0], 200)
        self.assertEqual(json.loads(self.request('GET', '/api/applications')[1]), [])

    def test_repeat_requires_confirmation_and_exports_batch(self):
        data = {'company':'Acme', 'role':'算法', 'batch':'提前批'}
        first = json.loads(self.request('POST', '/api/applications', data)[1])
        status, body = self.request('POST', '/api/applications', {**data, 'company':'ACME'})
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)['duplicates'][0]['id'], first['id'])
        status, body = self.request('POST', '/api/applications', {**data, 'batch':'正式批', 'allow_repeat':True})
        self.assertEqual(status, 201)
        self.assertNotEqual(json.loads(body)['id'], first['id'])
        exported = json.loads(self.request('GET', '/api/export.json')[1])
        self.assertEqual(exported['version'], 2)
        self.assertEqual(len(exported['applications']), 2)
        rows = list(csv.reader(io.StringIO(self.request('GET', '/api/export.csv')[1].decode('utf-8-sig'))))
        self.assertEqual(rows[0][2], '批次')
        self.assertEqual(rows[1][2], '正式批')

    def test_personalization_roundtrip_and_validation(self):
        status, body = self.request('GET', '/api/personalization')
        self.assertEqual(status, 200)
        defaults = json.loads(body)
        self.assertEqual(defaults['values'], defaults['defaults'])
        status, body = self.request('PATCH', '/api/personalization', {'icon':'sun', 'title':'保持好奇'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['title'], '保持好奇')
        self.assertEqual(self.request('PATCH', '/api/personalization', {'icon':'invalid'})[0], 400)
        self.assertEqual(self.request('PATCH', '/api/personalization', {'icon':'star'}, {'Origin':'https://foreign.example'})[0], 403)

    def test_blocks_cross_origin_and_private_files(self):
        self.assertEqual(self.request('POST', '/api/applications', {}, {'Origin': 'https://foreign.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/applications', {}, {'X-Workbench': ''})[0], 403)
        self.assertEqual(self.request('GET', '/api/applications', headers={'Host': 'foreign.example'})[0], 403)
        for path in ('/data/workbench.sqlite3', '/../store.py', '/server.py'):
            self.assertEqual(self.request('GET', path)[0], 404)

    def test_frontend_control_modules_are_served_as_javascript(self):
        for path, export in (('/selects.mjs', b'export function enhanceSelects'),
                             ('/dates.mjs', b'export function enhanceDates')):
            with self.subTest(path=path):
                con = HTTPConnection('127.0.0.1', self.server.server_port)
                try:
                    con.request('GET', path)
                    response = con.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertIn('javascript', response.getheader('Content-Type'))
                    self.assertIn(export, response.read())
                finally:
                    con.close()

    def test_bad_request_and_missing_record_are_reported(self):
        self.assertEqual(self.request('POST', '/api/applications', {'company': ''})[0], 400)
        self.assertEqual(self.request('PATCH', '/api/applications/missing', {'note': 'abc'})[0], 404)
        status, body = self.request('GET', '/api/health')
        self.assertEqual(json.loads(body)['app'], 'autumn-workbench')

    def test_large_export_can_be_restored_through_http(self):
        for i in range(90):
            self.store.create({'company': '公司' + str(i), 'role': '算法岗', 'note': '面' * 20000})
        backup = self.store.export()
        self.assertGreater(len(json.dumps(backup, ensure_ascii=False).encode()), 5 * 1024 * 1024)
        original = self.server.store
        restored = Store(Path(self.temp.name) / 'restored.sqlite3')
        self.server.store = restored
        try:
            status, body = self.request('POST', '/api/import', backup)
            self.assertEqual(status, 200, body)
            self.assertEqual(json.loads(body), {'imported': 90, 'skipped': 0})
            self.assertEqual(len(restored.list()), 90)
            self.assertEqual(restored.get(backup['applications'][0]['id'])['note'], '面' * 20000)
        finally:
            self.server.store = original

    def test_recognition_previews_without_creating_a_record(self):
        status, body = self.request('POST', '/api/recognize', {'text':'笔试邀请\n公司：示例科技\n企业性质：外商独资\n所属行业：互联网\n岗位：算法工程师\n笔试时间：2026-09-18 14:30'})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['fields']['company'], '示例科技')
        self.assertEqual(result['fields']['due_at'], '2026-09-18T14:30')
        self.assertEqual(result['fields']['company_type'], '外企')
        self.assertEqual(result['fields']['industry'], '互联网')
        self.assertEqual(self.store.list(), [])
        self.assertEqual(self.request('POST', '/api/recognize', {'url':'http://127.0.0.1:8765/'})[0], 400)


if __name__ == '__main__':
    unittest.main()
