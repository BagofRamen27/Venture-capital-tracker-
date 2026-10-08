// Local preview without the Vercel CLI: serves public/ and runs api/*.js like Vercel does.
// Usage: npm run dev  (then open http://localhost:3000). Reads .env.local if present.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const envFile = path.join(root, ".env.local");
if (fs.existsSync(envFile)) {
  for (const line of fs.readFileSync(envFile, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)\s*$/);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^['"]|['"]$/g, "");
  }
}
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png" };
const port = Number(process.env.PORT || 3000);

http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${port}`);
  res.status = code => { res.statusCode = code; return res; };
  res.json = obj => { res.setHeader("content-type", "application/json"); res.end(JSON.stringify(obj)); return res; };
  if (url.pathname.startsWith("/api/")) {
    const file = path.join(root, "api", path.basename(url.pathname) + ".js");
    if (!fs.existsSync(file)) return res.status(404).json({ error: "Not found" });
    const mod = await import(pathToFileURL(file).href);
    return mod.default(req, res);
  }
  let file = path.join(root, "public", decodeURIComponent(url.pathname));
  if (!file.startsWith(path.join(root, "public"))) return res.status(403).end();
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
  if (!fs.existsSync(file)) return res.status(404).end("Not found");
  res.setHeader("content-type", types[path.extname(file)] || "application/octet-stream");
  fs.createReadStream(file).pipe(res);
}).listen(port, () => console.log(`Startup Investment Tracker on http://localhost:${port}`));
