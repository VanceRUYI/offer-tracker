import test from 'node:test';
import assert from 'node:assert/strict';
import {dayKey, shiftDay, taskGroups, filterApps, waitingApps} from './model.mjs';

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
