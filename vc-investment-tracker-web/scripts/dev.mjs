import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import {database} from '../test/database.mjs';
import {handleAPI} from '../src/worker.js';
const root=path.resolve(import.meta.dirname,'..');fs.mkdirSync(path.join(root,'.local'),{recursive:true});
const DB=database(path.join(root,'.local','dev.sqlite'));
const port=Number(process.env.PORT||3010);
http.createServer(async(req,res)=>{
 try {
  const url=new URL(req.url,`http://127.0.0.1:${port}`);
  if(url.pathname==='/signin-with-chatgpt'){res.writeHead(302,{'set-cookie':'local_scout=1; HttpOnly; SameSite=Lax; Path=/','location':'/#tracking'}).end();return;}
  if(url.pathname.startsWith('/api/')) {
   const headers=new Headers(req.headers);headers.delete('oai-authenticated-user-id');
   if((req.headers.cookie||'').includes('local_scout=1'))headers.set('oai-authenticated-user-id','local-preview-user');
   const chunks=[];for await(const chunk of req)chunks.push(chunk);
   const r=await handleAPI(new Request(url,{method:req.method,headers,...(!['GET','HEAD'].includes(req.method)?{body:Buffer.concat(chunks)}:{})}),{DB});
   res.writeHead(r.status,Object.fromEntries(r.headers)).end(await r.text());return;
  }
  const file=path.resolve(root,'public','.'+(url.pathname==='/'?'/index.html':decodeURIComponent(url.pathname)));
  if(!file.startsWith(path.join(root,'public')+path.sep)||!fs.statSync(file,{throwIfNoEntry:false})?.isFile()){res.writeHead(404).end();return;}
  const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'};
  res.writeHead(200,{'content-type':types[path.extname(file)]||'text/plain'}).end(fs.readFileSync(file));
 }catch(e){console.error(e.message);res.writeHead(500).end(JSON.stringify({error:'Preview error'}));}
}).listen(port,'127.0.0.1',()=>console.log(`Local: http://127.0.0.1:${port}`));
