import {enhanceDates, closeDatePicker} from './dates.mjs';
import {enhanceSelects, closeSelectMenu} from './selects.mjs';
import {STATUSES, INTERVIEWS, COMPANY_TYPES, INDUSTRIES, dayKey, shiftDay, shiftMonth, calendarDate, calendarDays, taskGroups, filterApps, waitingApps, companyKey, groupCompanies, matchingCompanies, attemptLabel} from './model.mjs';

const $ = (s, root=document) => root.querySelector(s);
const escape = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const paths={
  calendar:'M8 3v4m8-4v4M4 10h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Zm3 9h2m4 0h2m-8 3h2',
  table:'M4 4h16v16H4ZM4 9h16M9 9v11M4 14h16',
  archive:'M4 8h16v12H4ZM3 4h18v4H3Zm6 8h6',
  search:'m16 16 5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
  plus:'M12 5v14M5 12h14',
  arrow:'M5 12h14m-5-5 5 5-5 5',
  chevron:'m9 5 7 7-7 7',
  close:'m6 6 12 12M6 18 18 6',
  check:'m5 12 4 4L19 6',
  clock:'M12 8v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  sun:'M12 3V1m0 22v-2M3 12H1m22 0h-2M5.6 5.6 4.2 4.2m15.6 15.6-1.4-1.4M5.6 18.4l-1.4 1.4M19.8 4.2l-1.4 1.4M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0Z',
  heart:'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z',
  coffee:'M4 8h13v7a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V8Zm13 1h2a3 3 0 0 1 0 6h-2M7 2v3m4-3v3m4-3v3M2 23h18',
  compass:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM16 8l-3 5-5 3 3-5 5-3Z',
  leaf:'M19 3C9 3 3 7 5 14c2 7 14 7 14-11ZM5 21c1-7 5-10 9-13',
  harddrive:'M5 4h14l3 11H2L5 4Zm-3 11v5h20v-5M6 18h.01M10 18h.01',
  eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Zm13 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  star:'m12 3 2.8 5.8 6.4.9-4.6 4.5 1.1 6.3-5.7-3-5.7 3 1.1-6.3L3 9.7l6.4-.9L12 3Z',
  edit:'m14 5 5 5M4 20l5-1L21 7l-5-5L4 14v6Z',
  download:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  upload:'M12 16V4m-5 5 5-5 5 5M4 16v5h16v-5',
  external:'M14 3h7v7m0-7L10 14M10 4H4v16h16v-6',
  briefcase:'M8 6V3h8v3M3 6h18v15H3ZM3 11c6 5 12 5 18 0M10 12h4v4h-4Z',
  chat:'M4 4h16v13H9l-5 4V4Zm4 5h8m-8 4h5',
  trophy:'M8 3h8v7a4 4 0 0 1-8 0V3Zm0 2H3v3a5 5 0 0 0 5 5m8-8h5v3a5 5 0 0 1-5 5m-4 1v6m-5 1h10',
  refresh:'M20 7a8 8 0 0 0-14-2L3 8m0-5v5h5m-4 9a8 8 0 0 0 14 2l3-3m0 5v-5h-5',
  shield:'m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6l8-4Zm-4 10 3 3 5-6',
  inbox:'M5 4h14l3 14v3H2v-3L5 4ZM2 15h6l2 3h4l2-3h6',
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.briefcase}"/></svg>`;
document.querySelectorAll('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));
document.querySelectorAll('[data-nav]').forEach(el=>el.setAttribute('aria-label',el.textContent.trim()));
const routeNames={overview:'近期安排',applications:'投递记录',backup:'数据备份'};
const initialRoute=location.hash.slice(1);
const state={apps:[],demo:false,route:routeNames[initialRoute]?initialRoute:'overview',query:'',status:'',priority:false,company_type:'',sort:'newest',day:'',scope:'week',calendarView:'week',calendarMonth:dayKey().slice(0,7),error:''};
let demoApps=[], toastTimer, createdHighlightTimer, formSnapshot='', recognitionPreview=null;
state.createdId='';
state.applicationView='companies';
const expandedCompanies=new Set();
let personalization=null, personalSnapshot='';
const apps=()=>state.demo?demoApps:state.apps;
const findApp=id=>apps().find(a=>a.id===id);
const options=(values,value)=>values.map(s=>`<option value="${escape(s)}" ${s===value?'selected':''}>${escape(s)}</option>`).join('');
function tone(status){return INTERVIEWS.includes(status)?'interview':['测评','笔试'].includes(status)?'assessment':status==='Offer'?'offer':status==='已结束'?'closed':status==='待确认'?'uncertain':['已投递','筛选中'].includes(status)?'active':'';}
const companyTags=app=>app.company_type?`<div class="company-tags"><span class="company-tag nature" title="企业性质">${escape(app.company_type)}</span></div>`:'';
const badge=status=>`<span class="badge ${tone(status)}">${escape(status)}</span>`;
function logo(app, large=false){const n=[...app.company].reduce((sum,c)=>sum+c.codePointAt(0),0)%4;return `<span class="company-logo tone${n}${large?' large':''}" aria-hidden="true">${escape(app.company.slice(0,1).toUpperCase())}</span>`;}
function prettyDate(s, withTime=false){if(!s)return '未定时间'; const day=s.slice(0,10);const base=day===dayKey()?'今天':day===shiftDay(dayKey(),1)?'明天':`${Number(day.slice(5,7))}月${Number(day.slice(8,10))}日`;return base+(withTime&&s.includes('T')?' '+s.slice(11,16):'');}
const isLate=a=>a.due_at&&new Date(a.due_at)<new Date();
const timeLabel=a=>a.due_at ? (a.due_at.slice(0,10)===dayKey()?a.due_at.slice(11,16):`${a.due_at.slice(5,10).replace('-','/')} ${a.due_at.slice(11,16)}`):'未定时间';
function notify(message,error=false){clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').classList.toggle('error',error);$('#toast').hidden=false;toastTimer=setTimeout(()=>$('#toast').hidden=true,4500);}
async function request(path,method='GET',body){
  let response;
  try{response=await fetch(path,{method,headers:{'Content-Type':'application/json','X-Workbench':'1'},body:body===undefined?undefined:JSON.stringify(body)});}
  catch{throw new Error('连接已断开，请重新启动工作台后再试。未保存的输入会保留。');}
  const data=await response.json().catch(()=>({error:'收到异常响应，请重试'}));
  if(!response.ok){const error=new Error(data.error||'操作未完成，请重试');error.duplicates=data.duplicates;throw error;}
  return data;
}
function navigate(route){state.route=route;state.day='';if(location.hash!=='#'+route)history.replaceState(null,'','#'+route);render();}
async function load(){
  try{const [records,personal]=await Promise.all([request('/api/applications'),request('/api/personalization')]);state.apps=records;personalization=personal;state.error='';}
  catch(error){state.error=error.message;}
  render();
}
function acceptApp(app){const i=state.apps.findIndex(a=>a.id===app.id);if(i<0)state.apps.unshift(app);else state.apps[i]=app;render();if($('#drawer').open&&$('#drawer').dataset.id===app.id)renderDrawer(app);$('#saveStatus').textContent='已保存到本机 · '+new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});}
function revealCreatedApplication(id){
  clearTimeout(createdHighlightTimer);
  Object.assign(state,{query:'',status:'',priority:false,company_type:'',sort:'newest',createdId:id});
  $('#globalSearch').value='';$('#drawer').close();navigate('applications');
  document.querySelector(`[data-application-id="${CSS.escape(id)}"]`)?.scrollIntoView({block:'nearest',inline:'nearest'});
  createdHighlightTimer=setTimeout(()=>{
    state.createdId='';
    document.querySelectorAll('.new-record-label').forEach(el=>el.remove());
    document.querySelectorAll('.is-new-record').forEach(el=>el.classList.remove('is-new-record'));
  },8000);
}
async function mutate(path,method,body,message){if(state.demo){notify('示例为只读，返回我的记录后即可操作');return;}
  try{const result=await request(path,method,body);acceptApp(result);notify(message);return result;}
  catch(error){notify(error.message,true);render();}
}
function heading(title,subtitle,aside=''){return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div>${aside}</div>`;}
function empty(title,description,buttons='',symbol='inbox'){return `<div class="empty-state"><div class="empty-icon">${icon(symbol)}</div><h3>${title}</h3><p>${description}</p><div class="empty-actions">${buttons}</div></div>`;}
function render(){
  closeSelectMenu();
  const all=apps();
  $('#seasonLabel').textContent=new Date().getFullYear()+' 秋招季';
  $('#crumb').textContent=routeNames[state.route];
  document.title=routeNames[state.route]+' · 秋招手帖';
  document.querySelectorAll('[data-nav]').forEach(b=>{b.classList.toggle('active',b.dataset.nav===state.route);if(b.dataset.nav===state.route)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  $('#navApps').textContent=all.length||'';
  const pending=all.filter(a=>a.next_action&&a.status!=='已结束').length;
  $('#navTasks').textContent=pending||'';
  $('#demoBanner').hidden=!state.demo;
  $('#demoButton').innerHTML=icon('eye')+`<span>${state.demo?'我的记录':'看看示例'}</span>`;
  $('#demoButton').setAttribute('aria-label',state.demo?'返回我的记录':'看看示例');
  $('#demoButton').classList.toggle('is-preview',state.demo);
  if(state.error&&!state.demo){$('#main').innerHTML=empty('工作台暂时没有连接上',escape(state.error),'<button class="button primary" data-action="refresh">重新连接</button>','refresh');return;}
  $('#main').innerHTML=state.route==='overview'?overview():state.route==='applications'?applications():backup();
  enhanceSelects($('#main'));
}
function monthTitle(month){return `${Number(month.slice(0,4))} 年 ${Number(month.slice(5))} 月`;}
function selectedCalendarDay(){return state.day || (state.calendarMonth===dayKey().slice(0,7)?dayKey():state.calendarMonth+'-01');}
function calendarViewHeader(){return `<div class="panel-head calendar-heading"><h2>我的日程</h2><div class="segmented" aria-label="日历视图">${[['week','近 7 天'],['month','日历']].map(([view,label])=>`<button id="calendar-view-${view}" data-action="calendar-view" data-view="${view}" aria-pressed="${state.calendarView===view}" class="${state.calendarView===view?'active':''}">${label}</button>`).join('')}</div></div>`;}
function calendarJumpForm(day){
  const [year,month,date]=day.split('-').map(Number);
  const last=Number(calendarDate(year,month,31).slice(8));
  const numberedOptions=(n,value,unit)=>Array.from({length:n},(_,i)=>`<option value="${i+1}" ${i+1===value?'selected':''}>${i+1} ${unit}</option>`).join('');
  return `<div class="calendar-jump"><span>跳转日期</span><form id="calendarJumpForm" aria-label="选择年月日"><div class="calendar-year"><button id="calendar-prev-year" type="button" class="calendar-year-step calendar-prev" data-action="calendar-year" data-offset="-1" aria-label="上一年" title="上一年" ${year<=1000?'disabled':''}>${icon('chevron')}</button><label><input id="calendarYear" name="year" type="number" min="1000" max="9998" step="1" value="${year}" required aria-label="输入年份" title="直接输入年份，再点击查看"><span>年</span></label><button id="calendar-next-year" type="button" class="calendar-year-step" data-action="calendar-year" data-offset="1" aria-label="下一年" title="下一年" ${year>=9998?'disabled':''}>${icon('chevron')}</button></div><select id="calendarMonth" name="month" class="compact-select" aria-label="选择月份">${numberedOptions(12,month,'月')}</select><select id="calendarDay" name="day" class="compact-select" aria-label="选择日期">${numberedOptions(last,date,'日')}</select><button class="button small" type="submit">查看</button></form></div>`;
}
function monthCalendar(all){
  const days=calendarDays(all,state.calendarMonth), selected=selectedCalendarDay(), today=dayKey();
  const total=days.filter(d=>d.inMonth).reduce((n,d)=>n+d.items.length,0);
  return `<section class="panel calendar-panel" aria-label="月历">${calendarViewHeader()}
    <div class="calendar-toolbar"><div><h3 id="calendar-month-label" aria-live="polite">${monthTitle(state.calendarMonth)}</h3><p>本月 ${total} 项待办</p></div><div class="calendar-navigation"><button id="calendar-prev" class="icon-button calendar-prev" data-action="calendar-month" data-offset="-1" aria-label="上个月">${icon('chevron')}</button><button id="calendar-today" class="button small" data-action="calendar-today">今天</button><button id="calendar-next" class="icon-button" data-action="calendar-month" data-offset="1" aria-label="下个月">${icon('chevron')}</button></div></div>
    ${calendarJumpForm(selected)}<div class="calendar-weekdays" aria-hidden="true">${['周一','周二','周三','周四','周五','周六','周日'].map(d=>`<span>${d}</span>`).join('')}</div>
    <div class="month-grid" role="group" aria-labelledby="calendar-month-label">${days.map(({day,inMonth,items})=>`<div class="calendar-cell ${inMonth?'':'outside-month'} ${day===selected?'is-selected':''}">
      <button class="calendar-date ${day===today?'is-today':''}" data-action="calendar-day" data-day="${day}" aria-label="${day}，${items.length} 项安排" aria-pressed="${day===selected}" ${day===today?'aria-current="date"':''}><time datetime="${day}">${Number(day.slice(8))}</time>${items.length?`<span class="calendar-day-count">${items.length} 项</span>`:''}</button>
      <div class="calendar-events">${items.slice(0,2).map(a=>`<button class="calendar-event ${tone(a.status)||'active'}" data-action="detail" data-id="${escape(a.id)}" aria-label="${escape(a.due_at.replace('T',' '))}，${escape(a.company)}，${escape(attemptLabel(a,apps()))}，${escape(a.next_action)}" title="${escape(a.due_at.slice(11,16)+' · '+a.company+' · '+attemptLabel(a,apps())+' · '+a.next_action)}"><span class="calendar-event-meta"><time>${escape(a.due_at.slice(11,16))}</time><span>${escape(a.company)}</span></span><span class="calendar-event-title">${escape(attemptLabel(a,apps()))} · ${escape(a.next_action)}</span></button>`).join('')}</div>
      ${items.length>2?`<button class="calendar-more desktop-more" data-action="calendar-day" data-day="${day}" aria-label="查看 ${day} 全部 ${items.length} 项安排">另 ${items.length-2} 项</button>`:''}${items.length>1?`<button class="calendar-more mobile-more" data-action="calendar-day" data-day="${day}" aria-label="查看 ${day} 全部 ${items.length} 项安排">另 ${items.length-1} 项</button>`:''}</div>`).join('')}</div>
    <div class="calendar-footnote"><span>点日期看当天清单，点安排查看投递</span><span>未定时间的待办在下方列出</span></div></section>`;
}
function selectCalendarDay(day, reveal=false){
  state.day=day;state.calendarMonth=day.slice(0,7);render();
  document.querySelector(`.calendar-date[data-day="${day}"]`)?.focus({preventScroll:!reveal});
}
function overview(){
  const all=apps(),groups=taskGroups(all),today=dayKey();
  const count=all.filter(a=>!['待投递','已结束','Offer'].includes(a.status)).length;
  const interviews=all.filter(a=>INTERVIEWS.includes(a.status)).length;
  const stats=[['全部投递',all.length,'briefcase','all'],['进行中',count,'clock','active'],['面试阶段',interviews,'chat','interviews'],['已获 Offer',all.filter(a=>a.status==='Offer').length,'trophy','offer']];
  const dateText=new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'});
  const week=Array.from({length:7},(_,i)=>{const key=shiftDay(today,i),d=new Date(key+'T12:00:00');const n=all.filter(a=>a.next_action&&a.status!=='已结束'&&a.due_at?.slice(0,10)===key).length;return `<button class="day-cell ${i===0?'today':''} ${state.day===key?'selected':''} ${n?'has-events':''}" data-action="day" data-day="${key}" aria-pressed="${state.day===key}" aria-label="${key}，${n} 项安排"><span class="day-name">${i===0?'今天':['周日','周一','周二','周三','周四','周五','周六'][d.getDay()]}</span><span class="day-number">${d.getDate()}</span><span class="day-dot"></span></button>`;}).join('');
  const scheduleDay=state.calendarView==='month'?selectedCalendarDay():state.day;
  let schedule='';
  if(scheduleDay){const items=all.filter(a=>a.next_action&&a.status!=='已结束'&&a.due_at?.slice(0,10)===scheduleDay).sort((a,b)=>a.due_at.localeCompare(b.due_at));schedule=items.length?taskSection('当天待办',items):empty('这一天还没有安排','在投递详情中设置下一步和时间，就会出现在日历里。','<button class="button primary" data-action="new">'+icon('plus')+'新增投递</button>','calendar');}
  else{schedule=taskSection('已逾期',groups.overdue,'overdue')+taskSection('今天',groups.today)+taskSection('未来几天',groups.week)+(state.scope==='all'?taskSection('更晚的安排',groups.later):'')+taskSection('时间待定',groups.unscheduled);}
  if(!schedule)schedule=all.length?empty('近期安排已清空','有新的笔试、面试或待办时，在岗位里添加进展就好。','<button class="button primary" data-action="new">'+icon('plus')+'新增投递</button><button class="button" data-nav="applications">查看投递记录</button>','calendar'):empty('从第一份投递开始','记下公司和岗位，后续的通知、面试和复盘都能接着记录。','<button class="button primary" data-action="new">'+icon('plus')+'新增投递</button><button class="button" data-action="demo">看看示例</button>');
  const recent=all.flatMap(a=>(a.events||[]).map(e=>({...e,app:a}))).sort((a,b)=>b.created_at.localeCompare(a.created_at)).slice(0,5);
  const waiting=waitingApps(all);
  return heading('近期安排',dateText+' · '+(groups.overdue.length?`${groups.overdue.length} 项安排需要处理`:groups.today.length?`今天有 ${groups.today.length} 项安排`:escape(personalization.values.tagline)),`<div class="date-label">${today.replaceAll('-',' / ')}</div>`)+
    `<section class="stats" aria-label="投递概览">${stats.map(([name,n,symbol,filter])=>`<button class="stat" data-action="stat" data-filter="${filter}"><span class="stat-label">${name}</span><span class="stat-number">${n}<em>次</em></span>${name==='全部投递'?`<small class="stat-companies">涉及 ${groupCompanies(all).length} 家公司</small>`:''}${icon(symbol)}</button>`).join('')}</section>
    ${state.calendarView==='month'?monthCalendar(all):''}<div class="overview-grid"><section id="scheduleAgenda" tabindex="-1" class="panel ${state.calendarView==='month'?'calendar-agenda':''}" aria-label="待办清单">${state.calendarView==='month'?`<div class="panel-head"><h2>${new Date(scheduleDay+'T12:00:00').toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'})}</h2><small>${scheduleDay.slice(0,4)}</small></div>`:`${calendarViewHeader()}<div class="week-strip">${week}</div><div class="schedule-toolbar"><span>${state.day?prettyDate(state.day):'待办安排'}${state.day?'<button class="text-button" data-action="clear-day">显示全部</button>':''}</span><div class="segmented" aria-label="安排范围"><button data-action="scope" data-scope="week" class="${state.scope==='week'?'active':''}">未来七天</button><button data-action="scope" data-scope="all" class="${state.scope==='all'?'active':''}">全部安排</button></div></div>`}${schedule}${state.calendarView==='month'?taskSection('时间待定',groups.unscheduled):''}</section>
    <aside class="right-stack"><section class="panel"><div class="panel-head"><h2>最近进展</h2>${icon('clock')}</div>${recent.length?`<div class="recent-list">${recent.map(e=>`<div class="recent-entry"><button data-action="detail" data-id="${escape(e.app.id)}">${escape(e.app.company)} · ${escape(attemptLabel(e.app,apps()))}</button><p>${e.kind==='task'?'完成待办':escape(e.status)}</p><time>${prettyDate(e.occurred_on)}</time></div>`).join('')}</div>`:'<p class="mini-empty">添加进展后，这里会留下每一步的记录。</p>'}</section>
    <section class="panel"><div class="panel-head"><h2>等一份回音</h2><small>14 天未更新</small></div>${waiting.length?`<div class="follow-list">${waiting.slice(0,5).map(a=>`<div class="follow-row"><button data-action="detail" data-id="${escape(a.id)}">${escape(a.company)}<small>${escape(attemptLabel(a,apps()))}</small></button><span class="follow-days">${Math.floor((Date.now()-new Date(a.updated_at))/86400000)} 天</span></div>`).join('')}</div>`:'<p class="mini-empty">暂时没有长时间未更新的投递。<br>收到回复，再记一笔。</p>'}</section><div class="note-block personal-note"><button class="icon-button note-edit" data-action="personalize" aria-label="编辑寄语与图标" title="编辑寄语与图标">${icon('edit')}</button><strong>${icon(personalization.values.icon)}${escape(personalization.values.title)}</strong><div class="personal-note-body">${escape(personalization.values.body)}</div></div></aside></div>`;
}
function taskSection(label,list,extra=''){return list.length?`<section class="task-group"><div class="group-label ${extra}">${label}<span class="count">${list.length}</span></div>${list.map(a=>`<div class="task-row"><button class="complete-button" data-action="complete" data-id="${escape(a.id)}" aria-label="完成：${escape(a.next_action)}" ${state.demo?'disabled':''}>${icon('check')}</button><button class="task-info" data-action="detail" data-id="${escape(a.id)}"><strong>${escape(a.next_action)}</strong><small>${escape(a.company)} · ${escape(attemptLabel(a,apps()))}</small></button><div class="task-meta"><time class="task-time ${isLate(a)?'late':''}">${timeLabel(a)}</time>${badge(a.status)}</div><button class="icon-button task-edit" data-action="event" data-id="${escape(a.id)}" aria-label="更新${escape(a.company)}的进展">${icon('chevron')}</button></div>`).join('')}</section>`:'';}
function applicationTable(records,inGroup=false){return `<div class="table-scroll"><table><thead><tr><th scope="col">${inGroup?'岗位 / 批次':'公司 / 岗位'}</th><th scope="col">当前阶段</th><th scope="col">城市</th><th scope="col">投递入口</th><th scope="col">下一步</th><th scope="col">投递日期</th><th scope="col">操作</th></tr></thead><tbody>${records.map(a=>`<tr data-application-id="${escape(a.id)}" class="${state.createdId===a.id?'is-new-record':''}"><td class="identity-cell"><div class="company-cell">${logo(a)}<div><button class="company-name" data-action="detail" data-id="${escape(a.id)}">${escape(inGroup?a.role:a.company)}</button>${state.createdId===a.id?'<span class="new-record-label">刚刚新增</span>':''}<small>${escape(inGroup?(attemptLabel(a,apps()).slice(a.role.length).replace(/^ · /,'')||a.applied_on):attemptLabel(a,apps()))}</small>${inGroup?'':companyTags(a)}</div></div></td><td class="stage-cell"><select class="badge status-select ${tone(a.status)}" data-status-id="${escape(a.id)}" aria-label="${escape(a.company)} ${escape(attemptLabel(a,apps()))}的当前阶段" ${state.demo?'disabled':''}>${options(STATUSES,a.status)}</select></td><td class="cell-muted city-cell" data-label="城市">${escape(a.city)||'未填写'}</td><td class="link-cell" data-label="投递入口">${applicationLink(a)}</td><td class="table-next" data-label="下一步">${a.next_action?`<strong>${escape(a.next_action)}</strong><small class="${isLate(a)?'overdue':''}">${prettyDate(a.due_at,true)}</small>`:`<button class="text-button" data-action="event" data-id="${escape(a.id)}">${state.demo?'查看进展':'+ 添加下一步'}</button>`}</td><td class="cell-muted applied-cell" data-label="投递日期">${escape(a.applied_on).replaceAll('-','/')}</td><td class="actions-cell"><div class="row-actions"><button class="icon-button priority-button ${a.priority==='重点关注'?'starred':''}" data-action="star" data-id="${escape(a.id)}" aria-label="${a.priority==='重点关注'?'取消重点关注':'重点关注'}${escape(a.company)}" aria-pressed="${a.priority==='重点关注'}" ${state.demo?'disabled':''}>${icon('star')}</button><button class="icon-button" data-action="detail" data-id="${escape(a.id)}" aria-label="查看${escape(a.company)} ${escape(attemptLabel(a,apps()))}">${icon('chevron')}</button></div></td></tr>`).join('')}</tbody></table></div>`;}
function companyAttemptList(records, company){
  return `<ul class="company-attempts" aria-label="${escape(company)}的投递">${records.map(a=>{
    const label=attemptLabel(a,apps()), batch=label.slice(a.role.length).replace(/^ · /,'');
    return `<li class="attempt-row ${state.createdId===a.id?'is-new-record':''}" data-application-id="${escape(a.id)}">
      <div class="attempt-identity"><div class="attempt-title"><button class="company-name" data-action="detail" data-id="${escape(a.id)}">${escape(a.role)}</button>${a.batch&&batch?`<span class="attempt-batch">${escape(batch)}</span>`:''}${state.createdId===a.id?'<span class="new-record-label">刚刚新增</span>':''}</div>
        <div class="attempt-meta">${a.city?`<span>${escape(a.city)}</span>`:''}<span>${escape(a.applied_on).replaceAll('-','/')} 投递</span>${a.job_code?`<span>编号 ${escape(a.job_code)}</span>`:''}${!a.batch&&batch&&batch!==a.applied_on?`<span>${escape(batch)}</span>`:''}${a.url||!state.demo?`<span class="attempt-link">${applicationLink(a)}</span>`:''}</div>
      </div>
      <div class="attempt-stage"><select class="badge status-select ${tone(a.status)}" data-status-id="${escape(a.id)}" aria-label="${escape(a.company)} ${escape(label)}的当前阶段" ${state.demo?'disabled':''}>${options(STATUSES,a.status)}</select></div>
      <div class="attempt-next">${a.next_action?`<button class="attempt-task" data-action="event" data-id="${escape(a.id)}" aria-label="${state.demo?'查看':'更新'}${escape(a.company)} ${escape(label)}的下一步"><span>${escape(a.next_action)}</span><small class="${isLate(a)?'overdue':''}">${icon('calendar')}${prettyDate(a.due_at,true)}${isLate(a)?' · 已逾期':''}</small></button>`:`<button class="text-button" data-action="event" data-id="${escape(a.id)}">${state.demo?'查看进展':'+ 添加下一步'}</button>`}</div>
      <div class="row-actions attempt-actions"><button class="icon-button priority-button ${a.priority==='重点关注'?'starred':''}" data-action="star" data-id="${escape(a.id)}" aria-label="${a.priority==='重点关注'?'取消重点关注':'重点关注'}${escape(a.company)} ${escape(label)}" aria-pressed="${a.priority==='重点关注'}" ${state.demo?'disabled':''}>${icon('star')}</button><button class="attempt-detail" data-action="detail" data-id="${escape(a.id)}" aria-label="查看${escape(a.company)} ${escape(label)}"><span>详情</span>${icon('chevron')}</button></div>
    </li>`;
  }).join('')}</ul>`;
}
function companyGroupsView(records){
  const totals=new Map(groupCompanies(apps()).map(g=>[g.key,g.items.length]));
  return `<div class="company-groups">${groupCompanies(records).map((group,index)=>{
    const open=expandedCompanies.has(group.key), first=group.items[0];
    const pending=group.items.filter(a=>a.next_action&&a.due_at&&a.status!=='已结束').sort((a,b)=>a.due_at.localeCompare(b.due_at))[0];
    const size=totals.get(group.key), count=size===group.items.length?`${size} 次投递`:`匹配 ${group.items.length} / ${size} 次投递`;
    return `<section class="company-group ${open?'is-expanded':''}" aria-label="${escape(group.company)}"><div class="company-group-head"><button class="company-group-toggle" data-action="toggle-company" data-key="${escape(group.key)}" aria-expanded="${open}" aria-controls="company-items-${index}"><span class="group-chevron ${open?'expanded':''}">${icon('chevron')}</span>${logo(first)}<span class="company-group-identity"><strong>${escape(group.company)}</strong><small>${count} · ${group.active} 项进行中</small></span></button><button class="button small company-add" data-action="${state.demo?'new':'company-new'}" data-id="${escape(first.id)}">${icon('plus')}${state.demo?'记录我的投递':'添加投递'}</button></div>${pending&&!open?`<button class="company-next" data-action="detail" data-id="${escape(pending.id)}">${icon('calendar')}<span>${isLate(pending)?'逾期待办':'最近安排'}：${prettyDate(pending.due_at,true)} · ${escape(attemptLabel(pending,apps()))} · ${escape(pending.next_action)}</span></button>`:''}<div id="company-items-${index}" ${open?'':'hidden'}>${open?companyAttemptList(group.items,group.company):''}</div></section>`;
  }).join('')}</div>`;
}
function applications(){
  let filtered=filterApps(apps(),{query:state.query,status:state.status==='面试阶段'?'':state.status,priority:state.priority,sort:state.sort,company_type:state.company_type});
  if(state.status==='面试阶段')filtered=filtered.filter(a=>INTERVIEWS.includes(a.status));
  const tabs=[['','全部'],['进行中','进行中'],['面试阶段','面试'],['Offer','Offer'],['已结束','已结束']];
  const selectStatus=tabs.some(([key])=>state.status===key)?'':state.status;
  return heading('投递记录',`投递 ${apps().length} 次 · 涉及 ${groupCompanies(apps()).length} 家公司`,`<button class="button" data-action="refresh">${icon('refresh')}刷新</button>`)+
    (state.query?`<div class="search-summary">搜索“${escape(state.query)}”<button class="text-button" data-action="clear-search">清除搜索</button></div>`:'')+
    `<section class="panel table-panel"><div class="table-toolbar"><div class="filter-tabs" aria-label="筛选阶段">${tabs.map(([key,name])=>`<button class="filter-tab ${state.status===key?'active':''}" data-action="filter" data-filter="${key}" aria-pressed="${state.status===key}">${name}</button>`).join('')}</div><div class="filter-tools"><button class="star-filter ${state.priority?'active':''}" data-action="priority-filter" aria-pressed="${state.priority}">${icon('star')}重点关注</button><select id="stageFilter" class="compact-select" aria-label="按具体阶段筛选"><option value="">具体阶段</option>${options(STATUSES,selectStatus)}</select><select id="sortSelect" class="compact-select" aria-label="排序方式">${[['newest','最近投递'],['due','安排时间'],['company','公司名称']].map(([value,name])=>`<option value="${value}" ${state.sort===value?'selected':''}>${name}</option>`).join('')}</select></div></div>
    ${classificationFilters()}<div class="application-view-bar"><span>${state.applicationView==='companies'?'同公司收在一起，每次投递独立跟进':'所有投递，逐条查看'}</span><div class="application-view-actions">${state.applicationView==='companies'&&filtered.length?`<button class="text-button collapse-companies" data-action="collapse-companies" aria-disabled="${!expandedCompanies.size}">全部收起</button>`:''}<div class="segmented" aria-label="投递展示方式">${[['companies','按公司'],['flat','按投递']].map(([view,label])=>`<button data-action="application-view" data-view="${view}" class="${state.applicationView===view?'active':''}" aria-pressed="${state.applicationView===view}">${label}</button>`).join('')}</div></div></div>${filtered.length?(state.applicationView==='companies'?companyGroupsView(filtered):applicationTable(filtered)):apps().length?empty('没有找到符合条件的投递','试试其他关键词，或者清除筛选条件。','<button class="button" data-action="reset-filters">清除筛选</button>','search'):empty('第一份投递，从这里记起','只需公司和岗位，其他信息可以之后补充。','<button class="button primary" data-action="new">'+icon('plus')+'新增投递</button>')}
    <div class="table-footer"><span>显示 ${filtered.length} / ${apps().length} 份投递</span><span>点击岗位查看详情 · 每次投递独立记录进展</span></div></section>`;
}
function backup(){return heading('数据备份','你的记录，由你保管。随时导出，安心保存。')+`<div class="backup-grid"><section class="panel backup-card">${icon('download')}<h2>导出我的记录</h2><p>完整备份包含岗位信息和所有进展；表格适合查看、整理，或分享给别人。</p><button class="button primary" data-action="export-json">${icon('download')}完整备份 JSON</button><button class="button" data-action="export-csv">导出表格 CSV</button><p class="field-hint">当前有 ${state.apps.length} 份真实投递记录。CSV 不包含完整时间线。</p></section><section class="panel backup-card">${icon('upload')}<h2>从备份恢复</h2><p>选择本工作台导出的 JSON 文件。只补充缺少的投递；新版备份按记录编号去重，保留同岗位的多次投递；旧版备份沿用公司与岗位去重；个性化设置仅在本机尚未设置时恢复。</p><button class="button" data-action="import">${icon('upload')}选择备份文件</button><p class="field-hint">导入前会自动备份当前数据。</p></section></div><section class="storage-info"><h2>本地保存，随时带走</h2><div class="info-line">${icon('harddrive')}<div><p>记录保存在应用文件夹里的 <code>data/workbench.sqlite3</code>。关闭页面后数据仍然保留。</p></div></div><div class="info-line">${icon('shield')}<div><p>每天首次启动时生成一次快照；导入和删除前也会备份，存放在 <code>data/backups/</code>。</p><p>建议偶尔下载完整备份，另外存一份。更换电脑时，可在新的工作台里导入。</p></div></div><div class="info-line">${icon('clock')}<div><p>当前版本的安排展示在页面内。关闭工作台后，不会发送系统通知。</p></div></div></section>`;}
function applicationLink(app, detail=false){
  if(!app.url){
    if(state.demo)return '<span class="cell-muted">未附链接</span>';
    return `<button class="${detail?'website-card missing':'application-link missing'}" data-action="link" data-id="${escape(app.id)}">${icon('plus')}<span>补充投递链接${detail?'<small>保存官网或岗位页面，之后直接打开</small>':''}</span></button>`;
  }
  let domain='';
  try{domain=new URL(app.url).hostname.replace(/^www\./,'');}catch{return '';}
  return `<a class="${detail?'website-card':'application-link'}" href="${escape(app.url)}" target="_blank" rel="noopener noreferrer" title="${escape(app.url)}" aria-label="打开${escape(app.company)}的投递链接（新标签页）">${detail?icon('external'):''}<span>${state.demo?'示例投递页':'打开投递页'}<small>${escape(domain)}</small></span>${icon(detail?'arrow':'external')}</a>`;
}
function renderDrawer(app){
  const d=$('#drawer'),scroll=d.scrollTop;
  d.dataset.id=app.id;
  const events=[...(app.events||[])].sort((a,b)=>b.occurred_on.localeCompare(a.occurred_on)||b.created_at.localeCompare(a.created_at));
  d.innerHTML=`<div class="drawer-top"><span>投递详情${state.demo?' · 示例':''}</span><button class="icon-button" data-action="close-drawer" aria-label="关闭详情">${icon('close')}</button></div><div class="drawer-body"><div class="detail-identity">${logo(app,true)}<div><h2 id="drawerTitle">${escape(app.company)}</h2><p>${escape(attemptLabel(app,apps()))}</p></div></div><div class="detail-badges">${badge(app.status)}${app.priority==='重点关注'?'<span class="badge assessment">'+icon('star')+'重点关注</span>':''}${app.city?'<span class="badge">'+escape(app.city)+'</span>':''}</div><div class="detail-actions">${state.demo?'<button class="button primary" data-action="new">创建我的投递</button>':`<button class="button primary" data-action="event" data-id="${escape(app.id)}">${icon('plus')}添加进展</button><button class="button" data-action="edit" data-id="${escape(app.id)}">${icon('edit')}编辑信息</button>`}</div><div class="detail-website">${applicationLink(app,true)}</div>
    ${app.next_action?`<section class="next-box"><div class="next-box-head"><span>下一步</span>${icon('calendar')}</div><h3>${escape(app.next_action)}</h3><p>${prettyDate(app.due_at,true)}${isLate(app)?' · 已逾期':''}</p>${state.demo?'':`<button class="button small" data-action="complete" data-id="${escape(app.id)}">${icon('check')}标记完成</button>`}</section>`:''}
    <dl class="details-grid">${[['岗位编号',app.job_code],['企业性质',app.company_type],['批次',app.batch],['投递日期',app.applied_on],['投递渠道',app.channel],['简历版本',app.resume],['城市',app.city]].map(([k,v])=>`<div><dt>${k}</dt><dd>${escape(v)||'未填写'}</dd></div>`).join('')}</dl>${app.note?`<section class="detail-section"><h3>岗位备注</h3><p class="detail-note">${escape(app.note)}</p></section>`:''}
    <section class="detail-section"><h3>进展时间线 <span class="muted">${events.length} 条</span></h3><div class="timeline">${events.map(e=>`<article class="timeline-entry"><header><span>${e.kind==='task'?'完成待办':escape(e.status)}</span><time>${escape(e.occurred_on)}</time></header><p>${escape(e.note)}</p></article>`).join('')}</div></section>${state.demo?'':`<button class="delete-link" data-action="delete" data-id="${escape(app.id)}">删除这份投递</button>`}</div>`;
  d.scrollTop=scroll;
}
function openDetail(id){const app=findApp(id);if(!app)return;renderDrawer(app);if(!$('#drawer').open){$('#drawer').showModal();$('#drawer').scrollTop=0;}}
function field(name,label,value='',type='text',placeholder='',full=false,required=false){return `<div class="field ${full?'full':''}"><label for="f-${name}">${label}${required?'':'<small>选填</small>'}</label><input id="f-${name}" name="${name}" type="${type}" value="${escape(value)}" placeholder="${escape(placeholder)}" ${required?'required':''} ${['date','datetime-local'].includes(type)?'min="1900-01-01" max="9999-12-31'+(type==='datetime-local'?'T23:59':'')+'"':''} maxlength="${name==='company'?160:name==='role'?200:name==='batch'?80:name==='job_code'?100:2000}"></div>`;}
function recognitionFields(url=''){
  return `<section class="recognition-entry"><div class="field"><label for="f-url">投递链接 <small>选填</small></label><div class="recognition-url"><input id="f-url" name="url" type="url" value="${escape(url)}" placeholder="粘贴岗位网址，试试自动识别" maxlength="2000"><button class="button soft" type="button" data-action="recognize-url">识别网址</button></div></div><details class="recognition-fallback"><summary>需要登录的页面？粘贴文字识别</summary><label class="field" for="recognitionText">复制岗位详情或投递通知<textarea id="recognitionText" name="recognition_text" maxlength="100000" placeholder="公司：…&#10;岗位：…&#10;当前进度：…&#10;笔试时间：2026-09-18 14:30"></textarea></label><button class="button small" type="button" data-action="recognize-text">识别文字</button></details><div id="recognitionResult" class="recognition-result" aria-live="polite" hidden></div></section>`;
}
const recognitionLabels={company_type:'企业性质',company:'公司',role:'岗位',city:'城市',applied_on:'实际投递日期',status:'当前进度',next_action:'下一步',due_at:'安排时间'};
async function recognizeInput(kind){
  const form=$('#recordForm'),editor=$('#editor'),resultBox=$('#recognitionResult');
  if(!form||editor.dataset.recognizing==='true')return;
  const payload={};
  if(kind==='url'){
    const raw=form.elements.url.value.trim();
    if(!raw){notify('请先粘贴岗位网址');form.elements.url.focus();return;}
    payload.url=raw.includes('://')?raw:'https://'+raw;
    form.elements.url.value=payload.url;
    if(!form.elements.url.checkValidity()){form.elements.url.reportValidity();return;}
  }else{
    payload.text=$('#recognitionText').value.trim();
    if(!payload.text){notify('请先粘贴岗位或通知文字');$('#recognitionText').focus();return;}
  }
  editor.dataset.recognizing='true';recognitionPreview=null;
  resultBox.hidden=false;resultBox.innerHTML='<p>正在识别，请稍候…</p>';
  const controls=[...form.querySelectorAll('[data-action^="recognize-"],button[type="submit"]')];
  controls.forEach(b=>b.disabled=true);
  try{
    const result=await request('/api/recognize','POST',payload);
    if($('#recordForm')!==form||!editor.open)return;
    if(kind==='url'&&form.elements.url.value!==payload.url){resultBox.innerHTML='<p>网址已修改，请重新识别当前网址。</p>';return;}
    const inferredStatus=!result.fields.status;
    if(inferredStatus&&editor.dataset.mode==='new'&&Object.keys(result.fields).some(key=>recognitionLabels[key])){result.fields.status='待确认';result.evidence.status='未识别到个人进度，作为待核对建议';}
    recognitionPreview=result;
    const entries=Object.entries(result.fields).filter(([key])=>recognitionLabels[key]);
    const rows=entries.map(([key,value])=>{
      const current=form.elements[key]?.value||'';
      const autoCheck=!current||(editor.dataset.mode==='new'&&['status','applied_on'].includes(key)&&form.elements[key]?.dataset.touched!=='true');
      return `<label class="recognition-row"><input type="checkbox" data-recognition-key="${key}" ${autoCheck?'checked':''}><span><strong>${recognitionLabels[key]}</strong><span>${escape(value).replace('T',' ')}</span><small>${escape(result.evidence[key]||'请核对')}</small>${current&&current!==value?`<small>当前填写：${escape(current)}</small>`:''}</span></label>`;
    }).join('');
    resultBox.innerHTML=`<h3>${entries.length?'识别到 '+entries.length+' 项信息':'这个页面没有可确定的信息'}</h3>${rows}${(result.facts||[]).map(f=>`<p class="recognition-fact">${escape(f.label)}：${escape(f.value)}</p>`).join('')}<p class="recognition-hint">${inferredStatus?'未识别到明确进度，请核对建议。 ':''}${!result.fields.applied_on?'实际投递日期未识别，请核对表单中的日期。 ':''}招聘发布日期不会当作投递日期。</p>${entries.length?'<button class="button small primary" type="button" data-action="apply-recognition">填入勾选信息</button>':'<p class="recognition-hint">可以展开上方“粘贴文字识别”，或直接手动填写。</p>'}`;
  }catch(error){
    if($('#recordForm')===form){resultBox.innerHTML=`<p class="recognition-error">${escape(error.message)}</p>`;const fallback=$('.recognition-fallback',form);fallback.open=true;}
  }finally{
    if($('#recordForm')===form){editor.dataset.recognizing='false';controls.forEach(b=>b.disabled=false);}
  }
}
function applyRecognition(){
  if(!recognitionPreview)return;
  const form=$('#recordForm');let filled=0;
  document.querySelectorAll('[data-recognition-key]:checked').forEach(check=>{
    const key=check.dataset.recognitionKey,control=form.elements[key];
    if(control){control.value=recognitionPreview.fields[key];const section=control.closest('details');if(section)section.open=true;filled++;}
  });
  if(!filled){notify('先勾选需要填入的信息');return;}
  enhanceSelects(form);enhanceDates(form);refreshCompanyHints();refreshRepeatNotice();
  $('#recognitionResult').innerHTML='<p>已填入 '+filled+' 项。核对后点击下方“保存投递”或“保存修改”。</p>';
  recognitionPreview=null;notify('已填入表单，尚未保存');
}
function companyTypeField(app){return `<div class="field"><label for="f-company_type">企业性质<small>选填</small></label><select id="f-company_type" name="company_type"><option value="">未填写 · 待确认</option>${options(COMPANY_TYPES,app.company_type)}</select></div>`;}
function classificationFilters(){return `<div class="classification-filters"><span>企业性质</span><label for="companyTypeFilter" class="sr-only">按企业性质筛选</label><select id="companyTypeFilter" class="compact-select"><option value="">全部性质</option>${options(['央国企',...COMPANY_TYPES,'未填写'],state.company_type)}</select>${state.company_type?'<button type="button" class="text-button" data-action="clear-classification">清除筛选</button>':''}</div>`;}
function stageField(status){return `<div class="field"><label for="f-status">当前阶段</label><select id="f-status" name="status">${options(STATUSES,status)}</select></div>`;}
function notesField(label,value='',name='note'){return `<div class="field full"><label for="f-${name}">${label}<small>选填</small></label><textarea id="f-${name}" name="${name}" maxlength="20000" placeholder="记下通知内容、面试题目，或需要准备的事情…">${escape(value)}</textarea></div>`;}
function companyInputField(app){return `<div class="field company-input"><label for="f-company">公司</label><input id="f-company" name="company" value="${escape(app.company)}" placeholder="输入公司名称，自动查找已有公司" maxlength="160" required autocomplete="off" aria-describedby="companyMatchHint"><div id="companySuggestions" class="company-suggestions" aria-label="已有公司建议" hidden></div><small id="companyMatchHint" class="muted"></small></div>`;}
function refreshCompanyHints(){
  const form=$('#recordForm');if(!form?.elements.company)return;
  const query=form.elements.company.value, matches=matchingCompanies(state.apps,query), exact=matches.find(g=>g.key===companyKey(query));
  const list=$('#companySuggestions');
  list.innerHTML=matches.map(g=>`<button type="button" data-action="choose-company" data-id="${escape(g.items[0].id)}"><span>${escape(g.company)}</span><small>已有 ${g.items.length} 次投递${g===exact?' · 自动归入':''}</small></button>`).join('');
  list.hidden=!matches.length||document.activeElement!==form.elements.company;
  $('#companyMatchHint').textContent=!query.trim()?'':exact?`保存后归入「${exact.company}」`:'新公司将自动建立分组；也可从建议中选择已有公司。';
  if(exact&&$('#editor').dataset.mode==='new'&&!form.elements.company_type.dataset.touched&&!form.elements.company_type.value){
    form.elements.company_type.value=exact.items.find(a=>a.company_type)?.company_type||'';
    enhanceSelects(form);
  }
}
function refreshRepeatNotice(serverMatches){
  const form=$('#recordForm'),box=$('#repeatNotice');if(!box||$('#editor').dataset.mode!=='new')return;
  const matches=serverMatches||state.apps.filter(a=>companyKey(a.company)===companyKey(form.elements.company.value)&&companyKey(a.role)===companyKey(form.elements.role.value));
  box.hidden=!matches.length;
  box.innerHTML=matches.length?`<strong>这个岗位已有 ${matches.length} 次投递</strong><p>继续原流程可以更新已有投递；新批次或重新投递，请勾选下方选项。</p><div class="repeat-existing">${matches.map(a=>`<button type="button" class="text-button" data-action="update-existing" data-id="${escape(a.id)}">更新已有投递 · ${escape(a.batch||a.applied_on)} · ${escape(a.status)}</button>`).join('')}</div><label class="checkbox-label"><input type="checkbox" name="allow_repeat">仍然新增一次投递，进度单独记录</label>`:'';
}
document.addEventListener('input',event=>{
  if(event.target.form?.id!=='recordForm')return;
  if(event.target.name==='company'){refreshCompanyHints();refreshRepeatNotice();}
  if(event.target.name==='role')refreshRepeatNotice();
});
document.addEventListener('focusin',event=>{if(event.target.id==='f-company')refreshCompanyHints();});
document.addEventListener('click',event=>{if(!event.target.closest('.company-input'))$('#companySuggestions')?.setAttribute('hidden','');});
document.addEventListener('keydown',event=>{const list=$('#companySuggestions');if(event.key==='Escape'&&list&&!list.hidden){list.hidden=true;event.preventDefault();}});
function openEditor(mode,id,prefill={}){
  if(state.demo&&mode!=='new'){openDetail(id);return;}
  if(mode==='new'&&state.demo){state.demo=false;$('#drawer').close();render();}
  const app=id?findApp(id):prefill;if(id&&!app)return;
  closeDatePicker();
  const editor=$('#editor');editor.dataset.mode=mode;editor.dataset.saving='false';editor.dataset.id=id||'';editor.dataset.recognizing='false';recognitionPreview=null;
  const title=mode==='new'?'新增投递':mode==='edit'?'编辑岗位信息':'添加进展';
  const description=mode==='new'?'先记下公司和岗位，其他信息可以慢慢补。':escape(app.company)+' · '+escape(attemptLabel(app,apps()));
  let fields;
  if(mode==='event')fields=`<div class="form-grid">${stageField(app.status)}${field('occurred_on','发生日期',dayKey(),'date','',false,true)}${notesField('这次有什么进展？')}${field('next_action','下一步',app.next_action,'text','例如：准备二面、完成测评',true)}${field('due_at','安排时间',app.due_at,'datetime-local','',true)}<p class="field-hint field full">原有待办会保留；完成后可在详情中勾选，也可以在这里修改或清空。</p></div>`;
  else fields=`${recognitionFields(app.url)}<div class="form-grid">${companyInputField(app)}${field('role','岗位',app.role,'text','例如：算法工程师',false,true)}${field('job_code','岗位编号',app.job_code,'text','例如：J2026001 / 001-AI')}${field('batch','批次 / 备注标签',app.batch,'text','例如：提前批、正式批、2027 春招')}<div id="repeatNotice" class="repeat-notice field full" hidden></div>${stageField(app.status||'已投递')}${field('applied_on','投递日期',app.applied_on||dayKey(),'date','',false,true)}${field('next_action','下一步',app.next_action,'text','例如：完成测评、等待面试通知',true)}${field('due_at','安排时间',app.due_at,'datetime-local','',true)}</div><details class="optional-fields" ${mode==='edit'?'open':''}><summary>更多信息 · 企业性质、城市与备注</summary><div class="form-grid">${companyTypeField(app)}${field('city','城市',app.city,'text','例如：北京 / 上海')}${field('channel','投递渠道',app.channel,'text','例如：官网 / 内推')}${field('resume','使用的简历',app.resume,'text','例如：算法岗 v3')}${notesField('岗位备注',app.note)}</div></details>`;
  editor.innerHTML=`<form id="recordForm"><div class="dialog-heading"><div><h2 id="editorTitle">${title}</h2><p>${description}</p></div><button type="button" class="icon-button" data-action="close-editor" aria-label="关闭编辑">${icon('close')}</button></div><div class="form-content">${fields}<p id="formError" class="form-error" role="alert" hidden></p></div><div class="dialog-footer">${mode!=='event'?`<label class="checkbox-label"><input type="checkbox" name="priority" ${app.priority==='重点关注'?'checked':''}>重点关注</label>`:''}<div class="actions"><button type="button" class="button" data-action="close-editor">取消</button><button class="button primary" type="submit">${mode==='new'?'保存投递':mode==='event'?'保存进展':'保存修改'}</button></div></div></form>`;
  enhanceSelects(editor);enhanceDates(editor);refreshCompanyHints();refreshRepeatNotice();
  formSnapshot=JSON.stringify([...new FormData($('#recordForm'))]);
  if(!editor.open)editor.showModal();editor.scrollTop=0;
}
function confirmBox(title,message,label='确认',danger=false){
  const d=$('#confirmDialog');d.returnValue='';
  d.innerHTML=`<h2 id="confirmTitle">${escape(title)}</h2><p>${escape(message)}</p><div class="actions"><button class="button" data-action="confirm-no" autofocus>取消</button><button class="button ${danger?'danger':'primary'}" data-action="confirm-yes">${escape(label)}</button></div>`;
  return new Promise(resolve=>{d.onclose=()=>resolve(d.returnValue==='yes');d.showModal();});
}
async function closeEditor(){
  if($('#editor').dataset.saving==='true')return;
  const changed=JSON.stringify([...new FormData($('#recordForm'))])!==formSnapshot;
  if(changed&&!await confirmBox('放弃未保存的内容？','这次输入还没有保存。','放弃修改',true))return;
  $('#editor').close();
}
document.addEventListener('submit',async event=>{
  if(event.target.id!=='recordForm')return;event.preventDefault();
  if($('#editor').dataset.saving==='true')return;
  if($('#editor').dataset.recognizing==='true'){notify('识别完成后再保存');return;}
  const form=event.target,ed=$('#editor'),mode=ed.dataset.mode,id=ed.dataset.id,data=Object.fromEntries(new FormData(form));
  if(mode==='new')data.allow_repeat=form.elements.allow_repeat?.checked===true;
  if(mode!=='event')data.priority=form.elements.priority.checked?'重点关注':'普通';
  const err=$('#formError');err.hidden=true;
  if(data.due_at&&!data.next_action.trim()&&data.status!=='已结束'){err.textContent='设置时间时，请填写下一步要做什么。';err.hidden=false;form.elements.next_action.focus();return;}
  if(data.status==='已结束'){data.next_action='';data.due_at='';}
  const button=$('button[type=submit]',form),original=button.textContent;button.disabled=true;button.textContent='保存中…';ed.dataset.saving='true';
  try{
    const result=await request(mode==='new'?'/api/applications':`/api/applications/${encodeURIComponent(id)}${mode==='event'?'/events':''}`,mode==='edit'?'PATCH':'POST',data);
    acceptApp(result);ed.close();notify(mode==='new'?'投递已记录':mode==='event'?'进展已保存':'信息已更新');
    if(mode==='new')revealCreatedApplication(result.id);
  }catch(error){if(error.duplicates)refreshRepeatNotice(error.duplicates);err.textContent=error.message;err.hidden=false;err.scrollIntoView({block:'nearest'});}
  finally{button.disabled=false;button.textContent=original;ed.dataset.saving='false';}
});
document.addEventListener('click',async event=>{
  const nav=event.target.closest('[data-nav]');if(nav){navigate(nav.dataset.nav);return;}
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
  const {action,id}=button.dataset;
  if(action==='application-view'){state.applicationView=button.dataset.view;render();return;}
  if(action==='collapse-companies'){
    expandedCompanies.clear();render();document.querySelector('[data-action="collapse-companies"]')?.focus({preventScroll:true});return;
  }
  if(action==='toggle-company'){
    const key=button.dataset.key;if(expandedCompanies.has(key))expandedCompanies.delete(key);else expandedCompanies.add(key);
    render();[...document.querySelectorAll('[data-action="toggle-company"]')].find(b=>b.dataset.key===key)?.focus({preventScroll:true});return;
  }
  if(action==='company-new'){const source=findApp(id);openEditor('new',null,{company:source.company,company_type:source.company_type});return;}
  if(action==='choose-company'){
    const source=state.apps.find(a=>a.id===id),form=$('#recordForm');if(!source)return;
    form.elements.company.value=source.company;
    if(!form.elements.company_type.dataset.touched)form.elements.company_type.value=source.company_type||'';
    enhanceSelects(form);refreshCompanyHints();refreshRepeatNotice();$('#companySuggestions').hidden=true;form.elements.role.focus();return;
  }
  if(action==='update-existing'){
    if(!await confirmBox('转到已有投递？','当前新增表单的内容不会保存，接下来为已有投递添加进展。','更新已有投递'))return;
    if(!findApp(id)){await load();if(!findApp(id)){notify('这条投递已不存在，请刷新后再试',true);return;}}
    openEditor('event',id);return;
  }

  if(action==='recognize-url'||action==='recognize-text')return recognizeInput(action==='recognize-url'?'url':'text');
  if(action==='apply-recognition')return applyRecognition();
  if(action==='personalize')return openPersonalization();
  if(action==='close-personalization')return closePersonalization();
  if(action==='reset-personalization'){fillPersonalization(personalization.defaults);notify('已恢复默认，保存后生效');return;}
  if(action==='new')return openEditor('new');
  if(action==='detail')return openDetail(id);
  if(action==='event'||action==='edit')return openEditor(action,id);
  if(action==='link'){openEditor('edit',id);if(!state.demo)$('#f-url').focus();return;}
  if(action==='close-drawer')return $('#drawer').close();
  if(action==='close-editor')return closeEditor();
  if(action==='confirm-yes'||action==='confirm-no')return $('#confirmDialog').close(action==='confirm-yes'?'yes':'no');
  if(action==='refresh'){await load();if(!state.error)notify('记录已刷新');return;}
  if(action==='demo'){state.demo=!state.demo;if(state.demo)demoApps=makeDemo();$('#drawer').close();state.day='';render();return;}
  if(action==='calendar-view'){state.calendarView=button.dataset.view;state.day='';render();document.getElementById(button.id)?.focus({preventScroll:true});return;}
  if(action==='calendar-year'){
    const form=$('#calendarJumpForm');
    const day=calendarDate(Number(form.elements.year.value)+Number(button.dataset.offset),Number(form.elements.month.value),Number(form.elements.day.value));
    if(!day){form.elements.year.reportValidity();return;}
    selectCalendarDay(day);document.getElementById(button.id)?.focus({preventScroll:true});return;
  }
  if(action==='calendar-month'){state.calendarMonth=shiftMonth(state.calendarMonth,Number(button.dataset.offset));state.day=state.calendarMonth+'-01';render();document.getElementById(button.id)?.focus({preventScroll:true});return;}
  if(action==='calendar-today'){state.calendarMonth=dayKey().slice(0,7);state.day=dayKey();render();$('#calendar-today')?.focus({preventScroll:true});return;}
  if(action==='calendar-day'){selectCalendarDay(button.dataset.day);if(button.classList.contains('calendar-more'))$('#scheduleAgenda').focus();return;}
  if(action==='day'){state.day=state.day===button.dataset.day?'':button.dataset.day;render();return;}
  if(action==='clear-day'){state.day='';render();return;}
  if(action==='scope'){state.scope=button.dataset.scope;state.day='';render();return;}
  if(action==='filter'){state.status=button.dataset.filter;render();return;}
  if(action==='priority-filter'){state.priority=!state.priority;render();return;}
  if(action==='clear-search'){state.query='';$('#globalSearch').value='';render();return;}
  if(action==='clear-classification'){state.company_type='';render();return;}
  if(action==='reset-filters'){Object.assign(state,{query:'',status:'',priority:false,company_type:''});$('#globalSearch').value='';render();return;}
  if(action==='stat'){state.query='';$('#globalSearch').value='';state.priority=false;state.company_type='';state.status={all:'',active:'进行中',interviews:'面试阶段',offer:'Offer'}[button.dataset.filter];navigate('applications');return;}
  if(action==='star'){const a=findApp(id);return mutate(`/api/applications/${encodeURIComponent(id)}`,'PATCH',{priority:a.priority==='重点关注'?'普通':'重点关注'},a.priority==='重点关注'?'已取消重点关注':'已标记为重点关注');}
  if(action==='complete'){button.disabled=true;await mutate(`/api/applications/${encodeURIComponent(id)}/complete`,'POST',{},'已完成，记下这一步了');button.disabled=false;return;}
  if(action==='delete'){
    const app=findApp(id);if(!app||state.demo)return;
    if(!await confirmBox('删除这份投递？',`${app.company} · ${app.role}\n岗位信息和时间线会一起删除。删除前会自动保存一份本地快照。`,'删除投递',true))return;
    try{await request(`/api/applications/${encodeURIComponent(id)}`,'DELETE');state.apps=state.apps.filter(a=>a.id!==id);$('#drawer').close();render();notify('投递已删除，删除前已生成本地备份');}catch(error){notify(error.message,true);}return;
  }
  if(action==='export-json'||action==='export-csv'){
    if(state.demo){notify('请先返回我的记录，再导出真实数据');return;}
    try{const response=await fetch(action==='export-json'?'/api/export.json':'/api/export.csv');if(!response.ok)throw new Error('导出失败，请重试');const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`秋招手帖-${dayKey()}.${action==='export-json'?'json':'csv'}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);notify('已生成导出文件');}catch(error){notify(error.message,true);}return;
  }
  if(action==='import'){if(state.demo){notify('请先返回我的记录，再导入备份');return;}$('#importFile').click();}
});
document.addEventListener('change',async event=>{
  const el=event.target;
  if(el.form?.id==='calendarJumpForm' && ['year','month'].includes(el.name)){
    const form=el.form,year=Number(form.elements.year.value),month=Number(form.elements.month.value);
    const last=calendarDate(year,month,31);
    if(last){const day=Number(calendarDate(year,month,Number(form.elements.day.value)).slice(8));form.elements.day.innerHTML=Array.from({length:Number(last.slice(8))},(_,i)=>`<option value="${i+1}" ${i+1===day?'selected':''}>${i+1} 日</option>`).join('');enhanceSelects(form);}
    return;
  }
  if(el.closest('#recordForm')&&['status','applied_on','company_type'].includes(el.name))el.dataset.touched='true';
  if(el.id==='companyTypeFilter'){state.company_type=el.value;render();return;}
  if(el.id==='stageFilter'){state.status=el.value;render();return;}
  if(el.id==='sortSelect'){state.sort=el.value;render();return;}
  if(el.dataset.statusId){
    const app=findApp(el.dataset.statusId),status=el.value;
    if(status==='已结束'&&app.next_action&&!await confirmBox('结束这份投递？','结束后，当前待办会一并清除，历史进展仍然保留。','结束投递')){el.value=app.status;enhanceSelects(el.parentElement);return;}
    el.disabled=true;enhanceSelects(el.parentElement);await mutate(`/api/applications/${encodeURIComponent(app.id)}`,'PATCH',{status},'阶段已更新，并记入时间线');return;
  }
  if(el.id==='importFile'){
    const file=el.files[0];el.value='';if(!file)return;
    try{
      let data;try{data=JSON.parse(await file.text());}catch{throw new Error('文件不是有效的 JSON，请选择完整备份');}
      if(data?.format!=='autumn-workbench'||![1,2].includes(data.version)||!Array.isArray(data.applications))throw new Error('请选择本工作台导出的 JSON 备份');
      if(!await confirmBox('合并这份备份？',`文件：${file.name}\n包含 ${data.applications.length} 份投递。已有记录会跳过，当前数据会先生成快照。`,'合并导入'))return;
      const result=await request('/api/import','POST',data);await load();notify(`已导入 ${result.imported} 份，跳过 ${result.skipped} 份已有记录`);
    }catch(error){notify(error.message,true);}
  }
});
$('#globalSearch').addEventListener('input',event=>{state.query=event.target.value;if(state.route!=='applications')navigate('applications');else render();});
document.addEventListener('keydown',event=>{if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)&&!document.querySelector('dialog[open]')){event.preventDefault();$('#globalSearch').focus();}});
$('#editor').addEventListener('cancel',event=>{event.preventDefault();closeEditor();});
$('#drawer').addEventListener('click',event=>{if(event.target===$('#drawer')){const box=event.target.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right)event.target.close();}});
$('#editor').addEventListener('click',event=>{if(event.target===$('#editor')){const box=event.target.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)closeEditor();}});
window.addEventListener('beforeunload',event=>{if($('#editor').open&&JSON.stringify([...new FormData($('#recordForm'))])!==formSnapshot){event.preventDefault();event.returnValue='';}});
window.addEventListener('hashchange',()=>{const route=location.hash.slice(1);if(routeNames[route])navigate(route);});
function personalValues(){return Object.fromEntries(new FormData($('#personalizationForm')));}
function personalPreview(){
  const values=personalValues();
  $('#personalPreview').innerHTML=`<div class="personal-preview-tagline">${escape(values.tagline)}</div><div class="note-block"><strong>${icon(values.icon)}${escape(values.title)}</strong><div class="personal-note-body">${escape(values.body)}</div></div>`;
}
function fillPersonalization(values){
  const form=$('#personalizationForm');
  for(const key of ['tagline','title','body','icon'])form.elements[key].value=values[key];
  personalPreview();
}
function openPersonalization(){
  const dialog=$('#personalizationDialog'),values=personalization.values;
  dialog.dataset.saving='false';
  dialog.innerHTML=`<form id="personalizationForm"><div class="dialog-heading"><div><h2 id="personalizationTitle">让工作台像你一点</h2><p>写给自己的话，按喜欢的样子来。</p></div><button type="button" class="icon-button" data-action="close-personalization" aria-label="关闭个性化设置">${icon('close')}</button></div><div class="form-content"><div id="personalPreview" class="personal-preview" aria-label="寄语预览"></div><div class="form-grid"><div class="field full"><label for="personalTagline">首页寄语</label><input id="personalTagline" name="tagline" maxlength="80" required><small class="muted">没有今日或逾期待办时显示，重要安排仍会优先提醒。</small></div><div class="field full"><label for="personalTitle">寄语标题</label><input id="personalTitle" name="title" maxlength="40" required></div><div class="field full"><label for="personalBody">寄语正文</label><textarea id="personalBody" name="body" maxlength="300" rows="3" required></textarea></div><fieldset class="personal-icons field full"><legend>选择图标</legend><div>${Object.entries(personalization.icons).map(([key,name])=>`<label title="${escape(name)}"><input type="radio" name="icon" value="${escape(key)}" ${key===values.icon?'checked':''} required><span>${icon(key)}<small>${escape(name)}</small></span></label>`).join('')}</div></fieldset></div><p id="personalError" class="form-error" role="alert" hidden></p></div><div class="dialog-footer"><button type="button" class="text-button" data-action="reset-personalization">恢复默认</button><div class="actions"><button type="button" class="button" data-action="close-personalization">取消</button><button type="submit" class="button primary">保存设置</button></div></div></form>`;
  fillPersonalization(values);personalSnapshot=JSON.stringify(personalValues());dialog.showModal();
}
async function closePersonalization(){
  const dialog=$('#personalizationDialog');if(dialog.dataset.saving==='true')return;
  if(JSON.stringify(personalValues())!==personalSnapshot&&!await confirmBox('放弃未保存的设置？','这些修改还没有保存。','放弃修改'))return;
  dialog.close();
}
$('#personalizationDialog').addEventListener('cancel',event=>{event.preventDefault();closePersonalization();});
document.addEventListener('input',event=>{if(event.target.form?.id==='personalizationForm')personalPreview();});
document.addEventListener('submit',async event=>{
  if(event.target.id!=='personalizationForm')return;
  event.preventDefault();const dialog=$('#personalizationDialog');if(dialog.dataset.saving==='true')return;
  const form=event.target,values=personalValues(),error=$('#personalError');
  error.hidden=true;dialog.dataset.saving='true';
  const controls=[...form.querySelectorAll('button,input,textarea')];controls.forEach(el=>el.disabled=true);
  try{personalization.values=await request('/api/personalization','PATCH',values);dialog.close();render();notify('个性化设置已保存');}
  catch(err){error.textContent=err.message;error.hidden=false;}
  finally{dialog.dataset.saving='false';controls.forEach(el=>el.disabled=false);}
});
window.addEventListener('beforeunload',event=>{if($('#personalizationDialog').open&&JSON.stringify(personalValues())!==personalSnapshot){event.preventDefault();event.returnValue='';}});
function makeDemo(){
  const today=dayKey();
  const fixtures=[
    ['远山科技','算法工程师','二面','北京','准备二面 · 复盘项目与算法题',today+'T19:00',-9,'重点关注','正式批'],
    ['星野智能','AI 应用工程师','笔试','上海','完成在线编程笔试',shiftDay(today,1)+'T14:00',-5,'重点关注'],
    ['知行数据','数据分析师','一面','杭州','参加业务一面',shiftDay(today,3)+'T10:30',-7,'普通'],
    ['远山科技','后端开发工程师','筛选中','深圳','补充作品集链接','',-3,'普通'],
    ['见微实验室','机器学习工程师','已投递','北京','','',-20,'重点关注'],
    ['长川软件','研发工程师','Offer','成都','确认录用意向与入职安排',shiftDay(today,5)+'T16:00',-18,'普通'],
    ['远山科技','算法工程师','已结束','北京','','',-30,'普通','提前批'],
    ['原点机器人','感知算法工程师','待投递','苏州','','',-1,'普通'],
  ];
  return fixtures.map(([company,role,status,city,next_action,due_at,days,priority,batch=''],i)=>{const applied_on=shiftDay(today,days),id='demo-'+i;const recentDay=i===4?applied_on:shiftDay(today,-(i%3));return {id,company,role,batch,status,city,company_type:['民企','民企','外企','民企','事业单位','国企','民企','民企'][i],industry:['互联网','人工智能','金融','互联网','教育科研','制造业','通信','制造业'][i],next_action,due_at,priority,applied_on,channel:i%2?'内推':'招聘官网',url:i<3?'https://example.com/careers/'+id:'',resume:i%2?'通用技术版 v2':'算法方向 v3',note:i===0?'重点准备：项目中的技术取舍、评估指标和失败案例。\n这是一条虚构的示例记录。':'这是一条虚构的示例记录，仅用于预览。',created_at:applied_on+'T10:00:00',updated_at:recentDay+'T14:00:00',events:[{id:id+'-1',status:'已投递',occurred_on:applied_on,created_at:applied_on+'T10:00:00',note:'通过招聘官网投递，使用对应方向的简历。',kind:'progress'},...(status!=='已投递'&&status!=='待投递'?[{id:id+'-2',status,occurred_on:recentDay,created_at:recentDay+'T14:00:00',note:i===0?'一面聊了项目设计与评估方式，已收到二面邀请。':'收到新的进展通知，已更新当前阶段。',kind:'progress'}]:[])]};});
}
await load();

