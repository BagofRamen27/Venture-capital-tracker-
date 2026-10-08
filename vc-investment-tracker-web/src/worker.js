import { discoveryURL, parseDirectory, safeURL } from './discovery.js';
import {marketAPI} from './market.js';
const stages=['Not disclosed','Pre-seed','Seed','Series A','Series B','Series C+','Growth','Bootstrapped'];
const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'}});
export function validateCompany(input) {
  const clean=(key,max)=>typeof input[key]==='string'?input[key].trim().slice(0,max):'';
  const name=clean('name',140), website=safeURL(clean('website',500));
  if(!name)throw new Error('Enter a company name.');
  if(!website)throw new Error('Enter a valid company website starting with https:// or http://.');
  return {name,website,industry:clean('industry',80)||'Other',location:clean('location',140),stage:stages.includes(input.stage)?input.stage:'Not disclosed',notes:clean('notes',2000),source:['StartupWho','StartupDB'].includes(input.source)?input.source:'Added by you',sourceURL:safeURL(clean('sourceURL',600)),checkedAt:new Date().toISOString()};
}
export function companyIdentity(record){return new URL(record.website).hostname.toLowerCase().replace(/^www\./,'');}
export async function handleAPI(request,env,fetchImpl=fetch) {
  const url=new URL(request.url), user=request.headers.get('oai-authenticated-user-id');
  if(url.pathname==='/api/market'||url.pathname==='/api/news'||url.pathname.startsWith('/api/company/'))return marketAPI(request,env.DB,fetchImpl);
  if(url.pathname==='/api/session')return json({signedIn:!!user});
  if(url.pathname==='/api/discover') {
    if(request.method!=='GET')return json({error:'Method not allowed'},405);
    const {url:source,page}=discoveryURL(url.searchParams), key=source.href;
    const cached=await env.DB.prepare('SELECT payload, fetched_at FROM discovery_cache WHERE key = ?').bind(key).first();
    if(cached&&Date.now()-cached.fetched_at<3600000)return json(JSON.parse(cached.payload));
    try {
      const response=await fetchImpl(source.href,{headers:{'User-Agent':'VentureScout/1.0 (startup research directory; linked attribution)'},signal:AbortSignal.timeout(12000)});
      if(!response.ok)throw new Error('Source unavailable');
      const html=await response.text();if(html.length>2500000)throw new Error('Source too large');
      const result=parseDirectory(html,source.href,page);
      await env.DB.prepare('INSERT INTO discovery_cache (key,payload,fetched_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,fetched_at=excluded.fetched_at').bind(key,JSON.stringify(result),Date.now()).run();
      return json(result);
    } catch {
      if(cached&&Date.now()-cached.fetched_at<7*86400000)return json({...JSON.parse(cached.payload),stale:true});
      return json({error:'StartupWho could not be reached. Try again later or open the source directory.',sourceURL:source.href},502);
    }
  }
  if(url.pathname==='/api/tracked'||url.pathname.startsWith('/api/tracked/')) {
    if(!user)return json({error:'Sign in to save and manage your startup list.'},401);
    const base=url.pathname==='/api/tracked';
    const id=base?null:url.pathname.slice('/api/tracked/'.length);
    if(request.method==='GET'&&base) {
      const rows=await env.DB.prepare('SELECT id,record,created_at,updated_at FROM tracked_startups WHERE owner = ? ORDER BY created_at DESC').bind(user).all();
      return json({companies:rows.results.map(r=>({...JSON.parse(r.record),id:r.id,createdAt:r.created_at,updatedAt:r.updated_at}))});
    }
    if(!['POST','PUT','DELETE'].includes(request.method))return json({error:'Method not allowed'},405);
    if(request.headers.get('origin')!==url.origin)return json({error:'Request origin not allowed'},403);
    if(request.method==='DELETE'&&!base) {
      const result=await env.DB.prepare('DELETE FROM tracked_startups WHERE owner = ? AND id = ?').bind(user,id).run();
      return result.meta.changes?json({removed:true}):json({error:'Startup not found'},404);
    }
    if((request.method==='POST'&&!base)||(request.method==='PUT'&&base))return json({error:'Method not allowed'},405);
    if(!request.headers.get('content-type')?.includes('application/json'))return json({error:'JSON required'},415);
    const text=await request.text();if(text.length>12000)return json({error:'Company details are too large'},413);
    let record;try {record=validateCompany(JSON.parse(text));}catch(e){return json({error:e.message},400);}
    const identity=companyIdentity(record),now=new Date().toISOString();
    const duplicate=await env.DB.prepare('SELECT id FROM tracked_startups WHERE owner = ? AND identity = ?').bind(user,identity).first();
    if(duplicate&&duplicate.id!==id)return json({error:'You are already tracking this website.',id:duplicate.id},409);
    if(request.method==='POST') {
      const newID='VS-'+crypto.randomUUID();
      try {await env.DB.prepare('INSERT INTO tracked_startups (id,owner,identity,record,created_at,updated_at) VALUES (?,?,?,?,?,?)').bind(newID,user,identity,JSON.stringify(record),now,now).run();}
      catch(e){if(String(e).includes('UNIQUE'))return json({error:'You are already tracking this website.'},409);throw e;}
      return json({company:{...record,id:newID,createdAt:now,updatedAt:now}},201);
    }
    const result=await env.DB.prepare('UPDATE tracked_startups SET identity=?,record=?,updated_at=? WHERE owner=? AND id=?').bind(identity,JSON.stringify(record),now,user,id).run();
    return result.meta.changes?json({company:{...record,id,updatedAt:now}}):json({error:'Startup not found'},404);
  }
  return json({error:'Not found'},404);
}
export function createWorker(assets) {
  return {async fetch(request,env) {
    const path=new URL(request.url).pathname;
    if(path.startsWith('/api/')) {try{return await handleAPI(request,env);}catch{return json({error:'The service is temporarily unavailable. Your saved data has not been cleared.'},503);}}
    if(!['GET','HEAD'].includes(request.method))return new Response('Method not allowed',{status:405});
    const asset=assets[path==='/'?'/index.html':path];
    if(!asset)return new Response('Not found',{status:404});
    return new Response(request.method==='HEAD'?null:asset.body,{headers:{'content-type':asset.type,'cache-control':'no-cache','x-content-type-options':'nosniff','referrer-policy':'strict-origin-when-cross-origin','content-security-policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"}});
  }};
}
