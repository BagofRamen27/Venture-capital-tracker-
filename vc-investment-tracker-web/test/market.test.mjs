import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeDetail, fetchMarket, API } from '../src/market.js';

const company = (i) => ({ slug: 'co-' + i, name: 'Company ' + i, websiteUrl: 'https://co' + i + '.test', latestFunding: { roundLabel: 'Seed', amount: { original: '1000000', currency: 'USD' } } });

test('funding is not substituted for valuation or revenue; sources and date precision preserved', () => {
  const d = normalizeDetail({ data: { slug: 'acme', name: 'Acme', fundingTotalRaised: '$5M', fundingHistory: [{ eventDate: '2026-10', roundLabel: 'Seed', amount: { original: '5000000', currency: 'USD' }, sourceUrls: ['https://example.com/source', 'javascript:alert(1)'] }] } });
  assert.equal(d.valuation, null); assert.equal(d.revenue, null); assert.equal(d.rounds[0].date, '2026-10');
  assert.equal(d.rounds[0].amount.value, 5000000); assert.equal(d.rounds[0].sources.length, 1);
});

test('daily fetch pages through StartupDB, collects details and skips failures', async () => {
  const calls = [];
  const fetchImpl = async url => {
    calls.push(url);
    if (url.startsWith(API + '?')) {
      const offset = Number(new URL(url).searchParams.get('offset'));
      const data = offset === 0 ? Array.from({ length: 50 }, (_, i) => company(i)) : [company(50), { name: 'no slug' }];
      return Response.json({ data, pagination: { total: 51 } });
    }
    if (url.endsWith('/co-1')) return new Response('fail', { status: 500 });
    const slug = url.split('/').pop();
    return Response.json({ data: { ...company(slug.slice(3)), slug, fundingHistory: [] } });
  };
  const r = await fetchMarket({ pages: 5, detailLimit: 3, fetchImpl, sleep: async () => {} });
  assert.equal(r.companies.length, 51); // malformed row skipped, stopped after a short page
  assert.equal(calls.filter(u => u.startsWith(API + '?')).length, 2);
  assert.deepEqual(Object.keys(r.details), ['co-0', 'co-2']);
  assert.equal(r.errors.length, 1); assert.equal(r.total, 51); assert.equal(r.license, 'CC BY 4.0');
});

test('daily fetch fails loudly when the first page is unavailable (no sample data)', async () => {
  await assert.rejects(fetchMarket({ fetchImpl: async () => new Response('down', { status: 503 }), sleep: async () => {} }), /HTTP 503/);
});
