/* Daily StartupDB update: writes public/data/market.json.
   If StartupDB is unreachable, the previous file is kept and marked stale (no sample data is substituted).
   Usage: node scripts/update-market.mjs [--pages 4] [--details 200] */
import fs from 'node:fs';
import path from 'node:path';
import { fetchMarket } from '../src/market.js';

const root = path.resolve(import.meta.dirname, '..');
const out = path.join(root, 'public', 'data', 'market.json');
const arg = (name, fallback) => { const i = process.argv.indexOf(name); return i > -1 ? Number(process.argv[i + 1]) : fallback; };

try {
  const data = await fetchMarket({ pages: arg('--pages', 4), detailLimit: arg('--details', 200) });
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(data));
  console.log(`StartupDB: saved ${data.companies.length} companies and ${Object.keys(data.details).length} funding histories` +
    (data.errors.length ? ` (${data.errors.length} skipped)` : ''));
} catch (e) {
  if (fs.existsSync(out)) {
    const previous = JSON.parse(fs.readFileSync(out, 'utf8'));
    fs.writeFileSync(out, JSON.stringify({ ...previous, stale: true, lastError: e.message, lastAttemptAt: new Date().toISOString() }));
    console.warn('StartupDB unavailable; kept previous data and marked it stale: ' + e.message);
  } else {
    console.warn('StartupDB unavailable and no previous data exists: ' + e.message);
  }
}
