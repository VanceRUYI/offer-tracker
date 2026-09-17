import json
import io
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from recognition import extract_page, extract_text, validate_public_url, RecognitionError, public_dns_addresses, proxy_tls_connection, resolve_through_proxy


class RecognitionTests(unittest.TestCase):
    def resolve_fixture(self, answers):
        class Socket:
            def settimeout(self, value): pass
        class Response(io.BytesIO):
            status = 200
        class Connection:
            sock = Socket()
            def __init__(self, payload): self.payload = payload
            def request(self, *args, **kwargs): pass
            def getresponse(self): return Response(json.dumps(self.payload).encode())
            def close(self): pass
        def connect(proxy, address, port, hostname, timeout):
            answer = answers[hostname]
            if isinstance(answer, Exception): raise answer
            return Connection({'Status': 0, 'Answer': [{'type': 1, 'data': answer}]})
        with patch('recognition.proxy_tls_connection', side_effect=connect):
            return resolve_through_proxy(urlsplit('http://localhost:7890'), 'jobs.example.com', time.monotonic()+5)

    def test_fake_dns_prefers_regional_cdn_answer_for_first_read(self):
        self.assertEqual(self.resolve_fixture({'dns.alidns.com': '8.8.4.4', 'dns.google': '8.8.8.8'}), '8.8.4.4')

    def test_fake_dns_uses_backup_when_primary_is_unreachable(self):
        self.assertEqual(self.resolve_fixture({'dns.alidns.com': TimeoutError(), 'dns.google': '8.8.8.8'}), '8.8.8.8')

    def test_fake_dns_does_not_accept_private_primary_answer(self):
        with self.assertRaises(RecognitionError):
            self.resolve_fixture({'dns.alidns.com': '127.0.0.1', 'dns.google': '8.8.8.8'})

    def test_company_nature_and_industry_are_separate_explicit_candidates(self):
        result = extract_text('公司：示例科技\n企业性质：民营企业\n所属行业：互联网/电子商务\n岗位：算法工程师')
        self.assertEqual(result['fields'].get('company_type'), '民企')
        self.assertEqual(result['fields'].get('industry'), '互联网')
        self.assertIn('民营企业', result['evidence']['company_type'])
        self.assertEqual(extract_text('企业类型：央企')['fields'].get('company_type'), '央企')

    def test_classification_does_not_guess_from_names_roles_or_ambiguous_labels(self):
        for text in ('公司：中国示例科技\n岗位：互联网产品经理\n客户包含央企、外企', '企业性质：非国企', '企业性质：上市公司', '企业性质：国企/民企', '所属行业：互联网、金融'):
            self.assertNotIn('company_type', extract_text(text)['fields'])
            self.assertNotIn('industry', extract_text(text)['fields'])

    def test_job_posting_industry_and_unknown_classification_reference(self):
        job = {'@type':'JobPosting','title':'工程师','industry':'制造业','hiringOrganization':{'name':'示例公司'}}
        result = extract_page('<script type="application/ld+json">'+json.dumps(job)+'</script>', 'https://example.com/jobs/1')
        self.assertEqual(result['fields'].get('industry'), '制造业')
        self.assertNotIn('company_type', result['fields'])
        self.assertTrue(extract_text('企业性质：混合所有制')['facts'])

    def test_conflicting_industry_sources_need_review(self):
        job = {'@type':'JobPosting','industry':'制造业'}
        result = extract_page('<p>所属行业：互联网</p><script type="application/ld+json">'+json.dumps(job)+'</script>', 'https://example.com/jobs/1')
        self.assertNotIn('industry', result['fields'])
        self.assertTrue(result['facts'])

    def test_structured_multiple_industries_do_not_silently_keep_one_candidate(self):
        for raw in (['互联网','金融'], '互联网、金融'):
            job = {'@type':'JobPosting','industry':raw}
            result = extract_page('<p>所属行业：互联网</p><script type="application/ld+json">'+json.dumps(job)+'</script>', 'https://example.com/jobs/1')
            self.assertNotIn('industry', result['fields'])
            self.assertTrue(result['facts'])

    def test_independent_dns_rejects_private_and_mixed_answers(self):
        for addresses in (['127.0.0.1'], ['198.18.0.1'], ['8.8.8.8', '10.0.0.1'], ['::1'], []):
            with self.assertRaises(RecognitionError):
                public_dns_addresses({'Status':0, 'Answer':[{'type':1,'data':a} for a in addresses]})
        self.assertEqual(public_dns_addresses({'Status':0, 'Answer':[{'type':5,'data':'alias.example.com'}, {'type':1,'data':'8.8.4.4'}]}), ['8.8.4.4'])

    def test_proxy_connect_pins_ip_and_preserves_hostname_tls(self):
        with patch('recognition.http.client.HTTPConnection') as connection, patch('recognition.ssl.create_default_context') as context:
            con = proxy_tls_connection(urlsplit('http://localhost:7890'), '8.8.4.4', 443, 'jobs.example.com', 4)
            con.set_tunnel.assert_called_once_with('8.8.4.4', 443, headers={})
            self.assertEqual(context.return_value.wrap_socket.call_args.kwargs['server_hostname'], 'jobs.example.com')
            con.connect.assert_called_once()
        with self.assertRaises(RecognitionError):
            proxy_tls_connection(urlsplit('http://localhost:7890'), '192.168.1.1', 443, 'jobs.example.com', 4)

    def test_job_posting_does_not_invent_application_date_or_status(self):
        job = {'@type':'JobPosting', 'title':'算法工程师', 'hiringOrganization':{'name':'示例科技'}, 'datePosted':'2026-08-20', 'jobLocation':{'address':{'addressLocality':'北京'}}}
        html = '<script type="application/ld+json">' + json.dumps(job) + '</script>'
        result = extract_page(html, 'https://jobs.example.com/123')
        self.assertEqual(result['fields']['company'], '示例科技')
        self.assertEqual(result['fields']['role'], '算法工程师')
        self.assertEqual(result['fields']['city'], '北京')
        self.assertNotIn('applied_on', result['fields'])
        self.assertNotIn('status', result['fields'])
        self.assertIn({'label':'招聘发布日期','value':'2026-08-20'}, result['facts'])

    def test_explicit_notice_extracts_schedule_and_actual_application_date(self):
        result=extract_text('公司名称：示例科技\n岗位名称：后端开发工程师\n投递时间：2026年9月12日 10:30\n当前进度：二面\n二面时间：2026年9月18日 14:30')
        self.assertEqual(result['fields']['company'],'示例科技')
        self.assertEqual(result['fields']['role'],'后端开发工程师')
        self.assertEqual(result['fields']['applied_on'],'2026-09-12')
        self.assertEqual(result['fields']['due_at'],'2026-09-18T14:30')
        self.assertEqual(result['fields']['status'],'二面')
        self.assertEqual(result['fields']['next_action'],'参加二面')

    def test_flow_labels_are_not_evidence_of_actual_progress(self):
        result=extract_text('招聘流程：投递 → 筛选 → 笔试 → 面试 → Offer\n发布时间：2026-09-10\n面试时间：待通知')
        self.assertNotIn('status',result['fields'])
        self.assertNotIn('applied_on',result['fields'])
        self.assertNotIn('due_at',result['fields'])

    def test_generic_title_or_multiple_jobs_not_arbitrarily_selected(self):
        result=extract_page('<title>欢迎加入我们 - 招聘官网</title>', 'https://jobs.example.com')
        self.assertFalse(result['fields'])
        job={'@type':'JobPosting','title':'后端工程师','hiringOrganization':{'name':'甲公司'}}
        page='<script type="application/ld+json">'+json.dumps([job,{**job,'title':'算法工程师'}])+'</script>'
        self.assertFalse(extract_page(page,'https://jobs.example.com')['fields'])

    def test_html_labels_and_title_fallback(self):
        result=extract_page('<title>算法工程师 - 示例科技招聘</title><p>投递状态：筛选中</p><div>投递日期：2026-09-10</div>', 'https://jobs.example.com/123')
        self.assertEqual(result['fields']['company'],'示例科技')
        self.assertEqual(result['fields']['role'],'算法工程师')
        self.assertEqual(result['fields']['status'],'筛选中')
        self.assertEqual(result['fields']['applied_on'],'2026-09-10')

    def test_invalid_or_ambiguous_dates_are_left_for_manual_review(self):
        for value in ('面试时间：9月18日 14:00','面试时间：2026-02-31 14:00','面试时间：2026-09-18 25:00'):
            self.assertNotIn('due_at',extract_text(value)['fields'])
        result=extract_text('当前进度：笔试\n当前进度：已结束')
        self.assertNotIn('status',result['fields'])

    def test_recruitment_windows_and_alternative_times_are_not_personal_dates(self):
        result=extract_text('投递时间：2026-09-01 至 2026-09-30\n面试邀请\n面试时间：2026-09-18 14:00 或 16:00')
        self.assertNotIn('applied_on',result['fields'])
        self.assertNotIn('due_at',result['fields'])

    def test_public_recruitment_schedule_is_reference_only(self):
        result=extract_page('<h1>校园招聘统一安排</h1><p>笔试时间：2026-09-18 14:00</p>', 'https://jobs.example.com')
        self.assertNotIn('status',result['fields'])
        self.assertNotIn('due_at',result['fields'])
        self.assertTrue(result['facts'])

    def test_rejects_private_networks_credentials_and_unusual_ports(self):
        for url in ('http://127.0.0.1:8765','http://localhost','http://169.254.169.254/','http://[::1]/','http://10.0.0.1/','file:///etc/passwd','https://user:pass@example.com','https://example.com:444/'):
            with self.assertRaises(RecognitionError):
                validate_public_url(url)


if __name__=='__main__':
    unittest.main()
