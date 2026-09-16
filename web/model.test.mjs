import test from 'node:test';
import assert from 'node:assert/strict';
import {dayKey, shiftDay, shiftMonth, calendarDate, calendarDays, pickerDays, dateValue, taskGroups, filterApps, waitingApps} from './model.mjs';

test('date picker clamps month-end dates and validates year, month, and day', () => {
  assert.equal(calendarDate(2026,2,31),'2026-02-28');
  assert.equal(calendarDate(2024,2,31),'2024-02-29');
  assert.equal(calendarDate(2026,4,31),'2026-04-30');
  assert.equal(calendarDate(2031,12,5),'2031-12-05');
  for(const parts of [[0,1,1],[2026,13,1],[2026,1,0],[2026,1,32],[2026.5,1,1],[2026,2,NaN]]) {
    assert.equal(calendarDate(...parts),'');
  }
});

test('month navigation handles year boundaries independently of the current day', () => {
  assert.equal(shiftMonth('2026-12',1),'2027-01');
  assert.equal(shiftMonth('2027-01',-1),'2026-12');
  assert.equal(shiftMonth('2024-01',1),'2024-02');
});

test('month grid starts on Monday and includes leap days and adjacent months', () => {
  const leap=calendarDays([], '2024-02');
  assert.equal(leap[0].day,'2024-01-29');
  assert.equal(leap.length,35);
  assert.equal(leap.find(d=>d.day==='2024-02-29').inMonth,true);
  assert.equal(leap.at(-1).day,'2024-03-03');
  const sixWeeks=calendarDays([], '2026-03');
  assert.equal(sixWeeks.length,42);
  assert.equal(sixWeeks[0].day,'2026-02-23');
  assert.equal(sixWeeks.at(-1).day,'2026-04-05');
  assert.equal(calendarDays([], '2025-02').some(d=>d.day==='2025-02-29'),false);
});

test('calendar shows dated pending tasks in time order, including past and distant dates', () => {
  const apps=[
    {id:'late',next_action:'面试',due_at:'2026-09-30T16:00'},
    {id:'early',next_action:'笔试',due_at:'2026-09-30T09:00'},
    {id:'past',next_action:'补材料',due_at:'2026-09-01T09:00'},
    {id:'adjacent',next_action:'面试',due_at:'2026-10-01T09:00'},
    {id:'closed',status:'已结束',next_action:'旧安排',due_at:'2026-09-30T08:00'},
    {id:'done',next_action:'',due_at:'2026-09-30T08:00'},
    {id:'unscheduled',next_action:'准备简历',due_at:''},
  ];
  const snapshot=JSON.stringify(apps), days=calendarDays(apps,'2026-09');
  assert.deepEqual(days.find(d=>d.day==='2026-09-30').items.map(a=>a.id),['early','late']);
  assert.deepEqual(days.find(d=>d.day==='2026-09-01').items.map(a=>a.id),['past']);
  assert.equal(days.find(d=>d.day==='2026-10-01').inMonth,false);
  assert.deepEqual(days.flatMap(d=>d.items).map(a=>a.id).sort(),['adjacent','early','late','past']);
  assert.equal(JSON.stringify(apps),snapshot);
});

test('company classification filters combine and include old unclassified records', () => {
  const apps=[{id:'a',company_type:'央企',industry:'制造业',status:'二面'}, {id:'b',company_type:'国企',industry:'金融'}, {id:'c',company_type:'民企',industry:'互联网'}, {id:'old'}];
  assert.deepEqual(filterApps(apps,{company_type:'央国企'}).map(a=>a.id), ['a','b']);
  assert.deepEqual(filterApps(apps,{company_type:'央国企',industry:'制造业',status:'二面'}).map(a=>a.id), ['a']);
  assert.deepEqual(filterApps(apps,{company_type:'未填写'}).map(a=>a.id), ['old']);
  assert.deepEqual(filterApps(apps,{query:'互联网'}).map(a=>a.id), ['c']);
});

