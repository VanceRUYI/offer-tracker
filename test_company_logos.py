import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from company_logos import image_data, validate_logo, discover_logo, known_company, IconParser
from recognition import RecognitionError
from store import Store, ValidationError

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7XQAAAAASUVORK5CYII=')

class CompanyLogoTests(unittest.TestCase):
    def test_application_url_discovers_icon_when_page_company_matches(self):
        html = '<title>算法工程师 - 测试科技校园招聘官网</title><link rel="icon" href="/logo.png">'
        with patch('recognition.fetch_public_page', side_effect=[(html,'https://example.com/jobs/123'),(PNG,'https://example.com/logo.png')]):
            result = discover_logo('测试科技','https://example.com/jobs/123', automatic=True)
            self.assertEqual(result['source_url'], 'https://example.com/logo.png')

    def test_automatic_discovery_does_not_assign_platform_or_unrelated_logo(self):
        html = '<title>算法工程师 - 测试科技校园招聘官网</title><link rel="icon" href="/logo.png">'
        for initial, final, page in [
            ('https://tenant.feishu.cn/jobs/123','https://tenant.feishu.cn/jobs/123',html),
            ('https://example.com/jobs/123','https://tenant.mokahr.com/jobs/123',html),
            ('https://example.com/jobs/123','https://example.com/jobs/123','<title>请登录</title>'),
            ('https://example.com/jobs/123','https://example.com/jobs/123',html.replace('测试科技','另一公司')),
        ]:
            with self.subTest(initial=initial,final=final,page=page), patch('recognition.fetch_public_page', side_effect=[(page,final),(PNG,'https://example.com/logo.png')]):
                with self.assertRaises(ValueError):
                    discover_logo('测试科技',initial,automatic=True)

    def test_known_company_uses_official_site_even_with_platform_application_url(self):
        with patch('recognition.fetch_public_page', side_effect=[('<link rel="icon" href="/logo.png">','https://www.tencent.com/'),(PNG,'https://www.tencent.com/logo.png')]):
            result=discover_logo('腾讯','https://tenant.feishu.cn/jobs/123',automatic=True)
            self.assertEqual(result['website'],'https://www.tencent.com/')

    def test_exact_aliases_do_not_guess_similar_company_names(self):
        self.assertEqual(known_company(' Tencent ')['name'], '腾讯')
        self.assertIsNone(known_company('腾讯生态合作伙伴'))
        self.assertIsNone(known_company('远山科技'))

    def test_validated_images_and_passive_formats_only(self):
        logo={'data_url':image_data(PNG),'website':'https://example.com/','source_url':''}
        self.assertEqual(validate_logo(logo),logo)
        self.assertEqual(validate_logo({'disabled':True}),{'disabled':True})
        for content in (b'<svg onload="alert(1)"></svg>', b'<html>not an image</html>', b'\x00\x00\x01\x00'+b'\xff'*30, b'x'*(512*1024+1)):
            with self.assertRaises(ValueError): image_data(content)
        with self.assertRaises(ValueError):validate_logo({'data_url':'data:image/jpeg;base64,'+base64.b64encode(PNG).decode()})

    def test_discovery_prioritizes_touch_icon_and_joins_relative_paths(self):
        with patch('recognition.fetch_public_page', side_effect=[('<link rel="icon" href="/tiny.ico"><link rel="apple-touch-icon" href="/large.png">','https://example.com/jobs'),(PNG,'https://example.com/large.png')]) as fetch:
            logo=discover_logo('未知公司','https://example.com')
            self.assertEqual(logo['source_url'],'https://example.com/large.png')
            self.assertEqual(fetch.call_args.args[0],'https://example.com/large.png')
            self.assertTrue(fetch.call_args.kwargs['image'])

    def test_embedded_image_sniffs_actual_format(self):
        embedded='data:image/x-icon;base64,'+base64.b64encode(PNG).decode()
        with patch('recognition.fetch_public_page', return_value=('<link rel="shortcut icon" href="'+embedded+'">','https://example.com/')) as fetch:
            result=discover_logo('未知','https://example.com/')
            self.assertTrue(result['data_url'].startswith('data:image/png;'))
            self.assertEqual(fetch.call_count,1)

    def test_unknown_company_needs_explicit_site_and_blocks_private_site(self):
        with self.assertRaises(ValueError):discover_logo('未知公司')
        with self.assertRaises(RecognitionError):discover_logo('未知公司','http://127.0.0.1')

    def test_local_cache_shared_and_backup_preserves_manual_choice(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'one.sqlite3')
            logo={'data_url':image_data(PNG),'website':'https://example.com/','source_url':''}
            store.set_company_logo(' 腾讯 ',logo)
            self.assertEqual(Store(store.path).company_logos()['腾讯'],logo)
            restored=Store(Path(folder)/'two.sqlite3')
            restored.import_data(store.export())
            self.assertEqual(restored.company_logos(),store.company_logos())
            restored.set_company_logo('腾讯',{'disabled':True})
            restored.import_data(store.export())
            self.assertEqual(restored.company_logos()['腾讯'],{'disabled':True})
            broken=store.export();broken['company_logos']['坏图']={'data_url':'javascript:bad'}
            with self.assertRaises(ValidationError):restored.import_data(broken)
            self.assertNotIn('坏图',restored.company_logos())
