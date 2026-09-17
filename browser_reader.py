"""Optional isolated Chromium reader. No login profile or model service."""
import importlib.util
import asyncio
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parent
READ_LOCK=threading.BoundedSemaphore(1)


def read_rendered_page(url, initial_document=None):
    from recognition import RecognitionError, validate_public_url
    url,_,_=validate_public_url(url)
    python=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.exists():
        if importlib.util.find_spec('playwright') is None:
            raise RecognitionError('尚未安装浏览器读取组件，请按 README 的“增强网址识别”步骤安装；也可粘贴岗位文字。')
        python=Path(sys.executable)
    if not READ_LOCK.acquire(blocking=False):
        raise RecognitionError('正在读取另一个页面，请稍后重试')
    try:
        env=os.environ.copy()
        if (ROOT/'.browser-runtime').exists():env['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.browser-runtime')
        process=subprocess.Popen([str(python),'-B',str(Path(__file__))],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=ROOT,env=env,start_new_session=os.name!='nt')
        try:
            output,_=process.communicate(json.dumps({'url':url, 'initial_document':initial_document}).encode(),timeout=60)
        except subprocess.TimeoutExpired:
            if os.name!='nt':os.killpg(process.pid,signal.SIGKILL)
            else:process.kill()
            process.communicate()
            raise RecognitionError('页面加载超时；网站可能限制自动读取，请稍后重试或粘贴正文。')
        try:
            result=json.loads(output)
            if result.get('error'):raise RecognitionError(result['error'])
            if not isinstance(result.get('url'),str):raise ValueError()
            return result
        except RecognitionError:
            raise
        except (ValueError,TypeError):
            raise RecognitionError('浏览器读取未能完成，请检查组件安装，或粘贴岗位正文。')
    finally:
        READ_LOCK.release()


async def render_page(url, initial_document=None):
    from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout
    from recognition import fetch_public_page, validate_public_url
    from rendered_extraction import ROLE, extract_rendered_page
    url,_,_=validate_public_url(url)
    responses=[];failures=[];errors=[];address_cache={};size=0;count=0
    pending=set();failed_script=False
    deadline=time.monotonic()+45
    network_slots=asyncio.Semaphore(6)
    async with async_playwright() as playwright:
        browser=await playwright.chromium.launch(headless=True,chromium_sandbox=True)
        try:
            context=await browser.new_context(service_workers='block',accept_downloads=False,
                viewport={'width':1365,'height':900},locale='zh-CN')
            async def close_socket(socket):await socket.close()
            await context.route_web_socket('**/*',close_socket)
            async def route_request(route):
                nonlocal size,count,failed_script
                request=route.request;count+=1
                if time.monotonic()>deadline or count>140 or size>32*1024*1024 or request.resource_type not in ('document','script','xhr','fetch'):
                    await route.abort();return
                pending.add(request)
                try:
                    # Fulfil through pinned public-IP connections: the browser never
                    # resolves/fetches page resources itself, including redirects.
                    if (request.resource_type=='document' and request.url==url
                            and isinstance(initial_document,(str,dict))):
                        document=initial_document if isinstance(initial_document,dict) else {'html':initial_document}
                        response={'body':document['html'].encode(), 'status':200,
                                  'headers':{'content-type':'text/html; charset=utf-8'}}
                        if document.get('set_cookie'):
                            response['headers']['set-cookie']=document['set_cookie']
                    else:
                        headers=dict(request.headers)
                        cookies=await context.cookies(request.url)
                        if cookies:headers['cookie']='; '.join(c['name']+'='+c['value'] for c in cookies)
                        async with network_slots:
                            response=await asyncio.to_thread(fetch_public_page,request.url,resource=True,method=request.method,
                                body=request.post_data_buffer,headers=headers,browser_session=True,
                                deadline=min(deadline,time.monotonic()+(25 if request.resource_type in ('document','script') else 10)),address_cache=address_cache)
                    body=response['body']
                    if size+len(body)>32*1024*1024:
                        await route.abort();return
                    size+=len(body)
                    if request.resource_type in ('xhr','fetch') and len(body)<256*1024 and len(responses)<40:
                        try:
                            data=json.loads(body)
                            if re.search(rb'"(?:positionName|jobName|job_title|jobTitle|JobPosting|title|name)"',body):
                                responses.append({'url':request.url,'method':request.method,'data':data})
                        except (ValueError,UnicodeError):pass
                    await route.fulfill(status=response['status'],headers=response['headers'],body=body)
                except Exception as error:
                    if request.resource_type=='script':failed_script=True
                    if len(failures)<12:failures.append({'url':request.url,'reason':str(error)[:200]})
                    try:await route.abort()
                    except Exception:pass  # Context may have closed at its time limit.
                finally:
                    pending.discard(request)
            await context.route('**/*',route_request)
            page=await context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)[:500]) if len(errors)<8 else None)
            page.set_default_timeout(4000)
            try:await page.goto(url,wait_until='commit',timeout=35000)
            except BrowserTimeout:pass
            # Poll for content, then allow delayed data to settle. Do not require
            # networkidle: tracking/polling requests can continue indefinitely.
            previous='';stable=0
            while time.monotonic()<deadline-1:
                try:
                    text=(await page.locator('body').inner_text(timeout=2000))[:100000]
                except BrowserTimeout:
                    continue
                if failed_script and not pending and len(text.strip())<120:
                    break
                if responses:
                    candidate=extract_rendered_page({'url':page.url, 'title':await page.title(),
                        'text':text, 'responses':responses})
                    if (candidate['fields'].get('company') and
                            candidate['evidence'].get('role','').startswith('页面加载的岗位数据')):
                        break
                has_job_content=bool(re.search(r'岗位职责|职位描述|岗位描述|任职要求|任职资格|岗位要求|工作职责|responsibilities|qualifications|job description',text,re.I))
                if text==previous and len(text)>120 and has_job_content and ROLE.search(text):stable+=1
                else:stable=0
                if stable>=2:break
                previous=text
                await asyncio.sleep(0.5)
            snapshot=await page.evaluate('''() => ({url:location.href,title:document.title,
                html:document.documentElement.outerHTML.slice(0,600000),
                text:(document.body?.innerText||'').slice(0,100000),
                headings:[...document.querySelectorAll('h1,h2,h3,[role="heading"]')].filter(e=>e.getClientRects().length).map(e=>e.innerText.trim()).filter(Boolean).slice(0,60),
                icon_url:document.querySelector('link[rel~="apple-touch-icon"],link[rel~="icon"]')?.href||''})''')
            snapshot['responses']=responses
            snapshot['diagnostics']={'requests':count,'bytes':size,'failures':failures,'errors':errors}
            return snapshot
        finally:
            await browser.close()


if __name__=='__main__':
    try:
        payload=json.load(sys.stdin)
        result=asyncio.run(render_page(payload['url'], initial_document=payload.get('initial_document')))
    except ImportError:
        result={'error':'尚未安装浏览器读取组件，请按 README 的“增强网址识别”步骤安装。'}
    except Exception as error:
        message=str(error)
        result={'error':('浏览器组件尚未就绪，请按 README 安装 Chromium。' if 'Executable doesn' in message else
                         '页面未能加载，可能需要登录、访问验证或网络不可用；可粘贴岗位正文继续识别。')}
    print(json.dumps(result,ensure_ascii=False))
