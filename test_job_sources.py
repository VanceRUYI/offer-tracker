import json
import unittest
from unittest.mock import patch
import job_sources


class JobSourceTests(unittest.TestCase):
    def setUp(self):
        self.sources = job_sources.JobSources()

    def page(self, **response):
        return {'url':'https://jobs.example.com/campus/position/22020', 'title':'测试公司校园招聘',
                'text':'测试公司 算法工程师', 'responses':[{
                    'url':'https://jobs.example.com/api/detail?positionId=22020', 'method':'GET',
                    'data':{'positionId':22020,'positionName':'算法工程师','workplace':'北京','duty':'研发'}, **response}]}

    def test_learned_source_reads_a_different_job_and_validates_its_identity(self):
        self.sources.learn(self.page())
        requests=[]
        def fetch(url, **kwargs):
            requests.append(url)
            return {'status':200,'body':json.dumps({'positionId':22021,'positionName':'后端工程师','workplace':'上海','duty':'研发'}).encode()}
        with patch('recognition.fetch_public_page', side_effect=fetch):
            page = self.sources.read('https://jobs.example.com/campus/position/22021')
        from rendered_extraction import extract_rendered_page
        result = extract_rendered_page(page)
        self.assertEqual(requests,['https://jobs.example.com/api/detail?positionId=22021'])
        self.assertEqual(result['fields']['role'],'后端工程师')
        self.assertEqual(result['fields']['job_code'],'22021')
        self.assertEqual(result['fields']['company'],'测试公司')

    def test_other_site_or_route_does_not_reuse_source(self):
        self.sources.learn(self.page())
        self.assertIsNone(self.sources.read('https://other.example.com/campus/position/22021'))
        self.assertIsNone(self.sources.read('https://jobs.example.com/social/position/22021'))

    def test_signed_queries_post_requests_and_cross_origin_api_are_not_learned(self):
        for response in ({'method':'POST'}, {'url':'https://jobs.example.com/api/detail?positionId=22020&token=secret'},
                         {'url':'https://api.example.com/detail?positionId=22020'}):
            self.sources.learn(self.page(**response))
        self.assertIsNone(self.sources.read('https://jobs.example.com/campus/position/22021'))

    def test_stale_or_error_response_is_not_shown_as_the_new_job(self):
        self.sources.learn(self.page())
        for data in ({'error':'not found'}, {'positionId':22020,'positionName':'旧岗位工程师','duty':'研发'}):
            with patch('recognition.fetch_public_page', return_value={'status':200,'body':json.dumps(data).encode()}):
                self.assertIsNone(self.sources.read('https://jobs.example.com/campus/position/22021'))

    def test_expired_discovery_is_not_used(self):
        with patch('job_sources.time.monotonic',return_value=100):
            self.sources.learn(self.page())
        with patch('job_sources.time.monotonic',return_value=100000):
            self.assertIsNone(self.sources.read('https://jobs.example.com/campus/position/22021'))
