import test from 'node:test';
import assert from 'node:assert/strict';
import {createCompanyLogos} from './logos.mjs';

// Only the DOM host is stubbed; exercise real cache/discovery orchestration.
globalThis.document={createElement:()=>({setAttribute(){},addEventListener(){}}),body:{append(){}},addEventListener(){},querySelectorAll:()=>[]};
const logo={data_url:'data:image/png;base64,dGVzdA=='};
function setup({logos={},discover=async()=>logo}={}){
  const stored={...logos},calls=[];
  const manager=createCompanyLogos({notify(){},request:async(path,method,data)=>{
    if(path==='/api/company-logos')return {logos:{...stored},catalog:[]};
    if(path==='/api/company-logo/discover'){calls.push(data);return discover(data);}
    if(path==='/api/company-logo'){stored[data.company.toLowerCase()]=data.logo;return data.logo;}
    throw Error(path);
  }});
  return {manager,stored,calls};
}
test('saved application URL fetches and shares an icon without a catalog entry',async()=>{
  const {manager,stored,calls}=setup();await manager.load();
  await manager.ensure([{company:'Acme',url:'https://example.com/jobs/1'},{company:'Acme',url:'https://example.com/jobs/2'}]);
  assert.deepEqual(stored.acme,logo);
  assert.equal(calls.length,1);
  assert.equal(calls[0].website,'https://example.com/jobs/1');
  assert.equal(calls[0].automatic,true);
  assert.match(manager.markup('Acme'),/<img /);
});
test('failed URL stays quiet and retries only when another link becomes available',async()=>{
  const {manager,stored,calls}=setup({discover:async({website})=>{if(website.endsWith('/bad'))throw Error('unavailable');return logo;}});
  await manager.load();const bad={company:'Acme',url:'https://example.com/bad'};
  await manager.ensure([bad]);await manager.ensure([bad]);assert.equal(calls.length,1);
  await manager.ensure([bad,{company:'Acme',url:'https://example.com/good'}]);
  assert.deepEqual(stored.acme,logo);assert.equal(calls.length,2);
});
test('manual default and uploaded images are never overwritten',async()=>{
  const {manager,calls}=setup({logos:{acme:{disabled:true},other:logo}});await manager.load();
  await manager.ensure([{company:'Acme',url:'https://example.com/'},{company:'Other',url:'https://other.example/'}]);
  assert.equal(calls.length,0);
});
test('recognized icon is saved only for its matching company and application URL',async()=>{
  const {manager,stored}=setup({discover:async()=>{throw Error('unavailable');}});await manager.load();
  manager.remember({company:'Acme',application_url:'https://example.com/jobs/1',logo});
  await manager.ensure([{company:'Other',url:'https://example.com/jobs/1'},{company:'Acme',url:'https://example.com/jobs/2'}]);
  assert.deepEqual(stored,{});
  await manager.ensure([{company:'Acme',url:'https://example.com/jobs/1'}]);
  assert.deepEqual(stored.acme,logo);
});
test('overlapping renders do not start duplicate discovery for one company',async()=>{
  let finish;const {manager,calls}=setup({discover:()=>new Promise(resolve=>{finish=resolve;})});await manager.load();
  const records=[{company:'Acme',url:'https://example.com/'}];
  const first=manager.ensure(records);await manager.ensure(records);
  assert.equal(calls.length,1);finish(logo);await first;
});
test('recognized icon URL is fetched only after saving the matching record',async()=>{
  const {manager,stored,calls}=setup();await manager.load();
  manager.remember({company:'Acme',application_url:'https://example.com/jobs/1',
    logo:{website:'https://example.com/jobs/1',icon_url:'https://example.com/favicon.ico'}});
  assert.equal(calls.length,0);assert.deepEqual(stored,{});
  await manager.ensure([{company:'Acme',url:'https://example.com/jobs/1'}]);
  assert.equal(calls[0].icon_url,'https://example.com/favicon.ico');
  assert.deepEqual(stored.acme,logo);
});
