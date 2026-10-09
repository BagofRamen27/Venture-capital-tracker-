/* Builds the static website into dist/ (what GitHub Pages publishes). No server code is involved. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const output = path.join(root, 'dist');
if (path.dirname(output) !== root) throw new Error('Invalid build target');
fs.rmSync(output, { recursive: true, force: true });
fs.cpSync(path.join(root, 'public'), output, { recursive: true });
fs.writeFileSync(path.join(output, '.nojekyll'), ''); // serve files as-is on GitHub Pages
for (const required of ['index.html', 'app.js', 'scout.js', 'market.js', 'app.css', 'data/config.json', 'contributors/contributors.json']) {
  if (!fs.existsSync(path.join(output, required))) throw new Error('Missing ' + required);
}
// Browsers cache scripts and styles for a while; a content hash in each URL makes them load the new
// version as soon as it changes, so the page and its code never get out of step after an update.
const indexPath = path.join(output, 'index.html');
let html = fs.readFileSync(indexPath, 'utf8');
for (const asset of ['app.css', 'scout.js', 'market.js', 'app.js']) {
  const hash = crypto.createHash('sha256').update(fs.readFileSync(path.join(output, asset))).digest('hex').slice(0, 10);
  const before = html;
  html = html.replace(`"${asset}"`, `"${asset}?v=${hash}"`);
  if (html === before) throw new Error('index.html does not reference ' + asset);
}
fs.writeFileSync(indexPath, html);
const data = ['market.json', 'discovery.json', 'news.json', 'status.json'].filter(f => !fs.existsSync(path.join(output, 'data', f)));
if (data.length) console.warn('Note: no ' + data.join(', ') + ' yet; the site shows "not available yet" for those sections.');
console.log('Built static site in dist/');
