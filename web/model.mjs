export const STATUSES = ['待投递','已投递','筛选中','测评','笔试','一面','二面','终面','HR面','Offer','已结束','待确认'];
export const INTERVIEWS = ['一面','二面','终面','HR面'];
export const COMPANY_TYPES = ['央企','国企','民企','外企','合资企业','事业单位','其他'];
export const INDUSTRIES = ['互联网','人工智能','金融','制造业','能源','通信','医疗健康','教育科研','消费零售','其他'];
export function dayKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
export function shiftDay(day, amount) {
  const d = new Date(day+'T12:00:00'); d.setDate(d.getDate()+amount); return dayKey(d);
}
export function shiftMonth(month, amount) {
  const d = new Date(month+'-01T12:00:00');
  d.setMonth(d.getMonth()+amount);
  return dayKey(d).slice(0,7);
}
export function calendarDate(year, month, day) {
  if(![year,month,day].every(Number.isInteger) || year<1000 || year>9998 || month<1 || month>12 || day<1 || day>31)return '';
  const last=new Date(year,month,0).getDate();
  return `${year}-${String(month).padStart(2,'0')}-${String(Math.min(day,last)).padStart(2,'0')}`;
}
export function calendarDays(apps, month) {
  const first=month+'-01', date=new Date(first+'T12:00:00');
  const offset=(date.getDay()+6)%7;
  const last=shiftDay(shiftMonth(month,1)+'-01',-1);
  const count=Math.max(35,Math.ceil((offset+Number(last.slice(8)))/7)*7);
  const byDay=new Map();
  apps.filter(a=>a.next_action && a.due_at && a.status!=='已结束')
    .sort((a,b)=>a.due_at.localeCompare(b.due_at))
    .forEach(a=>{const key=a.due_at.slice(0,10);if(!byDay.has(key))byDay.set(key,[]);byDay.get(key).push(a);});
  return Array.from({length:count},(_,i)=>{
    const day=shiftDay(first,i-offset);
    return {day,inMonth:day.slice(0,7)===month,items:byDay.get(day)||[]};
  });
}
export function taskGroups(apps, now = new Date()) {
  const today=dayKey(now), end=shiftDay(today,6);
  const groups={overdue:[],today:[],week:[],later:[],unscheduled:[]};
  [...apps].filter(a=>a.next_action && a.status!=='已结束').sort((a,b)=>(a.due_at||'9999').localeCompare(b.due_at||'9999')).forEach(a=>{
    if (!a.due_at) groups.unscheduled.push(a);
    else if (new Date(a.due_at)<now) groups.overdue.push(a);
    else if (a.due_at.slice(0,10)===today) groups.today.push(a);
    else if (a.due_at.slice(0,10)<=end) groups.week.push(a);
    else groups.later.push(a);
  });
  return groups;
}
export function filterApps(apps, {query='',status='',priority=false,sort='newest',company_type='',industry=''}={}) {
  const q=query.trim().toLocaleLowerCase();
  const matches=(value,filter)=>!filter || (filter==='未填写' ? !value : value===filter);
  const list=apps.filter(a=>(!q || [a.company,a.role,a.batch,a.job_code,a.city,a.note,a.next_action,a.channel,a.resume,a.company_type,a.industry].join(' ').toLocaleLowerCase().includes(q)) && (!status || (status==='进行中' ? !['待投递','已结束','Offer'].includes(a.status) : a.status===status)) && (!priority || a.priority==='重点关注') && (company_type==='央国企' ? ['央企','国企'].includes(a.company_type) : matches(a.company_type,company_type)) && matches(a.industry,industry));
  return list.sort((a,b)=>{
    if(sort==='company') return a.company.localeCompare(b.company,'zh-CN');
    if(sort==='due') return (a.due_at||'9999').localeCompare(b.due_at||'9999');
    return (b.applied_on||'').localeCompare(a.applied_on||'') || (b.created_at||'').localeCompare(a.created_at||'');
  });
}
export function waitingApps(apps, now=new Date()) {
  return apps.filter(a=>['已投递','筛选中','一面','二面','终面','HR面','待确认'].includes(a.status) && !a.next_action && (now-new Date(a.updated_at))/86400000>=14).sort((a,b)=>a.updated_at.localeCompare(b.updated_at));
}

export function pickerDays(month) {
  const first = month+'-01';
  const offset = (new Date(first+'T12:00:00').getDay()+6)%7;
  return Array.from({length:42}, (_,i)=>shiftDay(first,i-offset));
}
export function dateValue(day, hour, minute, withTime) {
  if(!/^\d{4}-\d{2}-\d{2}$/.test(day) || dayKey(new Date(day+'T12:00:00'))!==day)return '';
  if(!withTime)return day;
  if(!/^\d{1,2}$/.test(String(hour)) || !/^\d{1,2}$/.test(String(minute)) || Number(hour)>23 || Number(minute)>59)return '';
  return `${day}T${String(hour).padStart(2,'0')}:${String(minute).padStart(2,'0')}`;
}

// Grouping affects presentation only; every attempt retains its own identity.
export const companyKey = value => String(value || '').trim().toLowerCase();
export function groupCompanies(records) {
  const groups = new Map();
  for(const app of records) {
    const key = companyKey(app.company);
    if(!groups.has(key))groups.set(key,{key, company:app.company.trim(), items:[], active:0});
    const group=groups.get(key); group.items.push(app);
    if(!['待投递','已结束','Offer'].includes(app.status))group.active++;
  }
  return [...groups.values()];
}
export function matchingCompanies(records, query) {
  const key=companyKey(query);
  if(!key)return [];
  return groupCompanies(records).filter(g=>g.key.includes(key)||key.includes(g.key))
    .sort((a,b)=>Number(b.key===key)-Number(a.key===key)||a.company.localeCompare(b.company,'zh-CN')).slice(0,6);
}
export function attemptLabel(app, records) {
  const repeats=records.filter(a=>companyKey(a.company)===companyKey(app.company)&&companyKey(a.role)===companyKey(app.role));
  let detail=app.batch || (repeats.length>1 ? app.applied_on : '');
  const sameLabel=repeats.filter(a=>(a.batch || a.applied_on)===detail);
  if(sameLabel.length>1){
    sameLabel.sort((a,b)=>(a.created_at||'').localeCompare(b.created_at||'')||a.id.localeCompare(b.id));
    detail += ` · 第 ${sameLabel.findIndex(a=>a.id===app.id)+1} 次`;
  }
  return app.role+(detail ? ' · '+detail : '');
}

// Completed tasks live in the journal so later tasks never overwrite them.
export function completedTasks(apps, {day='',scope='week',today=dayKey()}={}) {
  return apps.flatMap(app=>(app.events||[]).filter(e=>e.kind==='task'&&!e.task_reopened).map(e=>({
    ...app, event_id:e.id, next_action:e.task_title||e.note.replace(/^已完成：/,''),
    due_at:e.task_due_at||'', completed_at:e.created_at, completed_day:e.occurred_on,
  }))).filter(task=>{
    const taskDay=(task.due_at||task.completed_day).slice(0,10);
    return day ? taskDay===day : scope==='all'||taskDay<=shiftDay(today,6);
  }).sort((a,b)=>b.completed_at.localeCompare(a.completed_at));
}
