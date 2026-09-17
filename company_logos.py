"""Company icon discovery and bounded, passive image validation."""
import base64
import binascii
import struct
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

MAX_ICON = 512 * 1024
# Exact names only. A recruitment platform's domain is never a company identity.
CATALOG = [
    {'name':'腾讯', 'aliases':['腾讯','腾讯科技','腾讯控股','tencent'], 'website':'https://www.tencent.com/'},
    {'name':'字节跳动', 'aliases':['字节跳动','字节','bytedance'], 'website':'https://www.bytedance.com/'},
    {'name':'阿里巴巴', 'aliases':['阿里巴巴','阿里巴巴集团','阿里','alibaba'], 'website':'https://www.alibabagroup.com/', 'icon_url':'https://static.alibabagroup.com/static/favicon.ico'},
]

# Shared recruitment/login sites carry platform icons, not employer branding.
PLATFORM_DOMAINS = ('feishu.cn','larkoffice.com','larksuite.com','mokahr.com',
                    'zhipin.com','liepin.com','51job.com','zhaopin.com','lagou.com',
                    'nowcoder.com','yingjiesheng.com','yupoo.com','beisen.com',
                    'zhiye.com','italent.cn','dayee.com','hotjob.cn','wecruit.cn',
                    'weixin.qq.com','mp.weixin.qq.com','linkedin.com','indeed.com')


def is_platform(url):
    host = (urlsplit(url).hostname or '').lower().rstrip('.')
    return any(host == domain or host.endswith('.' + domain) for domain in PLATFORM_DOMAINS)


def known_company(company):
    key = str(company).strip().lower()
    return next((item for item in CATALOG if key in item['aliases']), None)


def fetch_recognized_icon(website, icon_url):
    from recognition import validate_public_url, fetch_public_page
    website, _, _ = validate_public_url(website)
    icon_url, _, _ = validate_public_url(icon_url)
    if is_platform(website) or is_platform(icon_url):
        raise ValueError('招聘平台的图标不能作为公司图标')
    content, source = fetch_public_page(icon_url, image=True, deadline=time.monotonic()+5)
    if is_platform(source):
        raise ValueError('招聘平台的图标不能作为公司图标')
    return {'data_url':image_data(content), 'website':website, 'source_url':source}


def image_data(content):
    if not content or len(content) > MAX_ICON:
        raise ValueError('图标过大，请选择 512 KB 以内的图片')
    if content.startswith(b'\x89PNG\r\n\x1a\n') and len(content) >= 33:
        width, height = struct.unpack('>II', content[16:24])
        if not 0 < width <= 4096 or not 0 < height <= 4096:
            raise ValueError('图片尺寸过大')
        mime = 'image/png'
    elif content.startswith(b'\x00\x00\x01\x00') and len(content) >= 22:
        count = int.from_bytes(content[4:6], 'little')
        if not 0 < count <= 256 or len(content) < 6 + count * 16:
            raise ValueError('图标文件不完整')
        for i in range(count):
            size, offset = struct.unpack('<II', content[6+i*16+8:6+i*16+16])
            if not size or offset < 6+count*16 or offset+size > len(content):
                raise ValueError('图标文件不完整')
        mime = 'image/x-icon'
    elif content.startswith(b'\xff\xd8\xff') and content.endswith(b'\xff\xd9'):
        mime = 'image/jpeg'
    elif content.startswith(b'RIFF') and content[8:12] == b'WEBP' and len(content) >= 20:
        mime = 'image/webp'
    else:
        raise ValueError('没有找到支持的图标，请上传 PNG、JPG 或 WebP 图片')
    return 'data:' + mime + ';base64,' + base64.b64encode(content).decode('ascii')


def validate_logo(value):
    if not isinstance(value, dict):
        raise ValueError('图标格式不正确')
    if value.get('disabled') is True:
        return {'disabled':True}
    raw = value.get('data_url', '')
    if not isinstance(raw, str) or len(raw) > MAX_ICON * 4 // 3 + 100:
        raise ValueError('图标过大')
    try:
        header, encoded = raw.split(',', 1)
        if header not in ('data:image/png;base64','data:image/jpeg;base64','data:image/webp;base64','data:image/x-icon;base64'):
            raise ValueError('不支持这个图片格式')
        validated = image_data(base64.b64decode(encoded, validate=True))
        if validated.split(',')[0] != header:
            raise ValueError('图片格式与内容不一致')
    except (ValueError, binascii.Error):
        raise ValueError('图标图片无效，请重新选择')
    result = {'data_url':validated}
    for key in ('website','source_url'):
        url = value.get(key, '')
        if not isinstance(url,str) or len(url)>2000 or (url and (urlsplit(url).scheme not in ('https','http') or not urlsplit(url).hostname or urlsplit(url).username)):
            raise ValueError('图标来源网址不正确')
        result[key] = url
    return result


class IconParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        rel = values.get('rel', '').lower().split()
        if tag == 'link' and ('icon' in rel or 'apple-touch-icon' in rel) and values.get('href'):
            # Touch icons tend to be larger than traditional 16px favicons.
            self.icons.append((0 if 'apple-touch-icon' in rel else 1, values['href']))


def discover_logo(company, website='', *, automatic=False):
    from recognition import fetch_public_page, validate_public_url, extract_page, RecognitionError
    known = known_company(company)
    website = website.strip() if isinstance(website,str) else ''
    if automatic and known:
        website = known['website']
    if not website:
        if not known:
            raise ValueError('请填写公司官网，或上传公司图标')
        website = known['website']
    website, _, _ = validate_public_url(website)
    if automatic and is_platform(website):
        raise ValueError('招聘平台图标不代表公司，暂时保留默认企业图标')
    if known and known.get('icon_url') and urlsplit(website).hostname == urlsplit(known['website']).hostname:
        try:
            content, source = fetch_public_page(known['icon_url'], image=True)
            return {'data_url':image_data(content), 'website':website, 'source_url':source}
        except (ValueError, RecognitionError):
            pass
    parser = IconParser()
    final = website
    try:
        html, final = fetch_public_page(website, head_only=True)
        if automatic:
            if is_platform(final):
                raise ValueError('跳转到了招聘平台，暂时保留默认企业图标')
            if not known:
                detected = extract_page(html, final)['fields'].get('company', '')
                if detected.strip().lower() != str(company).strip().lower():
                    raise ValueError('无法确认页面所属公司，暂时保留默认企业图标')
        parser.feed(html)
    except RecognitionError:
        if automatic and not known:
            raise ValueError('暂时无法确认投递网址的图标')
        pass
    candidates = [urljoin(final, href) for _,href in sorted(parser.icons, key=lambda item:item[0])]
    candidates.append(urljoin(final, '/favicon.ico'))
    for candidate in list(dict.fromkeys(candidates))[:4]:
        try:
            if automatic and is_platform(candidate):
                continue
            if candidate.startswith('data:image/') and ';base64,' in candidate and len(candidate) <= MAX_ICON * 4 // 3 + 100:
                content = base64.b64decode(candidate.split(',',1)[1], validate=True)
                source = final
            else:
                content, source = fetch_public_page(candidate, image=True)
            if automatic and is_platform(source):
                continue
            return {'data_url':image_data(content), 'website':final, 'source_url':source}
        except (ValueError, RecognitionError):
            continue
    raise ValueError('暂时无法获取官网图标，可以换一个官网地址，或直接上传图片')
