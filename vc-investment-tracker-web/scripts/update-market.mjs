/* Daily StartupDB update: writes public/data/market.json.
   If StartupDB is unreachable, the previous file is kept and marked stale (no sample data is substituted).
   Usage: node scripts/update-market.mjs [--pages 4] [--details 200] [--strict] [--out <path>] */
import path from 'node:path';
import { updateMarketFile } from '../src/market.js';

const root = path.resolve(import.meta.dirname, '..');
const numArg = (name, fallback) => { const i = process.argv.indexOf(name); return i > -1 ? Number(process.argv[i + 1]) : fallback; };
const strArg = (name, fallback) => { const i = process.argv.indexOf(name); return i > -1 ? process.argv[i + 1] : fallback; };
const hasArg = name => process.argv.includes(name);

const outFile = strArg('--out', path.join(root, 'public', 'data', 'market.json'));
const result = await updateMarketFile({
  outFile,
  pages: numArg('--pages', 4),
  detailLimit: numArg('--details', 200),
  strict: hasArg('--strict'),
});

if (result.exitCode !== 0) {
  process.exitCode = result.exitCode;
}
