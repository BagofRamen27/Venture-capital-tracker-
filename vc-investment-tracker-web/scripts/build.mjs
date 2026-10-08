/* Builds the static website into dist/ (what GitHub Pages publishes). No server code is involved. */
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const output = path.join(root, 'dist');
if (path.dirname(output) !== root) throw new Error('Invalid build target');
fs.rmSync(output, { recursive: true, force: true });
fs.cpSync(path.join(root, 'public'), output, { recursive: true });
fs.writeFileSync(path.join(output, '.nojekyll'), ''); // serve files as-is on GitHub Pages
for (const required of ['index.html', 'app.js', 'scout.js', 'market.js', 'app.css', 'data/config.json']) {
  if (!fs.existsSync(path.join(output, required))) throw new Error('Missing ' + required);
}
const data = ['market.json', 'discovery.json', 'news.json', 'status.json'].filter(f => !fs.existsSync(path.join(output, 'data', f)));
if (data.length) console.warn('Note: no ' + data.join(', ') + ' yet; the site shows "not available yet" for those sections.');
console.log('Built static site in dist/');
