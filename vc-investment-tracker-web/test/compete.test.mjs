import { test } from 'node:test';
import assert from 'node:assert/strict';
await import('../public/compete.js');
const C = globalThis.VentureCompete;
const rated = (defs, ratings, extra = {}) => Object.fromEntries(defs.map(([k], i) => [k, { rating: ratings[i] ?? '', evidence: ratings[i] == null ? '' : 'evidence', source: '', self: false, ...extra }]));

test('weights sum to 100% for both scores', () => {
  for (const defs of [C.CS, C.DP]) assert.equal(defs.reduce((s, d) => s + d[2], 0), 100);
});

test('score is the weighted average of evidenced ratings', () => {
  const r = C.score(C.CS, rated(C.CS, ['5', '5', '5', '5', '5', '5']));
  assert.equal(r.score, 100); assert.equal(r.coverage, 1);
  assert.equal(C.score(C.CS, rated(C.CS, ['0', '0', '0', '0', '0', '0'])).score, 0);
  // 20%*5 + 20%*0 + 15%*5 + 20%*0 + 15%*5 + 10%*0 = 0.5 of the maximum
  assert.equal(C.score(C.CS, rated(C.CS, ['5', '0', '5', '0', '5', '0'])).score, 50);
});

test('missing factors are not scored as zero, and too little evidence withholds the score', () => {
  // 4 factors, 75% of weight, all rated 4 -> normalised over observed weight = 80, not 60
  const r = C.score(C.CS, rated(C.CS, ['4', '4', null, '4', '4', null]));
  assert.equal(r.score, 80); assert.equal(r.coverage, 0.75);
  // 3 factors only -> no score even though their weight is 60%
  assert.equal(C.score(C.CS, rated(C.CS, ['4', '4', null, '4', null, null])).score, null);
  // 4 factors but only 60% of the weight (diff, econ, gtm, exec) -> no score
  const low = C.score(C.CS, rated(C.CS, ['4', null, '4', null, '4', '4']));
  assert.equal(low.coverage, 0.6); assert.equal(low.factors, 4); assert.equal(low.score, null);
  assert.equal(C.score(C.DP, rated(C.DP, [null, null, '3', '3', '3', '3'])).score, null); // 60% coverage
});

test('a rating without written evidence does not count', () => {
  const v = rated(C.CS, ['5', '5', '5', '5', '5', '5']);
  for (const k of ['diff', 'traction', 'moat']) v[k].evidence = '  ';
  assert.equal(C.score(C.CS, v).score, null);
});

test('confidence is separate from the score', () => {
  const unsourced = C.score(C.CS, rated(C.CS, ['5', '5', '5', '5', '5', '5']));
  assert.equal(unsourced.score, 100); assert.equal(unsourced.confidence, 'low');
  const sourced = C.score(C.CS, rated(C.CS, ['1', '1', '1', '1', '1', '1'], { source: 'https://example.test/a' }));
  assert.equal(sourced.score, 20); assert.equal(sourced.confidence, 'high');
  const self = C.score(C.CS, rated(C.CS, ['3', '3', '3', '3', '3', '3'], { source: 'https://example.test/a', self: true }));
  assert.equal(self.mostlySelfReported, true); assert.notEqual(self.confidence, 'high');
});

test('stored or imported analyses are cleaned', () => {
  const a = C.normalize({ startup: { name: 'X'.repeat(500) }, competitors: Array(10).fill({ role: 'Bogus', exposure: 'total' }), type: 'magic', cs: { diff: { rating: 9 } }, extra: 'dropped' });
  assert.equal(a.startup.name.length, 140);
  assert.equal(a.competitors.length, C.MAX_COMPETITORS);
  assert.equal(a.competitors[0].role, C.ROLES[0]); assert.equal(a.competitors[0].exposure, 'unknown');
  assert.equal(a.type, 'insufficient_evidence'); assert.equal(a.cs.diff.rating, ''); assert.equal('extra' in a, false);
  const m = new Map(); const storage = { getItem: k => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
  storage.setItem(C.STORAGE_KEY, '{broken'); assert.deepEqual(C.load(storage), []);
  C.save(storage, [a]); assert.equal(C.load(storage)[0].id, a.id);
});

test('backup merge replaces same id and keeps others', () => {
  const a = C.newAnalysis('2026-10-15', 'CA-a'), b = C.newAnalysis('2026-10-15', 'CA-b');
  const r = C.merge([a, b], [{ ...a, risk: 'new' }, 'junk']);
  assert.equal(r.added, 1); assert.equal(r.list.length, 2); assert.equal(r.list.find(x => x.id === 'CA-a').risk, 'new');
});

test('markdown export shows unknowns, insufficient data and the method', () => {
  const a = C.newAnalysis('2026-10-15', 'CA-x');
  a.startup.name = 'Acme'; a.competitors.push(C.normalize({ competitors: [{ name: 'Big | Co' }] }).competitors[0]);
  const md = C.toMarkdown(a, '2026-10-15T00:00:00Z');
  assert.match(md, /# Acme/); assert.match(md, /Insufficient data/); assert.match(md, /\| Unknown \|/); assert.match(md, /Big \/ Co/); assert.match(md, /not investment advice/);
});

test('Christensen summary only calls it disruption when all four are yes', () => {
  assert.match(C.christensenSummary({ lowend: 'yes', worse: 'yes', ignore: 'yes', upmarket: 'yes' }), /All 4 yes/);
  assert.match(C.christensenSummary({ lowend: 'yes', worse: 'no', ignore: 'yes', upmarket: 'yes' }), /not disruption/);
  assert.match(C.christensenSummary({ lowend: 'yes' }), /not answered/);
});
