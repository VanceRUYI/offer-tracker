"""Conservative extraction of public job pages and pasted application notices."""
import http.client
import base64
import ipaddress
import json
import re
import socket
import ssl
import time
import zlib
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit, unquote
from urllib.request import getproxies
from store import ValidationError, STATUSES, COMPANY_TYPES, INDUSTRIES

MAX_PAGE = 2 * 1024 * 1024
FAKE_DNS = ipaddress.ip_network('198.18.0.0/15')


class RecognitionError(ValidationError):
    pass


def validate_public_url(url):
    if not isinstance(url, str) or not url.strip() or len(url) > 2000:
        raise RecognitionError('请粘贴有效的招聘页面网址')
    url = url.strip()
    if '://' not in url:
        url = 'https://' + url
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').rstrip('.').encode('idna').decode('ascii').lower()
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    except (ValueError, UnicodeError):
        raise RecognitionError('网址格式不正确')
    if parsed.scheme not in ('http', 'https') or not host or parsed.username or parsed.password or port not in (80, 443):
        raise RecognitionError('仅支持普通 http/https 招聘网址，不支持带登录凭据的网址')
    if any(ord(c) < 33 for c in url) or host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise RecognitionError('仅支持公开招聘页面，不能读取本机或内网地址')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise RecognitionError('仅支持公开招聘页面，不能读取本机或内网地址')
    hostpart = '[' + host + ']' if ':' in host else host
    authority = hostpart + (':' + str(port) if parsed.port else '')
    normalized = urlunsplit((parsed.scheme, authority, quote(parsed.path or '/', safe='/%:@!$&\'()*+,;=-._~'), quote(parsed.query, safe='%/:?@!$&\'()*+,;=-._~'), ''))
    return normalized, host, port


def proxy_tls_connection(proxy, address, port, hostname, timeout):
    """Pin CONNECT to a public IP while verifying TLS against the original hostname."""
    if not ipaddress.ip_address(address).is_global:
        raise RecognitionError('该网址指向内网或本机地址，无法读取')
    con = http.client.HTTPConnection(proxy.hostname, proxy.port or 80, timeout=timeout)
    headers = {}
    if proxy.username:
        credentials = unquote(proxy.username) + ':' + unquote(proxy.password or '')
        headers['Proxy-Authorization'] = 'Basic ' + base64.b64encode(credentials.encode()).decode('ascii')
    con.set_tunnel(address, port, headers=headers)
    try:
        con.connect()
        con.sock = ssl.create_default_context().wrap_socket(con.sock, server_hostname=hostname)
        return con
    except Exception:
        con.close()
        raise


def public_dns_addresses(payload):
    if not isinstance(payload, dict) or payload.get('Status') != 0:
        raise RecognitionError('无法解析岗位网站，请复制页面文字识别')
    answers = payload.get('Answer', [])
    if not isinstance(answers, list):
        raise RecognitionError('无法解析岗位网站，请复制页面文字识别')
    addresses = [ipaddress.ip_address(a.get('data', '')) for a in answers
                 if isinstance(a, dict) and a.get('type') in (1, 28)]
    if not addresses or any(not a.is_global for a in addresses):
        raise RecognitionError('该网址没有可验证的公网地址，无法读取')
    return [str(a) for a in addresses]


def resolve_through_proxy(proxy, host, deadline):
    # Fake DNS cannot establish a public destination. Resolve independently over
    # authenticated DoH, then pin the subsequent tunnel to the returned public IP.
    # Prefer a regional resolver for Chinese recruitment sites: the previous
    # Google-only lookup selected distant CDN nodes even on the very first read.
    # Keep the system resolver path untouched when it already returns public IPs.
    providers = [('223.5.5.5', 'dns.alidns.com', 2), ('8.8.8.8', 'dns.google', 4)]
    for address, hostname, budget in providers:
        try:
            return query_public_dns(proxy, host, min(deadline, time.monotonic()+budget), address, hostname)
        except RecognitionError:
            raise  # Invalid/private answers remain a hard failure.
        except (OSError, ValueError, http.client.HTTPException):
            if time.monotonic() >= deadline:
                break
    raise RecognitionError('无法解析岗位网站，请稍后重试')


