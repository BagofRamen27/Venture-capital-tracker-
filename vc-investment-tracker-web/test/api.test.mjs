import {test} from 'node:test';
import assert from 'node:assert/strict';
import {handleAPI,validateCompany} from '../src/worker.js';
import {parseDirectory,discoveryURL} from '../src/discovery.js';
import {database} from './database.mjs';
const origin='https://example.test';
const req=(path,method='GET',body,user='alice',requestOrigin=origin)=>new Request(origin+path,{method,headers:{...(user?{'oai-authenticated-user-id':user}:{}),origin:requestOrigin,'content-type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
test('personal records persist, deduplicate, and are isolated between users',async()=>{
 const DB=database();
 try {
  const result=await handleAPI(req('/api/tracked','POST',{name:'Acme',website:'https://acme.test',stage:'Seed'}),{DB});assert.equal(result.status,201);const {company}=await result.json();
  assert.equal((await handleAPI(req('/api/tracked','POST',{name:'Acme duplicate',website:'https://www.acme.test/about'}),{DB})).status,409);
  assert.equal((await (await handleAPI(req('/api/tracked'),{DB})).json()).companies.length,1);
  assert.equal((await (await handleAPI(req('/api/tracked','GET',null,'bob'),{DB})).json()).companies.length,0);
  assert.equal((await handleAPI(req('/api/tracked/'+company.id,'PUT',{name:'Changed',website:'https://acme.test'},'bob'),{DB})).status,404);
  assert.equal((await handleAPI(req('/api/tracked/'+company.id,'DELETE',null,'bob'),{DB})).status,404);
  assert.equal((await handleAPI(req('/api/tracked','POST',{name:'Unsafe',website:'javascript:alert(1)'}),{DB})).status,400);
  assert.equal((await handleAPI(req('/api/tracked','POST',{name:'CSRF',website:'https://other.test'},'alice','https://evil.test'),{DB})).status,403);
  assert.equal((await handleAPI(req('/api/tracked','GET',null,null),{DB})).status,401);
  assert.equal((await handleAPI(req('/api/tracked/'+company.id,'PUT',{name:'Acme edited',website:'https://acme.test',stage:'Series A'}),{DB})).status,200);
  assert.equal((await (await handleAPI(req('/api/tracked'),{DB})).json()).companies[0].stage,'Series A');
 } finally {DB.close();}
});
test('personal list supports more than twenty companies',async()=>{
 const DB=database();
 try {
  for(let i=0;i<25;i++)assert.equal((await handleAPI(req('/api/tracked','POST',{name:'Company '+i,website:'https://startup'+i+'.test'}),{DB})).status,201);
  const list=await (await handleAPI(req('/api/tracked'),{DB})).json();
  assert.equal(list.companies.length,25);
  assert.equal(new Set(list.companies.map(c=>c.id)).size,25);
 } finally {DB.close();}
});
test('directory parser returns factual listings with unknown funding stage and safe links',()=>{
 const html='<p>1 results</p><tbody><tr><td><span>Acme &amp; Co</span><span>B2B</span></td><td>B2B</td><td>London</td><td>Founder</td><td><a href="https://acme.test">Website</a></td></tr></tbody><footer></footer>';
 const r=parseDirectory(html,'https://www.startupwho.com/startups');assert.equal(r.companies[0].name,'Acme & Co');assert.equal(r.companies[0].stage,'Not disclosed');assert.equal(r.total,1);
 assert.throws(()=>parseDirectory('<h1>Denied</h1>','https://www.startupwho.com/startups'));
 assert.equal(discoveryURL(new URLSearchParams('q=robotics&page=-4&industry=Fintech')).url.href,'https://www.startupwho.com/startups?q=robotics&vertical=Fintech');
 assert.throws(()=>validateCompany({name:'X',website:'https://user:password@example.com'}));
});
test('discovery cache preserves fetched timestamp and marks stale fallback',async()=>{
 const DB=database(),url='https://www.startupwho.com/startups';
 const value={companies:[],total:0,page:1,fetchedAt:'2026-01-01T00:00:00Z',stale:false};
 try {
  await DB.prepare('INSERT INTO discovery_cache VALUES (?,?,?)').bind(url,JSON.stringify(value),Date.now()).run();
  const fresh=await (await handleAPI(req('/api/discover'),{DB},()=>{throw Error('Must not fetch')})).json();assert.equal(fresh.fetchedAt,value.fetchedAt);assert.equal(fresh.stale,false);
  await DB.prepare('UPDATE discovery_cache SET fetched_at=? WHERE key=?').bind(Date.now()-7200000,url).run();
  const stale=await (await handleAPI(req('/api/discover'),{DB},()=>{throw Error('Offline')})).json();assert.equal(stale.stale,true);assert.equal(stale.fetchedAt,value.fetchedAt);
 } finally{DB.close();}
});
