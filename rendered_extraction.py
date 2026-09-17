"""Evidence-based extraction from a rendered page; no company-specific API paths."""
import json
import re
from urllib.parse import urlsplit, parse_qs, unquote

ROLE = re.compile(r'工程师|开发|算法|分析师|产品经理|设计师|运营|研究员|实习生|经理|专员|engineer|developer|scientist|designer|analyst', re.I)
LIMITS = {'company':160,'role':200,'city':160,'job_code':100,'batch':80}


def scalar(value, limit=200):
    if isinstance(value, (str,int)) and not isinstance(value,bool):
        value=str(value).strip()
        if value and value.lower() not in ('-','--','—','暂无','待定','null','undefined') and len(value)<=limit and not re.search(r'<[^>]+>',value):
            return value
    return ''


def first(obj, keys, limit=200):
    return next((v for key in keys if (v:=scalar(obj.get(key),limit))), '')


def company_from_title(title, role=''):
    title=title.replace(role,'') if role else title
    pieces=re.split(r'\s*[|｜—–-]\s*',title)
    for part in reversed(pieces):
        part=re.sub(r'(?:加入我们|欢迎加入|招聘官网|校园招聘|社会招聘|人才招聘|招聘网站|招聘|Careers?)','',part,flags=re.I).strip()
        if 2<=len(part)<=40 and not re.search(r'职位|岗位|登录|注册|首页|人才|join|login|job|position',part,re.I) and not ROLE.search(part):
            return part
    return ''