def query_public_dns(proxy, host, deadline, address, hostname):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError()
    con = proxy_tls_connection(proxy, address, 443, hostname, remaining)
    sock = con.sock
    try:
        con.request('GET', '/resolve?name=' + quote(host, safe='') + '&type=A&edns_client_subnet=0.0.0.0/0',
                    headers={'Host':hostname, 'Accept':'application/dns-json'})
        response = con.getresponse()
        if response.status != 200:
            raise OSError('Public DNS service unavailable')
        content = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            sock.settimeout(min(8, remaining))
            chunk = response.read1(min(16384, 65537 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > 65536:
                raise RecognitionError('网站解析响应过大，请复制页面文字识别')
        return public_dns_addresses(json.loads(content))[0]
    finally:
        con.close()


def fetch_public_page(url, *, image=False, head_only=False, resource=False,
                      method='GET', body=None, headers=None, deadline=None, address_cache=None,
                      browser_session=False, response_metadata=None):
    deadline = deadline or time.monotonic() + 20
    limit = 8 * 1024 * 1024 if resource else 512 * 1024 if image else MAX_PAGE
    if method not in ('GET', 'POST', 'HEAD', 'OPTIONS') or (body and len(body) > 128*1024):
        raise RecognitionError('页面请求超出读取范围')
    for _ in range(5):
        normalized, host, port = validate_public_url(url)
        try:
            addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            proxy = urlsplit(getproxies().get('https', ''))
            resolved = [ipaddress.ip_address(a[4][0]) for a in addresses]
            # Some local proxy clients return benchmark-range synthetic DNS addresses.
            # Independently resolve these HTTPS hosts before using the configured proxy.
            use_proxy = bool(resolved and all(a.version == 4 and a in FAKE_DNS for a in resolved)
                             and urlsplit(normalized).scheme == 'https' and proxy.scheme == 'http' and proxy.hostname)
            if not addresses or (not use_proxy and any(not a.is_global for a in resolved)):
                raise RecognitionError('该网址指向内网或本机地址，无法读取')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            # Connect to the address just checked, preventing DNS rebinding between checks and use.
            if use_proxy:
                cache_key=(host,port)
                address = (address_cache or {}).get(cache_key)
                if not address:
                    address = resolve_through_proxy(proxy, host, deadline)
                    if address_cache is not None:address_cache[cache_key]=address
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                con = proxy_tls_connection(proxy, address, port, host, min(8, remaining))
                sock = con.sock
            else:
                sock = socket.create_connection((addresses[0][4][0], port), timeout=min(8, remaining))
                con = http.client.HTTPConnection(host, port, timeout=min(8, remaining))
            try:
                if not use_proxy and urlsplit(normalized).scheme == 'https':
                    try:
                        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
                    except Exception:
                        sock.close()
                        raise
                con.sock = sock
                parsed = urlsplit(normalized)
                path = parsed.path + ('?' + parsed.query if parsed.query else '')
                request_headers={'host':parsed.netloc, 'user-agent':'AutumnWorkbench/1.0 (personal job link preview)', 'accept':'image/png,image/x-icon,image/jpeg,image/webp' if image else 'text/html,application/xhtml+xml', 'accept-encoding':'gzip, deflate'}
                if resource:
                    request_headers.update({k.lower():v for k,v in (headers or {}).items()
                        if k.lower() in ('accept','content-type','origin','referer','user-agent') or k.lower().startswith('x-')})
                    if browser_session and (headers or {}).get('cookie'):
                        request_headers['cookie'] = headers['cookie']
                con.request(method, path, body=body, headers=request_headers)
                response = con.getresponse()
                if not resource and response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if not location:
                        raise RecognitionError('网页跳转不完整，请粘贴最终的岗位页面网址')
                    url = urljoin(normalized, location)
                    continue
                if not resource and response.status != 200:
                    raise RecognitionError('网页无法直接读取（可能需要登录或限制访问）。可在下面粘贴页面或通知文字继续识别。')
                content_type = response.getheader('Content-Type', '')
                if not resource and not image and content_type and not any(t in content_type.lower() for t in ('text/html', 'application/xhtml+xml', 'text/plain')):
                    raise RecognitionError('这不是可识别的文字网页，请打开岗位页面后复制文字')
                compression = response.getheader('Content-Encoding', 'identity').strip().lower()
                if compression not in ('identity', 'gzip', 'deflate'):
                    raise RecognitionError('网页使用了不支持的压缩方式，请复制页面文字识别')
                decoder = zlib.decompressobj(31 if compression == 'gzip' else 15) if compression != 'identity' else None
                content = bytearray()
                transferred = 0
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    sock.settimeout(min(8, remaining))
                    chunk = response.read1(min(65536, limit + 1 - len(content)))
                    if not chunk:
                        if decoder and not decoder.eof:
                            raise RecognitionError('网页压缩内容不完整，请重试')
                        break
                    transferred += len(chunk)
                    if transferred > limit:
                        raise RecognitionError('网页内容过大，请复制岗位或通知文字识别')
                    if decoder:
                        chunk = decoder.decompress(chunk, limit + 1 - len(content))
                    content.extend(chunk)
                    if len(content) > limit:
                        raise RecognitionError('网页内容过大，请复制岗位或通知文字识别')
                    if head_only and not image and (b'</head>' in content.lower() or len(content)>=256*1024):
                        break
                    if len(content) > limit:
                        raise RecognitionError('网页内容过大，请复制岗位或通知文字识别')
                if resource:
                    response_headers={k.lower():v for k,v in response.getheaders() if k.lower() not in
                        ('set-cookie','content-length','content-encoding','transfer-encoding','connection')}
                    if browser_session and response.headers.get_all('Set-Cookie'):
                        response_headers['set-cookie']='\n'.join(response.headers.get_all('Set-Cookie'))
                    return {'body':bytes(content), 'status':response.status, 'url':normalized,
                            'headers':response_headers}
                if image:
                    return bytes(content), normalized
                if response_metadata is not None:
                    response_metadata['set_cookie']='\n'.join(response.headers.get_all('Set-Cookie') or [])
                charset = re.search(r'charset\s*=\s*["\']?([\w-]+)', content_type, re.I)
                if not charset:
                    charset = re.search(r'charset\s*=\s*["\']?([\w-]+)', bytes(content[:4096]).decode('ascii', errors='ignore'), re.I)
                for encoding in ([charset.group(1)] if charset else []) + ['utf-8', 'gb18030']:
                    try:
                        return bytes(content).decode(encoding), normalized
                    except (UnicodeError, LookupError):
                        pass
                raise RecognitionError('无法解码网页文字，请复制岗位信息后识别')
            finally:
                con.close()
        except RecognitionError:
            raise
        except (OSError, ValueError, zlib.error, http.client.HTTPException):
            raise RecognitionError('暂时无法读取这个网址。请检查网络，或粘贴已打开页面中的岗位、投递通知文字。')
    raise RecognitionError('网页跳转次数过多，请使用浏览器最终打开的岗位网址')


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.scripts, self.title = [], [], []
        self.script = None
        self.skip = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'script':
            self.script = [] if values.get('type', '').lower() == 'application/ld+json' else None
            self.skip += 1
        elif tag in ('style', 'noscript'):
            self.skip += 1
        elif tag == 'title':
            self.in_title = True
        elif tag in ('p','div','li','br','tr','h1','h2','h3','dt','dd','section'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag == 'script':
            if self.script is not None:
                self.scripts.append(''.join(self.script))
            self.script = None
            self.skip = max(0, self.skip - 1)
        elif tag in ('style', 'noscript'):
            self.skip = max(0, self.skip - 1)
        elif tag == 'title':
            self.in_title = False
        elif tag in ('p','div','li','tr','h1','h2','h3','dt','dd','section'):
            self.parts.append('\n')

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        elif self.skip:
            if self.script is not None:
                self.script.append(data)
        else:
            self.parts.append(data)


def unique_label(text, labels):
    values = re.findall(r'(?:^|\n)\s*(?:' + labels + r')\s*[:：]\s*([^\n]+)', text)
    values = list(dict.fromkeys(v.strip() for v in values if v.strip()))
    return values[0] if len(values) == 1 else ''


DATE = r'(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})日?'

TYPE_ALIASES = {'中央企业':'央企', '中央国有企业':'央企', '国有企业':'国企', '国有独资':'国企',
                '国有控股':'国企', '地方国企':'国企', '民营':'民企', '民营企业':'民企',
                '私营企业':'民企', '外资':'外企', '外资企业':'外企', '外商独资':'外企',
                '外商独资企业':'外企', '合资':'合资企业', '中外合资':'合资企业'}
INDUSTRY_ALIASES = {'互联网/电子商务':'互联网', '互联网和相关服务':'互联网', '电子商务':'互联网',
                    'AI':'人工智能', '银行':'金融', '证券':'金融', '保险':'金融',
                    '制造':'制造业', '机械制造':'制造业', '汽车制造':'制造业', '新能源':'能源',
                    '电力':'能源', '石油化工':'能源', '电信':'通信', '通信设备':'通信',
                    '医药':'医疗健康', '医疗':'医疗健康', '生物医药':'医疗健康',
                    '教育':'教育科研', '科研':'教育科研', '零售':'消费零售', '消费品':'消费零售'}


def classify_value(value, key):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    values, aliases = (COMPANY_TYPES, TYPE_ALIASES) if key == 'company_type' else (INDUSTRIES, INDUSTRY_ALIASES)
    return value if value in values else aliases.get(value, '')


def extract_classification(text, fields, evidence, facts):
    for key, label, labels in [('company_type','企业性质','企业性质|公司性质|企业类型|公司类型'),
                                ('industry','所属行业','所属行业|公司行业|企业行业|行业')]:
        raw_values = re.findall(r'(?:^|\n)\s*(?:' + labels + r')\s*[:：]\s*([^\n]+)', text)
        if not raw_values:
            continue
        values = {classify_value(v, key) for v in raw_values}
        if len(values) == 1 and '' not in values:
            fields[key] = values.pop()
            evidence[key] = '明确字段：' + ' / '.join(dict.fromkeys(v.strip() for v in raw_values))[:200]
        else:
            facts.append({'label':label + '待核对', 'value':' / '.join(raw_values)[:300]})


def parse_date(value, with_time=False):
    if len(re.findall(DATE, value)) != 1 or re.search(r'至|到|[~～]|或|、|\s[-–—]\s', value):
        return ''
    if with_time and len(re.findall(r'\d{1,2}\s*[:：]\s*\d{2}', value)) != 1:
        return ''
    pattern = DATE + (r'[ T\s]*(\d{1,2})\s*[:：]\s*(\d{2})(?!\d)' if with_time else '')
    match = re.search(pattern, value)
    if not match:
        return ''
    try:
        d = datetime(*[int(x) for x in match.groups()])
        return d.strftime('%Y-%m-%dT%H:%M' if with_time else '%Y-%m-%d')
    except ValueError:
        return ''


def extract_text(text):
    if not isinstance(text, str) or len(text) > 100000:
        raise RecognitionError('请粘贴不超过 10 万字的岗位或通知文字')
    fields, evidence, facts = {}, {}, []
    extract_classification(text, fields, evidence, facts)
    for key, labels in [('company','公司名称|公司|企业名称|招聘公司'),('role','岗位名称|职位名称|应聘职位|投递岗位|申请岗位|岗位|职位'),('city','工作地点|工作城市')]:
        value = unique_label(text, labels)
        if value and len(value) <= (160 if key == 'company' else 200):
            fields[key], evidence[key] = value, '页面或通知中的明确字段'
    application_time = unique_label(text, '投递时间|投递日期|申请时间|申请日期')
    day = parse_date(application_time)
    if day:
        fields['applied_on'], evidence['applied_on'] = day, '明确标注的投递 / 申请日期'
    elif application_time:
        facts.append({'label':'投递时间待核对','value':application_time})
    status = unique_label(text, '投递状态|申请状态|当前进度|当前阶段|进度状态|当前状态')
    aliases = {'投递成功':'已投递','简历已投递':'已投递','简历筛选中':'筛选中','测评中':'测评','待笔试':'笔试','待二面':'二面','待一面':'一面','录用':'Offer','已拒绝':'已结束','不通过':'已结束'}
    status = aliases.get(status, status)
    if status in STATUSES:
        fields['status'], evidence['status'] = status, '明确标注的个人申请进度'
    schedules = []
    for name in ('笔试','测评','一面','二面','终面','HR面','面试'):
        value = unique_label(text, re.escape(name) + '(?:时间|日期)')
        when = parse_date(value, True)
        if when:
            schedules.append((name, when))
        elif value:
            facts.append({'label':name + '时间待核对','value':value})
    if len(schedules) == 1:
        name, when = schedules[0]
        personal = re.search(r'面试邀请|笔试邀请|测评邀请|邀请您|邀您|您的(?:申请|面试|笔试)|投递状态|申请状态|当前进度|当前阶段|投递成功', text)
        if personal:
            fields['due_at'], fields['next_action'] = when, ('完成' if name == '测评' else '参加') + name
            evidence['due_at'] = evidence['next_action'] = '邀请或申请通知中标注的' + name + '时间'
        else:
            facts.append({'label':name + '时间（参考）','value':when.replace('T', ' ') + '；未确定属于个人安排，未自动填入'})
    elif len(schedules) > 1:
        facts.append({'label':'多项安排','value':'识别到多个时间，请自行选择下一步，未自动填入'})
    return {'fields':fields, 'evidence':evidence, 'facts':facts}


def extract_page(html, url):
    parser = PageParser()
    parser.feed(html)
    result = extract_text(''.join(parser.parts)[:100000])
    jobs = []

    def visit(value, depth=0):
        if depth > 30:
            return
        if isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
        elif isinstance(value, dict):
            kind = value.get('@type', '')
            if kind == 'JobPosting' or (isinstance(kind, list) and 'JobPosting' in kind):
                jobs.append(value)
            else:
                for item in value.values():
                    if isinstance(item, (dict, list)):
                        visit(item, depth + 1)

    for raw in parser.scripts:
        try:
            visit(json.loads(raw))
        except (ValueError, RecursionError):
            continue
    # Some sites repeat the same posting in multiple scripts.
    jobs = list({json.dumps(job, sort_keys=True):job for job in jobs}.values())
    if len(jobs) > 1:
        return {'fields':{}, 'evidence':{}, 'facts':[{'label':'多个岗位','value':'这是多个岗位的页面，请复制某个具体岗位的网址'}], 'source_url':url}
    fields, evidence = result['fields'], result['evidence']
    if jobs:
        job = jobs[0]
        raw_industry = job.get('industry', '')
        if isinstance(raw_industry, list) and len(raw_industry) == 1:
            raw_industry = raw_industry[0]
        industry = classify_value(raw_industry, 'industry')
        if industry:
            conflict = fields.get('industry') not in (None, industry) or any(f['label']=='所属行业待核对' for f in result['facts'])
            if conflict:
                fields.pop('industry', None)
                evidence.pop('industry', None)
                result['facts'].append({'label':'所属行业待核对','value':'网页行业信息不一致；结构化字段：' + str(raw_industry)[:200]})
            else:
                fields['industry'], evidence['industry'] = industry, '网页结构化行业字段：' + raw_industry
        elif raw_industry:
            fields.pop('industry', None)
            evidence.pop('industry', None)
            result['facts'].append({'label':'所属行业待核对','value':'结构化行业包含多项或未支持的类型：' + str(raw_industry)[:200]})
        organization = job.get('hiringOrganization', {})
        company = organization.get('name', '') if isinstance(organization, dict) else ''
        location = job.get('jobLocation', {})
        if isinstance(location, list):
            location = location[0] if len(location) == 1 else {}
        address = location.get('address', {}) if isinstance(location, dict) else {}
        city = address.get('addressLocality', '') if isinstance(address, dict) else ''
        for key, value in [('company',company),('role',job.get('title','')),('city',city)]:
            if isinstance(value, str) and value.strip() and len(value) <= (160 if key == 'company' else 200):
                fields[key], evidence[key] = value.strip(), '网页提供的结构化招聘信息'
        posted = parse_date(str(job.get('datePosted', '')))
        if posted:
            result['facts'].append({'label':'招聘发布日期', 'value':posted})
    else:
        title = ''.join(parser.title).strip()
        match = re.fullmatch(r'(.{2,80}?)\s+(?:[-|—])\s+(.{2,80}?)(?:招聘|校园招聘|社会招聘)(?:官网)?', title)
        if match and re.search(r'工程师|开发|算法|分析师|产品经理|设计师|运营|研究员|实习生', match.group(1)):
            for key, value in [('role',match.group(1)),('company',match.group(2))]:
                if key not in fields:
                    fields[key], evidence[key] = value.strip(), '网页标题，保存前请核对'
    result['source_url'] = url
    return result


def title_job_code(role):
    """A conservative code candidate from the current role, not arbitrary page IDs."""
    code = re.search(r'[（(]\s*([A-Za-z]{1,8}[-_]?\d{4,16})\s*[）)]\s*$', role)
    return code.group(1) if code else ''


def recognize(data, progress=None, *, use_ai=False):
    if not isinstance(data, dict):
        raise RecognitionError('识别内容格式不正确')
    if data.get('text'):
        return extract_text(data['text'])
    url, _, _ = validate_public_url(data.get('url', ''))
    started = time.monotonic()
    emit = progress or (lambda event: None)
    emit({'stage':'reading', 'message':'正在读取岗位页面…'})
    from job_sources import SOURCES
    from rendered_extraction import extract_rendered_page
    page = SOURCES.read(url)
    if page:
        result = extract_rendered_page(page)
        result['read_method'] = 'api'
    else:
        result = {'fields':{}, 'evidence':{}, 'facts':[], 'source_url':url}
        page = {'title':'', 'text':''}
        initial_document = None
        final = url
        try:
            metadata = {}
            html, final = fetch_public_page(url, response_metadata=metadata)
            initial_document = {'html':html, 'set_cookie':metadata.get('set_cookie','')}
            result = extract_page(html, final)
            parser = PageParser(); parser.feed(html)
            page = {'title':''.join(parser.title), 'text':' '.join(parser.parts)}
        except RecognitionError:
            pass
        if all(result['fields'].get(key) for key in ('company','role')):
            result['read_method'] = 'html'
        else:
            from browser_reader import read_rendered_page
            from rendered_extraction import extract_rendered_page
            emit({'stage':'browser', 'message':'正在加载动态岗位页面…'})
            try:
                page = read_rendered_page(final, initial_document=initial_document)
                rendered = extract_rendered_page(page)
                SOURCES.learn(page)
                for key, value in result['fields'].items():
                    if key not in rendered['fields']:
                        rendered['fields'][key] = value
                        rendered['evidence'][key] = result['evidence'][key]
                result = rendered
                result['read_method'] = 'browser'
            except RecognitionError as error:
                result['facts'].append({'label':'页面读取未完成','value':str(error)})
                result['read_method'] = 'partial'
    reading_seconds = round(time.monotonic() - started, 1)
    if use_ai:
        from glm_recognition import load_key, extract_fields, ModelError, MODEL, LIMITS
        # Company and role are the form's required fields. Do not hold a usable
        # preview behind an optional model call just to fill city/code/batch.
        skip_model = all(result['fields'].get(k) for k in ('company','role'))
        key = None if skip_model else load_key()
        result['ai_status'] = 'unconfigured' if not key else 'skipped'
        if skip_model:
            result['ai_status'] = 'not_needed'
        elif key and (page.get('text','').strip() or result['fields']):
            emit({'stage':'model', 'message':'免费 GLM 正在提取岗位信息…', 'reading_seconds':reading_seconds})
            model_started = time.monotonic()
            try:
                fields = extract_fields(page, result, key)
                for field in LIMITS:
                    result['fields'].pop(field, None)
                    result['evidence'].pop(field, None)
                result['fields'].update(fields)
                result['evidence'].update({field:'GLM 提取，已检查文字依据，请核对：'+value for field,value in fields.items()})
                if fields.get('role'):
                    result['facts'] = [fact for fact in result['facts'] if fact['label'] != '已读取页面']
                result['ai_status'] = 'success'
                result['ai_model'] = MODEL
            except ModelError as error:
                result['ai_status'] = 'fallback'
                result['facts'].append({'label':'AI 识别未完成', 'value':str(error)+'；以下保留规则识别结果。'})
            result['model_seconds'] = round(time.monotonic() - model_started, 1)
        elif not key:
            result['facts'].append({'label':'规则识别', 'value':'尚未配置本地模型密钥，当前使用规则识别。'})
        else:
            result['facts'].append({'label':'AI 未调用', 'value':'没有读到可供模型提取的页面内容。'})
        result['reading_seconds'] = reading_seconds
    # Some sites expose the public job code only as a suffix of the role title.
    # Keep the source title intact; never replace an already identified code.
    if not result['fields'].get('job_code'):
        code = title_job_code(result['fields'].get('role', ''))
        if code:
            result['fields']['job_code'] = code
            result['evidence']['job_code'] = '当前岗位标题中的编号：' + code
    from company_logos import is_platform
    if (result['fields'].get('company') and result['fields'].get('role') and result.get('icon_url')
            and not is_platform(result['source_url']) and not is_platform(result['icon_url'])):
        # Return the candidate URL immediately; the logo manager fetches it after save.
        result['company_logo'] = {'company':result['fields']['company'], 'application_url':url,
            'logo':{'website':result['source_url'], 'icon_url':result['icon_url']}}
    return result
