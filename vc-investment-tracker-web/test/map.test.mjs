import { test } from 'node:test';
import assert from 'node:assert/strict';
await import('../public/scout.js');
const VS = globalThis.VentureScout;

const discovery = { companies: [
  { id: 1, name: 'Acme Robotics', industry: 'Robotics', funding_stage: 'Series A', latest_funding: { amount: 12e6, display: 'USD 12,000,000' }, total_funding: {} },
  { id: 2, name: 'No City Co', industry: 'Fintech', latest_funding: {}, total_funding: {} },
] };
const market = { companies: [
  { slug: 'acme-robotics', name: 'Acme Robotics', industry: 'robotics', location: 'Boston', latestAmount: { value: 1, currency: 'USD' } },
  { slug: 'nova', name: 'Nova', industry: 'climate_tech', stage: 'Seed', latestAmount: { value: 2500000, currency: 'EUR', qualifier: 'approximately' }, sourceURL: 'https://startupdb.com/organizations/nova' },
  { slug: 'ghost', name: 'Ghost', industry: 'ai' },
], details: { nova: {} } };
const places = {
  discovery: { 1: { lat: 42.36, lon: -71.06, place: 'Boston, United States', country: 'United States' } },
  market: { 'acme-robotics': { lat: 1, lon: 1 }, nova: { lat: 48.85, lon: 2.35, place: 'Paris, France', country: 'France' }, ghost: { lat: 'x', lon: 2 } },
};

test('only startups with a looked-up city become map points, each company once', () => {
  const points = VS.mapPoints(discovery, market, places);
  assert.deepEqual(points.map(p => p.name), ['Acme Robotics', 'Nova']);  // no city -> not placed; bad coordinates -> not placed
  assert.equal(points[0].kind, 'discovery');  // the discovered record wins over the StartupDB duplicate
  assert.equal(points[0].amount, 'Latest round USD 12,000,000');
  assert.deepEqual([points[1].industry, points[1].amount, points[1].detail], ['climate tech', 'Latest round approximately EUR 2,500,000', true]);
});

test('map filters combine search, country and industry', () => {
  const points = VS.mapPoints(discovery, market, places);
  assert.deepEqual(VS.filterMapPoints(points, { q: 'paris' }).map(p => p.name), ['Nova']);
  assert.deepEqual(VS.filterMapPoints(points, { country: 'United States' }).map(p => p.name), ['Acme Robotics']);
  assert.deepEqual(VS.filterMapPoints(points, { industry: 'CLIMATE TECH' }).map(p => p.name), ['Nova']);
  assert.equal(VS.filterMapPoints(points, { q: 'nova', country: 'United States' }).length, 0);
  assert.equal(VS.filterMapPoints(points, {}).length, 2);
});

test('missing data never produces a point', () => {
  assert.deepEqual(VS.mapPoints(null, null, null), []);
  assert.deepEqual(VS.mapPoints(discovery, market, {}), []);
});
