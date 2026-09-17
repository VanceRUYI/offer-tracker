"""Learn public GET job endpoints from actual page traffic, without site adapters."""
import json
import re
import threading
import time
from urllib.parse import urlsplit, parse_qsl


class JobSources:
    def __init__(self):
        self.entries = {}
        self.lock = threading.Lock()

    def learn(self, page):
        from company_logos import is_platform
        from rendered_extraction import extract_rendered_page
        url = page.get('url', '')
        parsed = urlsplit(url)
        if is_platform(url):
            return
        ids = [p for p in parsed.path.split('/') if re.fullmatch(r'\d{3,24}', p)]
        ids += [v for _, v in parse_qsl(parsed.query) if re.fullmatch(r'\d{3,24}', v)]
        for response in page.get('responses', []):
            api = response.get('url', '')
            target = urlsplit(api)
            if response.get('method') != 'GET' or (target.scheme,target.netloc) != (parsed.scheme,parsed.netloc):
                continue
            # Do not retain signed URLs, credentials, cookies, or arbitrary query parameters.
            params = parse_qsl(target.query, keep_blank_values=True)
            if any(not re.fullmatch(r'(?:position|job|post|requisition)?_?id', k, re.I) for k, _ in params):
                continue
            for identifier in ids:
                values = target.path.split('/') + [v for _,v in params]
                if identifier not in values or api.count(identifier) != 1 or url.count(identifier) != 1:
                    continue
                subset = {**page, 'html':'', 'text':'', 'responses':[response]}
                result = extract_rendered_page(subset)
                if not result['fields'].get('company') or not result['evidence'].get('role','').startswith('页面加载的岗位数据'):
                    continue
                before, after = url.split(identifier)
                entry = {'match':re.compile(re.escape(before)+r'(\d{3,24})'+re.escape(after)+r'\Z'),
                         'api':api.split(identifier), 'company':result['fields']['company'],
                         'icon_url':page.get('icon_url',''), 'expires':time.monotonic()+6*3600}
                with self.lock:
                    self.entries[(before, after)] = entry
                    while len(self.entries)>32:
                        self.entries.pop(next(iter(self.entries)))
                return

    def read(self, url):
        from recognition import fetch_public_page, RecognitionError
        from rendered_extraction import extract_rendered_page
        with self.lock:
            self.entries = {k:v for k,v in self.entries.items() if v['expires']>time.monotonic()}
            entries = list(self.entries.values())
        for entry in entries:
            match = entry['match'].fullmatch(url)
            if not match:
                continue
            api = match.group(1).join(entry['api'])
            try:
                response = fetch_public_page(api, resource=True, headers={'accept':'application/json'},
                                             deadline=time.monotonic()+3)
                if response['status'] != 200 or len(response['body'])>256*1024:
                    return None
                page = {'url':url, 'title':entry['company']+'招聘', 'text':'', 'icon_url':entry['icon_url'],
                        'responses':[{'url':api,'method':'GET','data':json.loads(response['body'])}]}
                result = extract_rendered_page(page)
                # With no visible title/text, a role is returned only for an exact matching ID.
                if result['evidence'].get('role','').startswith('页面加载的岗位数据'):
                    return page
            except (RecognitionError, ValueError, KeyError, TypeError):
                pass
            return None
        return None


SOURCES = JobSources()