def extract_rendered_page(page):
    from recognition import extract_page, extract_text, title_job_code
    url=page['url']
    result=extract_page(page.get('html',''),url)
    fields,evidence,facts=result['fields'],result['evidence'],result['facts']
    text=page.get('text','')[:100000]
    # Rendered dl/grid labels often become separate lines instead of "label: value".
    labels='公司名称|公司|企业名称|招聘公司|岗位名称|职位名称|工作地点|工作城市|岗位编号|职位编号|招聘批次'
    text=re.sub(r'(?m)^\s*('+labels+r')[：:]?\s*\n\s*([^\n]+)',r'\1：\2',text)
    explicit=extract_text(text)
    for key in LIMITS:
        if key in explicit['fields'] and key not in fields:
            fields[key]=explicit['fields'][key];evidence[key]='已加载页面中的明确字段'
    for key,label in [('job_code','岗位编号|职位编号'),('batch','招聘批次')]:
        values=set(re.findall(r'(?m)^(?:'+label+r')\s*[：:]\s*([^\n]+)',text))
        if len(values)==1:
            value=scalar(values.pop(),LIMITS[key])
            if value: fields[key]=value;evidence[key]='已加载页面中的明确字段'

    parsed=urlsplit(url)
    ids=set(unquote(parsed.path).strip('/').split('/'))
    for values in parse_qs(parsed.query).values(): ids.update(values)
    jobs=[];visited=0
    def visit(value,source,depth=0):
        nonlocal visited
        visited+=1
        if depth>12 or visited>6000:return
        if isinstance(value,list):
            for item in value[:200]:visit(item,source,depth+1)
        elif isinstance(value,dict):
            role=first(value,('positionName','jobName','job_title','jobTitle','title','name'))
            description=first(value,('duty','description','jobDescription','job_description','responsibility'),20000)
            identity_keys=('positionId','jobId','job_id','id','requisitionId')
            identities={scalar(value.get(k),100) for k in identity_keys}-{''}
            code=(first(value,('jobCode','code','requisitionId'),100) or title_job_code(role) or
                  first(value,('positionId','jobId','job_id','id'),100))
            if role and ROLE.search(role) and (description or any(k in value for k in ('positionName','jobName','job_title','jobTitle'))):
                item={'role':role,'job_code':code,
                      'company':first(value,('companyName','company_name','employerName'),160),
                      'city':first(value,('workplace','workplaceDesc','workLocation','city','location'),160),
                      'batch':first(value,('jobProjectName','batchName','recruitProjectName'),80)}
                org=value.get('hiringOrganization')
                if isinstance(org,dict):item['company']=first(org,('name',),160) or item['company']
                for city_key in ('city_info','location','workLocation','workLocations'):
                    city=value.get(city_key)
                    if not item['city'] and isinstance(city,dict):item['city']=first(city,('name','city','addressLocality'),160)
                    if not item['city'] and isinstance(city,list) and 0<len(city)<=20:
                        names=[first(place,('name','city','addressLocality'),160) if isinstance(place,dict)
                               else scalar(place,160) for place in city]
                        if all(names):item['city']=scalar(' / '.join(dict.fromkeys(names)),160)
                jobs.append((item,source,bool(identities & ids)))
            for child in value.values():
                if isinstance(child,(dict,list)):visit(child,source,depth+1)
    for response in page.get('responses',[])[:40]:
        visit(response.get('data'),response.get('url',url))
    exact=[job for job in jobs if job[2]]
    candidates=exact or jobs
    unique={json.dumps(item,sort_keys=True):(item,source) for item,source,_ in candidates}
    ambiguous=len(unique)>1
    if len(unique)==1:
        item,source=next(iter(unique.values()))
        # Require an explicit matching ID, or a job title actually visible on this page.
        if exact or item['role'] in text:
            for key,value in item.items():
                if value:
                    fields[key]=value;evidence[key]='页面加载的岗位数据：'+source.split('?')[0][:200]
    headings=list(dict.fromkeys(h.strip() for h in page.get('headings',[]) if scalar(h) and ROLE.search(h)))
    if not headings:
        # Some sites use styled divs for the main title. Look only before the job
        # description, excluding responsibility paragraphs and related-job lists.
        intro=re.split(r'岗位职责|职位描述|岗位描述|工作职责|任职要求|任职资格|Job Description',text,maxsplit=1,flags=re.I)[0]
        headings=list(dict.fromkeys(line.strip() for line in intro.splitlines()[:35]
            if scalar(line,120) and ROLE.search(line) and len(line.strip())>=4))
    if 'role' not in fields and len(headings)==1 and not ambiguous:
        fields['role']=headings[0];evidence['role']='已加载页面的岗位标题'
    if 'company' not in fields:
        company=company_from_title(page.get('title',''),fields.get('role',''))
        if company:fields['company']=company;evidence['company']='招聘网页标题：'+page.get('title','')[:200]
    if ambiguous and not fields.get('role'):
        facts.append({'label':'多个岗位','value':'页面包含多个岗位，请使用具体岗位详情链接，未自动选择其中一项。'})
    if not fields.get('role'):
        if re.search(r'请.*登录|登录后|验证码|访问验证|verify you are|sign in to',text,re.I):
            facts.append({'label':'页面需要验证','value':'已读取页面，但岗位内容需要登录或验证；请打开原网页后粘贴岗位文字。'})
        elif page.get('diagnostics',{}).get('failures'):
            facts.append({'label':'页面未完整加载','value':'部分网页资源读取失败，岗位内容可能还没有显示；请重试，或粘贴岗位正文。'})
        else:
            facts.append({'label':'已读取页面','value':'页面已加载，但暂未找到可确定的单个岗位；可粘贴岗位正文继续识别。'})
    # Browser reads are public job descriptions, never personal application records.
    for key in ('status','applied_on','due_at','next_action'):
        fields.pop(key,None);evidence.pop(key,None)
    for key in list(fields):
        if key in LIMITS and not scalar(fields[key],LIMITS[key]):
            fields.pop(key,None);evidence.pop(key,None)
    if fields.get('city','').lower() in ('团队','职位','工作地点','全部','搜索','登录','team','teams','locations','search'):
        fields.pop('city',None);evidence.pop('city',None)
    result['page_title']=page.get('title','')[:200]
    result['icon_url']=page.get('icon_url','')
    return result
