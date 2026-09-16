#!/usr/bin/env python3
"""Loopback-only HTTP interface for the local autumn workbench."""
import argparse
import csv
import io
import json
import sqlite3
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen
from store import Store, ValidationError, DuplicateApplication, PERSONALIZATION_DEFAULTS, PERSONALIZATION_ICONS
from recognition import recognize

ROOT = Path(__file__).resolve().parent
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/model.mjs': ('model.mjs', 'text/javascript; charset=utf-8'),
          '/dates.mjs': ('dates.mjs', 'text/javascript; charset=utf-8'),
          '/selects.mjs': ('selects.mjs', 'text/javascript; charset=utf-8'),
          '/favicon.svg': ('favicon.svg', 'image/svg+xml')}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, code, data, content_type='application/json; charset=utf-8', filename=None):
        payload = json.dumps(data, ensure_ascii=False).encode() if not isinstance(data, bytes) else data
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(payload)

    def dispatch(self):
        port = self.server.server_port
        hosts = {'127.0.0.1:' + str(port), 'localhost:' + str(port)}
        host = self.headers.get('Host', '')
        if host not in hosts:
            return self.reply(403, {'error': '仅支持从本机工作台地址访问'})
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + host:
            return self.reply(403, {'error': '请求来源不正确，请在工作台页面操作'})
        path = urlsplit(self.path).path
        store = self.server.store
        if self.command == 'GET':
            if path == '/api/health':
                return self.reply(200, {'app': 'autumn-workbench', 'version': 1})
            if path == '/api/personalization':
                return self.reply(200, {'values': store.personalization(), 'defaults': PERSONALIZATION_DEFAULTS, 'icons': PERSONALIZATION_ICONS})
            if path == '/api/applications':
                return self.reply(200, store.list())
            if path == '/api/export.json':
                return self.reply(200, store.export(), filename='autumn-workbench-backup.json')
            if path == '/api/export.csv':
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(['公司', '岗位', '批次', '岗位编号', '当前阶段', '优先级', '投递日期', '城市', '渠道', '岗位链接', '简历版本', '下一步', '安排时间', '备注', '企业性质', '所属行业'])
                for app in store.list():
                    values = [app[k] for k in ('company','role','batch','job_code','status','priority','applied_on','city','channel','url','resume','next_action','due_at','note','company_type','industry')]
                    writer.writerow(["'" + s if s.lstrip().startswith(('=', '+', '-', '@')) or s.startswith(('\t', '\r', '\n')) else s for s in values])
                return self.reply(200, ('\ufeff' + output.getvalue()).encode(), 'text/csv; charset=utf-8', 'autumn-applications.csv')
            if path in ASSETS:
                asset, content_type = ASSETS[path]
                return self.reply(200, (ROOT / 'web' / asset).read_bytes(), content_type)
            return self.reply(404, {'error': '没有找到这个页面'})

        if self.headers.get('X-Workbench') != '1':
            return self.reply(403, {'error': '请在工作台页面操作'})
        if self.command not in ('POST', 'PATCH', 'DELETE'):
            return self.reply(405, {'error': '不支持此操作'})
        if self.command != 'DELETE':
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415, {'error': '请求必须为 JSON 格式'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                raise ValidationError('请求长度不正确')
            if size < 0:
                raise ValidationError('请求长度不正确')
            # A complete export must remain restorable as the local journal grows.
            # Imports are explicitly chosen files behind the same-origin boundary.
            if path != '/api/import' and size > 1024 * 1024:
                return self.reply(413, {'error': '单次编辑内容过大，请缩短后再保存'})
            try:
                data = json.loads(self.rfile.read(size))
            except (ValueError, UnicodeDecodeError):
                raise ValidationError('内容不是有效的 JSON')
        else:
            data = {}
        if self.command == 'PATCH' and path == '/api/personalization':
            return self.reply(200, store.set_personalization(data))
        if self.command == 'POST' and path == '/api/applications':
            return self.reply(201, store.create(data))
        if self.command == 'POST' and path == '/api/recognize':
            return self.reply(200, recognize(data))
        if self.command == 'POST' and path == '/api/import':
            return self.reply(200, store.import_data(data))
        parts = path.strip('/').split('/')
        if len(parts) in (3, 4) and parts[:2] == ['api', 'applications']:
            app_id = parts[2]
            if self.command == 'PATCH' and len(parts) == 3:
                return self.reply(200, store.update(app_id, data))
            if self.command == 'DELETE' and len(parts) == 3:
                store.delete(app_id)
                return self.reply(200, {'deleted': True})
            if self.command == 'POST' and len(parts) == 4:
                if parts[3] == 'events':
                    return self.reply(200, store.add_event(app_id, data))
                if parts[3] == 'complete':
                    return self.reply(200, store.complete(app_id))
        return self.reply(404, {'error': '没有找到这个操作'})

    def handle_request(self):
        try:
            self.dispatch()
        except DuplicateApplication as error:
            self.reply(409, {'error': str(error), 'duplicates': error.matches})
        except ValidationError as exc:
            self.reply(400, {'error': str(exc)})
        except KeyError as exc:
            self.reply(404, {'error': exc.args[0]})
        except (sqlite3.Error, OSError) as exc:
            print('Storage/request error:', repr(exc), file=sys.stderr)
            self.reply(500, {'error': '暂时无法读取或保存数据，请检查磁盘空间并重试；输入内容仍保留在页面中'})
        except Exception as exc:
            print('Unexpected request error:', repr(exc), file=sys.stderr)
            self.reply(500, {'error': '操作未完成，请重试；输入内容仍保留在页面中'})

    do_GET = handle_request
    do_POST = handle_request
    do_PATCH = handle_request
    do_DELETE = handle_request
    do_OPTIONS = handle_request


def make_server(store, port=8765):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.store = store
    return server


def main():
    parser = argparse.ArgumentParser(description='秋招工作台 · 本地版')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'workbench.sqlite3')
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    url = 'http://127.0.0.1:' + str(args.port)
    if args.open:
        try:
            with urlopen(url + '/api/health', timeout=1) as response:
                if json.load(response).get('app') == 'autumn-workbench':
                    webbrowser.open(url)
                    print('工作台已经在运行，已打开页面。')
                    return
        except (URLError, ValueError, TimeoutError):
            pass
    store = Store(args.db)
    store.backup('daily')
    try:
        server = make_server(store, args.port)
    except OSError:
        print('端口已被占用。请关闭之前的工作台，或使用 --port 8766 启动。', file=sys.stderr)
        sys.exit(1)
    print('秋招工作台已启动：' + url, flush=True)
    print('数据文件：' + str(store.path), flush=True)
    print('保留这个窗口即可持续使用。按 Control+C 停止。', flush=True)
    if args.open:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
