import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..'),output=path.join(root,'dist');
if(path.dirname(output)!==root)throw new Error('Invalid build target');
fs.mkdirSync(path.join(output,'server'),{recursive:true});
fs.mkdirSync(path.join(output,'.openai'),{recursive:true});
const assets={};
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8'};
function visit(dir,prefix=''){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const rel=prefix+'/'+entry.name,file=path.join(dir,entry.name);if(entry.isDirectory())visit(file,rel);else assets[rel]={body:fs.readFileSync(file,'utf8'),type:types[path.extname(entry.name)]||'text/plain'};}}
visit(path.join(root,'public'));
fs.copyFileSync(path.join(root,'src','worker.js'),path.join(output,'server','worker.js'));
fs.copyFileSync(path.join(root,'src','discovery.js'),path.join(output,'server','discovery.js'));
fs.copyFileSync(path.join(root,'src','market.js'),path.join(output,'server','market.js'));
fs.writeFileSync(path.join(output,'server','index.js'),`import {createWorker} from './worker.js';\nexport default createWorker(${JSON.stringify(assets)});\n`);
const manifest=path.join(root,'.openai','hosting.json');
if(fs.existsSync(manifest))fs.copyFileSync(manifest,path.join(output,'.openai','hosting.json'));
else fs.writeFileSync(path.join(output,'.openai','hosting.json'),JSON.stringify({d1:'DB'}));
fs.cpSync(path.join(root,'drizzle'),path.join(output,'.openai','drizzle'),{recursive:true});
console.log('Built VentureScout Worker with static assets and database migrations.');
