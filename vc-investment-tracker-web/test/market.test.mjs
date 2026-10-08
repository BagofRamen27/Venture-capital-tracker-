import {test} from 'node:test';
import assert from 'node:assert/strict';
import {normalizeDetail,parseNews,marketAPI} from '../src/market.js';
import {database} from './database.mjs';
test('funding is not substituted for valuation or revenue; sources and date precision preserved',()=>{
 const d=normalizeDetail({data:{slug:'acme',name:'Acme',fundingTotalRaised:'$5M',fundingHistory:[{eventDate:'2026-10',roundLabel:'Seed',amount:{original:'5000000',currency:'USD'},sourceUrls:['https://example.com/source','javascript:alert(1)']} ]}});
 assert.equal(d.valuation,null);assert.equal(d.revenue,null);assert.equal(d.rounds[0].date,'2026-10');assert.equal(d.rounds[0].amount.value,5000000);assert.equal(d.rounds[0].sources.length,1);
});
test('RSS keeps linked headlines only and rejects unsafe links',()=>{
 const r=parseNews('<rss><item><title><![CDATA[Funding &amp; growth]]></title><link>https://example.com/news</link><pubDate>Thu, 08 Oct 2026 10:00:00 GMT</pubDate><description>Article body not copied</description></item><item><title>Bad</title><link>javascript:alert(1)</link></item></rss>');
 assert.equal(r.length,1);assert.equal(r[0].title,'Funding & growth');assert.equal(r[0].description,undefined);
});
test('market paging uses fixed source and fails honestly without sample data',async()=>{
 const DB=database();try{
  let called;
  const r=await marketAPI(new Request('https://example.test/api/market?q=acme&offset=50'),DB,async url=>{called=url;return Response.json({data:[],pagination:{offset:50,limit:50,total:0}})});
  assert.equal(called,'https://startupdb.com/api/v1/startups?limit=50&offset=50&q=acme');assert.equal(r.status,200);
  const fail=await marketAPI(new Request('https://example.test/api/company/unknown'),DB,async()=>new Response('offline',{status:503}));assert.equal(fail.status,502);assert.equal((await fail.json()).companies,undefined);
 }finally{DB.close();}
});
