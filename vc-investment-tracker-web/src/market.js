import {safeURL,plain} from './discovery.js';
const text=(v,max=250)=>typeof v==='string'?v.slice(0,max):'';
const amount=a=>a&&Number.isFinite(Number(a.original))&&a.original!==null?{value:Number(a.original),currency:text(a.currency,8),qualifier:text(a.qualifier,30)}:null;
export function normalizeCompany(c){
 if(!c||!c.slug||!c.name)throw Error('Invalid company response');
 return {slug:text(c.slug,150),name:text(c.name,160),website:safeURL(c.websiteUrl||''),industry:text(c.profile?.sectorTags?.[0]?.value||c.profile?.sourceIndustryLabels?.[0]?.value||'Other',100),location:text(c.profile?.headquartersLocation),stage:text(c.latestFunding?.roundLabel||c.fundingHistory?.[0]?.roundLabel||'Not disclosed',60),latestDate:text(c.latestFundingDate,30),latestAmount:amount(c.latestFunding?.amount),source:'StartupDB',sourceURL:'https://startupdb.com/organizations/'+encodeURIComponent(c.slug)};
}
export function normalizeDetail(j){
 const c=j.data;
 const rounds=(c.fundingHistory||[]).map(r=>({date:text(r.eventDate,40),stage:text(r.roundLabel,80),amount:amount(r.amount),amountMeaning:text(r.amountMeaning,60),status:text(r.eventStatus,60),sources:(r.sourceUrls||[]).map(safeURL).filter(Boolean).slice(0,8),investors:(r.participants||[]).map(i=>({name:text(i.name,120),role:text(i.role,40)})),attribution:text(r.attribution,60)}));
 return {...normalizeCompany(c),totalRaised:text(c.fundingTotalRaised,100),lastSyncedAt:text(c.lastSyncedAt,100),rounds,roundsTotal:c.fundingHistoryTotal??rounds.length,valuation:null,revenue:null,coverage:'This feed supplies reported funding rounds, not structured valuations or revenue. Missing data is not zero.',disclosures:(c.scopeDisclosures||[]).map(x=>typeof x==='string'?x:JSON.stringify(x)).slice(0,10)};
}
export function parseNews(xml){
 if(!xml.includes('<rss'))throw Error('Invalid feed');
 const read=(item,tag)=>{const v=item.match(new RegExp('<'+tag+'[^>]*>([\\s\\S]*?)</'+tag+'>','i'))?.[1]||'';return plain(v.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g,'$1'));};
 return [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].slice(0,12).map(([,i])=>({title:read(i,'title'),url:safeURL(read(i,'link')),publishedAt:read(i,'pubDate')})).filter(x=>x.title&&x.url);
}
export async function marketAPI(request,DB,fetchImpl=fetch){
 const u=new URL(request.url);let source,normalize;
 if(u.pathname==='/api/market'){
  source=new URL('https://startupdb.com/api/v1/startups');source.searchParams.set('limit','50');
  source.searchParams.set('offset',String(Math.max(0,Math.min(100000,Number.parseInt(u.searchParams.get('offset')||'0',10)||0))));
  const q=(u.searchParams.get('q')||'').trim().slice(0,100);if(q)source.searchParams.set('q',q);
  normalize=j=>({companies:j.data.map(normalizeCompany),pagination:j.pagination,source:'StartupDB',license:'CC BY 4.0'});
 }else if(u.pathname.startsWith('/api/company/')){
  const slug=u.pathname.slice('/api/company/'.length);if(!/^[a-z0-9-]{1,150}$/.test(slug))return new Response(JSON.stringify({error:'Invalid company ID'}),{status:400});
  source=new URL('https://startupdb.com/api/v1/startups/'+slug);normalize=normalizeDetail;
 }else if(u.pathname==='/api/news'){
  source=new URL('https://techcrunch.com/tag/funding/feed/');normalize=xml=>({articles:parseNews(xml),source:'TechCrunch',sourceURL:'https://techcrunch.com/tag/funding/'});
 }else return null;
 const respond=(v,status=200)=>new Response(JSON.stringify(v),{status,headers:{'content-type':'application/json','cache-control':'no-store'}});
 if(request.method!=='GET')return respond({error:'Method not allowed'},405);
 const key=source.href,cached=await DB.prepare('SELECT payload,fetched_at FROM discovery_cache WHERE key=?').bind(key).first();
 if(cached&&Date.now()-cached.fetched_at<900000)return respond(JSON.parse(cached.payload));
 try{
  const r=await fetchImpl(source.href,{signal:AbortSignal.timeout(15000),headers:{Accept:u.pathname==='/api/news'?'application/rss+xml':'application/json'}});
  if(!r.ok)throw Error('Upstream '+r.status);
  const body=await r.text();if(body.length>8000000)throw Error('Response too large');
  const data={...normalize(u.pathname==='/api/news'?body:JSON.parse(body)),fetchedAt:new Date().toISOString(),stale:false};
  await DB.prepare('INSERT INTO discovery_cache (key,payload,fetched_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,fetched_at=excluded.fetched_at').bind(key,JSON.stringify(data),Date.now()).run();
  return respond(data);
 }catch{
  if(cached&&Date.now()-cached.fetched_at<86400000)return respond({...JSON.parse(cached.payload),stale:true});
  return respond({error:'The data source is unavailable. Retry shortly; no example data has been substituted.'},502);
 }
}
