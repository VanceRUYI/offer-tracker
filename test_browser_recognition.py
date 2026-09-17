import json
import unittest
from unittest.mock import patch
from recognition import recognize, RecognitionError


class BrowserRecognitionTests(unittest.TestCase):
    def test_job_code_in_current_heading_is_a_separate_field_without_model_call(self):
        for role in ('北京-网络研发工程师(J100700)', '北京-网络研发工程师（J100700）'):
            with self.subTest(role=role):
                page={'url':'https://example.com/jobs/detail/uuid','title':'百度校园招聘',
                      'html':'','text':role,'headings':[role],'responses':[]}
                with patch('recognition.fetch_public_page',return_value=('<div id="app"></div>',page['url'])), \
                     patch('browser_reader.read_rendered_page',return_value=page), \
                     patch('glm_recognition.extract_fields',side_effect=AssertionError('no model needed')):
                    result=recognize({'url':page['url']},use_ai=True)
                self.assertEqual(result['fields']['job_code'],'J100700')
                self.assertEqual(result['fields']['role'],role)
                self.assertIn('J100700',result['evidence']['job_code'])
                self.assertEqual(result['ai_status'],'not_needed')

    def test_title_code_handles_static_pages_but_does_not_treat_years_as_codes(self):
        for suffix, expected in [('J001007','J001007'), ('2027',None), ('27届校招',None), ('北京',None), ('C++',None)]:
            with self.subTest(suffix=suffix):
                html='<title>网络研发工程师('+suffix+') - 示例科技招聘</title>'
                with patch('recognition.fetch_public_page',return_value=(html,'https://example.com/job')):
                    result=recognize({'url':'https://example.com/job'},use_ai=True)
                self.assertEqual(result['fields'].get('job_code'),expected)

    def test_explicit_job_code_is_not_overwritten_by_title_suffix(self):
        page={'url':'https://example.com/job','title':'示例科技招聘','html':'',
              'text':'网络研发工程师(J100700)\n岗位编号：R00123',
              'headings':['网络研发工程师(J100700)'],'responses':[]}
        with patch('recognition.fetch_public_page',return_value=('',page['url'])), \
             patch('browser_reader.read_rendered_page',return_value=page):
            result=recognize({'url':page['url']})
        self.assertEqual(result['fields']['job_code'],'R00123')

    def test_public_title_code_precedes_internal_api_id_but_not_explicit_code(self):
        role='网络研发工程师(REQ-001234)'
        for extra, expected in [({},'REQ-001234'), ({'jobCode':'A000987'},'A000987')]:
            with self.subTest(extra=extra):
                result=self.extract(responses=[{'url':'https://jobs.example.com/api/detail','data':{
                    'id':22020,'name':role,'description':'研发网络系统', **extra}}])
                self.assertEqual(result['fields']['job_code'],expected)

    def test_title_code_does_not_come_from_recommended_position_or_url_uuid(self):
        page={'url':'https://example.com/jobs/545e6823-28d2-4c8c-a162-123456789012',
              'title':'示例公司招聘','html':'','headings':['网络研发工程师'],
              'text':'网络研发工程师\n职位描述\n开发网络系统\n推荐岗位\n算法工程师(J100700)', 'responses':[]}
        with patch('recognition.fetch_public_page',return_value=('',page['url'])), \
             patch('browser_reader.read_rendered_page',return_value=page):
            result=recognize({'url':page['url']})
        self.assertNotIn('job_code',result['fields'])

    def extract(self, **extra):
        from rendered_extraction import extract_rendered_page
        return extract_rendered_page({'url':'https://jobs.example.com/position/22020',
            'title':'示例科技校园招聘','text':'','html':'','headings':[], 'responses':[], **extra})

    def test_dynamic_json_response_yields_job_fields_not_recruitment_status(self):
        result=self.extract(responses=[{'url':'https://jobs.example.com/api/detail', 'data':{
            'data':{'positionId':22020,'positionName':'【2027校招】Agent研发工程师',
                    'workplace':'北京市，上海市','jobProjectName':'2027 校园招聘',
                    'duty':'研发 Agent','recruitStatus':'in_recruitment','datePosted':'2026-09-01'}}}])
        self.assertEqual(result['fields'],{'company':'示例科技','role':'【2027校招】Agent研发工程师',
            'job_code':'22020','city':'北京市，上海市','batch':'2027 校园招聘'})
        self.assertIn('api/detail',result['evidence']['role'])

    def test_rendered_dom_heading_and_separate_field_labels(self):
        result=self.extract(title='加入我们 - 某某科技',headings=['高级后端工程师'],
            text='高级后端工程师\n工作地点\n杭州\n职位编号\nJ00019\n岗位职责\n开发业务系统')
        self.assertEqual(result['fields']['company'],'某某科技')
        self.assertEqual(result['fields']['role'],'高级后端工程师')
        self.assertEqual(result['fields']['city'],'杭州')
        self.assertEqual(result['fields']['job_code'],'J00019')

    def test_multiple_jobs_not_arbitrarily_chosen(self):
        result=self.extract(url='https://jobs.example.com/list',headings=['算法工程师','后端工程师'],
            responses=[{'url':'https://jobs.example.com/api/list','data':{'items':[
                {'positionId':1,'positionName':'算法工程师','duty':'算法'},
                {'positionId':2,'positionName':'后端工程师','duty':'服务'}]}}])
        self.assertNotIn('role',result['fields'])
        self.assertNotIn('job_code',result['fields'])
        self.assertTrue(result['facts'])

    def test_matching_url_id_excludes_recommended_jobs(self):
        result=self.extract(responses=[{'url':'https://jobs.example.com/api/jobs','data':[
            {'id':999,'jobName':'推荐岗位工程师','description':'推荐'},
            {'id':22020,'jobName':'当前岗位工程师','description':'当前','companyName':'当前公司'}]}])
        self.assertEqual(result['fields']['role'],'当前岗位工程师')
        self.assertEqual(result['fields']['company'],'当前公司')

    def test_public_code_and_nested_city_are_separate_from_route_ids(self):
        result=self.extract(responses=[{'url':'https://jobs.example.com/api/detail','data':{'data':[
            {'id':'22020','job_id':'999','code':'A0019','title':'算法工程师','description':'研发',
             'city_info':{'name':'上海'}},
            {'id':'777','title':'推荐工程师','description':'推荐'}]}}])
        self.assertEqual(result['fields']['role'],'算法工程师')
        self.assertEqual(result['fields']['job_code'],'A0019')
        self.assertEqual(result['fields']['city'],'上海')

    def test_navigation_and_placeholders_are_not_locations(self):
        for text in ('工作地点\n团队\n登录','工作地点：-'):
            self.assertNotIn('city',self.extract(text=text)['fields'])

    def test_styled_title_without_heading_tag_is_read_from_intro(self):
        result=self.extract(text='首页\n登录\n高级算法工程师\n上海\n职位描述\n研发系统。\n推荐岗位\n后端工程师')
        self.assertEqual(result['fields']['role'],'高级算法工程师')

    def test_failed_page_resources_are_explained(self):
        result=self.extract(diagnostics={'failures':[{'url':'https://example.com/main.js','reason':'timeout'}]})
        self.assertIn('未完整加载',str(result['facts']))

    def test_login_page_does_not_become_a_job(self):
        result=self.extract(title='账号登录',text='请登录后查看职位',headings=['登录'])
        self.assertNotIn('company',result['fields']);self.assertNotIn('role',result['fields'])
        self.assertTrue(result['facts'])

    def test_platform_icon_is_not_assigned_to_the_employer(self):
        url='https://tenant.feishu.cn/position/22020'
        snapshot={'url':url,'title':'示例公司招聘','text':'公司：示例公司\n岗位：算法工程师',
                  'html':'','headings':[], 'responses':[], 'icon_url':'https://tenant.feishu.cn/favicon.ico'}
        with patch('recognition.fetch_public_page',return_value=('<div id="app"></div>',url)),patch('browser_reader.read_rendered_page',return_value=snapshot):
            result=recognize({'url':url})
        self.assertEqual(result['fields']['role'],'算法工程师')
        self.assertNotIn('company_logo',result)

    def test_standard_jobposting_remains_fast_path(self):
        job={'@type':'JobPosting','title':'算法工程师','hiringOrganization':{'name':'示例公司'}}
        with patch('recognition.fetch_public_page',return_value=('<script type="application/ld+json">'+json.dumps(job)+'</script>','https://example.com/job')), patch('browser_reader.read_rendered_page') as reader:
            result=recognize({'url':'https://example.com/job'})
        self.assertEqual(result['fields']['role'],'算法工程师');reader.assert_not_called()

    def test_empty_shell_uses_generic_reader(self):
        snapshot={'url':'https://example.com/job','title':'示例公司招聘','text':'公司：示例公司\n岗位：算法工程师','html':'','headings':[], 'responses':[]}
        with patch('recognition.fetch_public_page',return_value=('<div id="app"></div>',snapshot['url'])), patch('browser_reader.read_rendered_page',return_value=snapshot):
            result=recognize({'url':snapshot['url']})
        self.assertEqual(result['fields']['role'],'算法工程师')
        self.assertEqual(result['read_method'],'browser')

    def test_failed_browser_retains_partial_fields_and_explains_reason(self):
        with patch('recognition.fetch_public_page',return_value=('<p>公司：示例公司</p>','https://example.com/job')), patch('browser_reader.read_rendered_page',side_effect=RecognitionError('尚未安装浏览器读取组件')):
            result=recognize({'url':'https://example.com/job'})
        self.assertEqual(result['fields']['company'],'示例公司')
        self.assertIn('尚未安装',str(result['facts']))