test('local calendar crosses month/year boundaries without UTC date shifts', () => {
  assert.equal(dayKey(new Date(2026, 8, 15, 0, 10)), '2026-09-15');
  assert.equal(shiftDay('2026-12-31', 1), '2027-01-01');
});
test('tasks cover overdue, today, seven-day boundary and no-date; ended jobs excluded', () => {
  const apps = [
    {id:'old', due_at:'2026-09-14T18:00',next_action:'测评'},
    {id:'today',due_at:'2026-09-15T19:00',next_action:'面试'},
    {id:'week',due_at:'2026-09-21T14:00',next_action:'面试'},
    {id:'later',due_at:'2026-09-22T14:00',next_action:'面试'},
    {id:'none',due_at:'',next_action:'补材料'},
    {id:'closed',status:'已结束',due_at:'2026-09-15T16:00',next_action:'旧任务'},
  ];
  const groups=taskGroups(apps, new Date(2026,8,15,12));
  assert.deepEqual(groups.overdue.map(x=>x.id),['old']);
  assert.deepEqual(groups.today.map(x=>x.id),['today']);
  assert.deepEqual(groups.week.map(x=>x.id),['week']);
  assert.deepEqual(groups.later.map(x=>x.id),['later']);
  assert.deepEqual(groups.unscheduled.map(x=>x.id),['none']);
});
test('search combines with status and priority and does not mutate input order', () => {
  const apps=[{id:'a',company:'Alpha',role:'算法',status:'二面',priority:'重点关注',applied_on:'2026-09-10'}, {id:'b',company:'Beta',role:'算法',status:'已投递',priority:'普通',applied_on:'2026-09-15'}];
  assert.deepEqual(filterApps(apps,{query:'alpha',status:'二面',priority:true}).map(x=>x.id),['a']);
  assert.deepEqual(filterApps(apps,{sort:'newest'}).map(x=>x.id),['b','a']);
  assert.equal(apps[0].id,'a');
});
test('waiting excludes not-yet-applied and ended applications', () => {
  const base={updated_at:'2026-08-01T10:00:00',next_action:''};
  const result=waitingApps([{...base,id:1,status:'已投递'}, {...base,id:2,status:'待投递'}, {...base,id:3,status:'已结束'}],new Date(2026,8,15));
  assert.deepEqual(result.map(x=>x.id),[1]);
});

test('date picker includes leap days and adjacent year dates', () => {
  const days=pickerDays('2024-02');
  assert.equal(days.length,42);
  assert.equal(days[0],'2024-01-29');
  assert.ok(days.includes('2024-02-29'));
  assert.equal(pickerDays('2027-01')[0],'2026-12-28');
});

test('date selection preserves local minutes and rejects invalid dates or times', () => {
  assert.equal(dateValue('2028-02-29','0','5',true),'2028-02-29T00:05');
  assert.equal(dateValue('2027-01-01','23','59',true),'2027-01-01T23:59');
  assert.equal(dateValue('2027-01-01','','',false),'2027-01-01');
  for(const args of [['2027-02-29','9','00'],['2028-02-30','9','00'],['2027-01-01','','00'],['2027-01-01','24','00'],['2027-01-01','9','60'],['2027-01-01','-1','00']]){
    assert.equal(dateValue(...args,true),'');
  }
});

test('companies group exact names without folding abbreviations and retain filtered order', async () => {
  const {groupCompanies, companyKey}=await import('./model.mjs');
  assert.equal(typeof groupCompanies,'function');
  const rows=[{id:'a',company:' Acme ',role:'算法',status:'一面'}, {id:'b',company:'ACME',role:'后端',status:'已结束'}, {id:'c',company:'Ac',role:'算法',status:'已投递'}];
  const groups=groupCompanies(rows);
  assert.equal(groups.length,2);
  assert.deepEqual(groups[0].items.map(a=>a.id),['a','b']);
  assert.equal(groups[0].active,1);
  assert.equal(companyKey(' AcME '),'acme');
  assert.deepEqual(groupCompanies(filterApps(rows,{status:'一面'}))[0].items.map(a=>a.id),['a']);
});

test('company suggestions prefer exact match and attempt labels distinguish repeat records', async () => {
  const {matchingCompanies, attemptLabel}=await import('./model.mjs');
  assert.equal(typeof matchingCompanies,'function');
  const rows=[{id:'a',company:'字节跳动',role:'算法',batch:'提前批',applied_on:'2026-08-01'}, {id:'b',company:'字节跳动',role:'算法',batch:'',applied_on:'2026-09-15'}, {id:'c',company:'字节',role:'后端'}];
  assert.equal(matchingCompanies(rows,'字节')[0].company,'字节');
  assert.equal(matchingCompanies(rows,'字节').length,2);
  assert.equal(attemptLabel(rows[0],rows),'算法 · 提前批');
  assert.equal(attemptLabel(rows[1],rows),'算法 · 2026-09-15');
  assert.equal(attemptLabel(rows[2],rows),'后端');
  assert.deepEqual(filterApps(rows,{query:'提前批'}).map(a=>a.id),['a']);
});

test('search matches job codes while old records need no code', () => {
  const records=[{id:'a',company:'Acme',role:'AI',job_code:'001-AI-26'},{id:'b',company:'Acme',role:'后端'}];
  assert.deepEqual(filterApps(records,{query:'001-ai'}).map(a=>a.id),['a']);
  assert.equal(filterApps(records).length,2);
});
