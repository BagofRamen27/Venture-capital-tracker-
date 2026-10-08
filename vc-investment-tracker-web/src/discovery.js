export const INDUSTRIES = ['B2B','Fintech','Consumer','Healthcare','Education','Industrials','Real Estate','Other'];
const entities = {amp:'&',quot:'"',apos:"'",lt:'<',gt:'>',nbsp:' '};
export function plain(value='') {
  return value.replace(/<!--[\s\S]*?-->/g,'').replace(/<[^>]*>/g,'').replace(/&(#x[0-9a-f]+|#\d+|\w+);/gi,(_,key)=>{
    if(key[0]==='#'){const n=key[1].toLowerCase()==='x'?parseInt(key.slice(2),16):Number(key.slice(1));return n>0&&n<=0x10ffff?String.fromCodePoint(n):'';}
    return entities[key]??'';
  }).replace(/\s+/g,' ').trim();
}
export function safeURL(value) {
  try { const u=new URL(value);if(!['http:','https:'].includes(u.protocol)||u.username||u.password)return '';return u.href; } catch {return '';}
}
export function discoveryURL(query) {
  const url=new URL('https://www.startupwho.com/startups');
  const q=(query.get('q')||'').trim().slice(0,100);
  const industry=query.get('industry')||'';
  const page=Math.min(100,Math.max(1,parseInt(query.get('page')||'1',10)||1));
  if(q)url.searchParams.set('q',q);
  if(INDUSTRIES.includes(industry))url.searchParams.set('vertical',industry);
  if(page>1)url.searchParams.set('page',String(page));
  return {url,page};
}
export function parseDirectory(html,sourceURL,page=1) {
  const body=html.match(/<tbody[^>]*>([\s\S]*?)<\/tbody>/i)?.[1];
  const totalMatch=plain(html.slice(0,html.indexOf('<footer'))).match(/([\d,]+) results/);
  const total=totalMatch?Number(totalMatch[1].replaceAll(',','')):null;
  if(!body && total!==0)throw new Error('The directory format changed. Open StartupWho directly while discovery is unavailable.');
  const companies=[];
  for(const row of (body||'').matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gi)) {
    const cells=[...row[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gi)].map(x=>x[1]);
    if(cells.length<3)continue;
    const name=plain(cells[0].match(/<span[^>]*>([\s\S]*?)<\/span>/)?.[1]||cells[0]);
    const website=safeURL(cells.at(-1).match(/href="([^"]+)"/)?.[1]?.replaceAll('&amp;','&')||'');
    if(!name)continue;
    companies.push({name,industry:plain(cells[1]),location:plain(cells[2]).replace(/^—$/,''),website,stage:'Not disclosed',source:'StartupWho',sourceURL});
  }
  if(!companies.length && total!==0)throw new Error('No readable listings returned by StartupWho.');
  return {companies,total,page,hasNext:html.includes('Next →')||html.includes('Next &rarr;'),sourceURL,fetchedAt:new Date().toISOString(),stale:false};
}