// Progressive enhancement: supported agent browsers can use the same actions.
if(document.modelContext?.registerTool){
  const lifecycle=new AbortController();
  const register=tool=>{try{Promise.resolve(document.modelContext.registerTool(tool,{signal:lifecycle.signal})).catch(()=>{});}catch{/* Ordinary browsers keep using the visible interface. */}};
  const requireLive=()=>{if(state.demo)throw new Error('示例预览是只读的，请先返回我的记录。');};
  register({name:'search_applications',title:'查找秋招投递',description:'读取当前工作台的投递记录，返回匹配公司的岗位、编号、当前阶段和下一步。示例模式返回的记录会明确标记。',inputSchema:{type:'object',properties:{query:{type:'string'}},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute(input={}){if(typeof input.query!=='undefined'&&typeof input.query!=='string')throw new Error('query 必须是文字');return {demo:state.demo,applications:filterApps(apps(),{query:input.query||''}).map(({id,company,role,batch,job_code,company_type,industry,status,next_action,due_at})=>({id,company,role,batch,job_code,company_type,industry,status,next_action,due_at}))};}});
  register({name:'create_application',title:'记录新投递',description:'创建并保存一份真实投递，然后在列表中突出显示。需要公司和岗位；同公司自动归组；同名岗位再次投递需明确设置 allow_repeat=true。',inputSchema:{type:'object',properties:{company:{type:'string'},role:{type:'string'},job_code:{type:'string',maxLength:100,description:'招聘岗位编号，按原文保存（包括前导零）'},batch:{type:'string',maxLength:80},allow_repeat:{type:'boolean',description:'明确确认同公司同岗位新增一次独立投递'},company_type:{type:'string',enum:['',...COMPANY_TYPES]},industry:{type:'string',enum:['',...INDUSTRIES]},status:{type:'string',enum:STATUSES},city:{type:'string'},url:{type:'string',description:'投递官网或岗位页面的完整 http/https 地址'},next_action:{type:'string'},due_at:{type:'string',description:'本地时间，YYYY-MM-DDTHH:MM；有时间时必须填写 next_action'}},required:['company','role'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:true},async execute(input){requireLive();const result=await request('/api/applications','POST',input);acceptApp(result);revealCreatedApplication(result.id);notify('投递已记录');return {id:result.id,company:result.company,role:result.role,status:result.status};}});
  register({name:'add_application_progress',title:'保存投递进展',description:'为指定编号的真实投递追加进展并更新当前阶段。省略下一步与时间会保留原待办；传空字符串可清除。',inputSchema:{type:'object',properties:{id:{type:'string'},status:{type:'string',enum:STATUSES},note:{type:'string'},occurred_on:{type:'string',description:'YYYY-MM-DD'},next_action:{type:'string'},due_at:{type:'string'}},required:['id','status'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:true},async execute(input){requireLive();if(typeof input?.id!=='string'||!input.id)throw new Error('请提供投递编号');const {id,...data}=input;const result=await request(`/api/applications/${encodeURIComponent(id)}/events`,'POST',data);acceptApp(result);notify('进展已保存');return {id:result.id,status:result.status,next_action:result.next_action,due_at:result.due_at};}});
  window.addEventListener('pagehide',event=>{if(!event.persisted)lifecycle.abort();});
}

// Date navigation stays local to the month calendar and retains keyboard focus after render.
document.addEventListener('keydown',event=>{
  const button=event.target.closest?.('.calendar-date');
  if(!button || event.altKey || event.ctrlKey || event.metaKey)return;
  const offsets={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7};
  if(!(event.key in offsets))return;
  event.preventDefault();event.stopPropagation();
  selectCalendarDay(shiftDay(button.dataset.day,offsets[event.key]),true);
});

document.addEventListener('submit',event=>{
  if(event.target.id!=='calendarJumpForm')return;
  event.preventDefault();
  const form=event.target;
  const date=calendarDate(Number(form.elements.year.value),Number(form.elements.month.value),Number(form.elements.day.value));
  if(!date)return;
  selectCalendarDay(date);
  $('#calendarJumpForm button[type="submit"]')?.focus({preventScroll:true});
});
