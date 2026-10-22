import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { normalizeDetail, fetchMarket, API, updateMarketFile, validateSnapshot, readSnapshot, safeWriteJSON } from '../src/market.js';

const company = (i) => ({ slug: 'co-' + i, name: 'Company ' + i, websiteUrl: 'https://co' + i + '.test', latestFunding: { roundLabel: 'Seed', amount: { original: '1000000', currency: 'USD' } } });


const withTempDir = async (fn) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vct-market-test-'));
  try {
    await fn(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
};

const makeLogger = () => {
  const logs = [], warns = [], errors = [];
  return {
    log: (...args) => logs.push(args.join(' ')),
    warn: (...args) => warns.push(args.join(' ')),
    error: (...args) => errors.push(args.join(' ')),
    logs, warns, errors,
  };
};

test('funding is not substituted for valuation or revenue; sources and date precision preserved', () => {
  const d = normalizeDetail({ data: { slug: 'acme', name: 'Acme', fundingTotalRaised: '$5M', fundingHistory: [{ eventDate: '2026-10', roundLabel: 'Seed', amount: { original: '5000000', currency: 'USD' }, sourceUrls: ['https://example.com/source', 'javascript:alert(1)'] }] } });
  assert.equal(d.valuation, null); assert.equal(d.revenue, null); assert.equal(d.rounds[0].date, '2026-10');
  assert.equal(d.rounds[0].amount.value, 5000000); assert.equal(d.rounds[0].sources.length, 1);
});

test('normalizeDetail rejects invalid response wrappers with predictable error', () => {
  const invalidWrappers = [
    null,
    undefined,
    'primitive-string',
    123,
    true,
    {},
    { error: 'Not found' },
    { data: null },
    { data: [] },
    { data: 'primitive-data' },
    { data: 123 },
    { data: true },
  ];
  for (const payload of invalidWrappers) {
    assert.throws(
      () => normalizeDetail(payload),
      { message: 'Invalid detail response' }
    );
  }
});

test('normalizeDetail rejects invalid company identity (missing or empty slug and name)', () => {
  const invalidIdentities = [
    { data: { name: 'Acme' } },                // missing slug
    { data: { slug: 'acme' } },                // missing name
    { data: { slug: '', name: 'Acme' } },       // empty slug
    { data: { slug: 'acme', name: '' } },       // empty name
    { data: { slug: '', name: '' } },           // empty both
  ];
  for (const payload of invalidIdentities) {
    assert.throws(
      () => normalizeDetail(payload),
      { message: 'Invalid detail response' }
    );
  }
});

test('normalizeDetail handles fundingHistory correctly: accepts missing, null, and valid array; rejects malformed non-array', () => {
  // 1. Missing fundingHistory -> defaults to empty array
  const missingFH = normalizeDetail({ data: { slug: 'acme', name: 'Acme' } });
  assert.deepEqual(missingFH.rounds, []);
  assert.equal(missingFH.roundsTotal, 0);

  // 2. Null fundingHistory -> defaults to empty array
  const nullFH = normalizeDetail({ data: { slug: 'acme', name: 'Acme', fundingHistory: null } });
  assert.deepEqual(nullFH.rounds, []);
  assert.equal(nullFH.roundsTotal, 0);

  // 3. Valid fundingHistory array -> mapped correctly
  const validFH = normalizeDetail({
    data: {
      slug: 'acme',
      name: 'Acme',
      fundingHistory: [
        { eventDate: '2026-01-01', roundLabel: 'Seed', amount: { original: '1000000', currency: 'USD' } }
      ]
    }
  });
  assert.equal(validFH.rounds.length, 1);
  assert.equal(validFH.rounds[0].stage, 'Seed');
  assert.equal(validFH.rounds[0].amount.value, 1000000);

  // 4. Present malformed non-array fundingHistory -> throws Invalid detail response
  const malformedFH = [
    { data: { slug: 'acme', name: 'Acme', fundingHistory: 'Series A' } },
    { data: { slug: 'acme', name: 'Acme', fundingHistory: 12345 } },
    { data: { slug: 'acme', name: 'Acme', fundingHistory: true } },
    { data: { slug: 'acme', name: 'Acme', fundingHistory: { round: 'Seed' } } },
  ];
  for (const payload of malformedFH) {
    assert.throws(
      () => normalizeDetail(payload),
      { message: 'Invalid detail response' }
    );
  }
});

test('normalizeDetail preserves output shape and mappings for valid minimal and full detail fixtures', () => {
  // Minimal valid fixture
  const min = normalizeDetail({ data: { slug: 'min-co', name: 'Min Co' } });
  assert.equal(min.slug, 'min-co');
  assert.equal(min.name, 'Min Co');
  assert.equal(min.website, '');
  assert.equal(min.industry, 'Other');
  assert.equal(min.location, '');
  assert.equal(min.stage, 'Not disclosed');
  assert.equal(min.latestDate, '');
  assert.equal(min.latestAmount, null);
  assert.equal(min.source, 'StartupDB');
  assert.equal(min.sourceURL, 'https://startupdb.com/organizations/min-co');
  assert.equal(min.totalRaised, '');
  assert.equal(min.lastSyncedAt, '');
  assert.deepEqual(min.rounds, []);
  assert.equal(min.roundsTotal, 0);
  assert.equal(min.valuation, null);
  assert.equal(min.revenue, null);
  assert.equal(min.coverage, 'This feed supplies reported funding rounds, not structured valuations or revenue. Missing data is not zero.');
  assert.deepEqual(min.disclosures, []);

  // Full valid fixture
  const full = normalizeDetail({
    data: {
      slug: 'full-co',
      name: 'Full Company',
      websiteUrl: 'https://full.test',
      profile: {
        sectorTags: [{ value: 'Enterprise AI' }],
        headquartersLocation: 'San Francisco, CA',
      },
      latestFunding: { roundLabel: 'Series B', amount: { original: '25000000', currency: 'USD' } },
      latestFundingDate: '2026-05-15',
      fundingTotalRaised: '$35M',
      lastSyncedAt: '2026-10-01T12:00:00Z',
      fundingHistoryTotal: 2,
      fundingHistory: [
        {
          eventDate: '2026-05-15',
          roundLabel: 'Series B',
          amount: { original: '25000000', currency: 'USD' },
          amountMeaning: 'equity',
          eventStatus: 'closed',
          sourceUrls: ['https://news.test/round', 'javascript:alert(1)'],
          participants: [{ name: 'Apex Ventures', role: 'lead' }],
          attribution: 'Public filing',
        },
      ],
      scopeDisclosures: ['Private data excluded', { complex: true }],
    },
  });
  assert.equal(full.slug, 'full-co');
  assert.equal(full.name, 'Full Company');
  assert.equal(full.website, 'https://full.test/');
  assert.equal(full.industry, 'Enterprise AI');
  assert.equal(full.location, 'San Francisco, CA');
  assert.equal(full.stage, 'Series B');
  assert.equal(full.latestDate, '2026-05-15');
  assert.equal(full.latestAmount.value, 25000000);
  assert.equal(full.totalRaised, '$35M');
  assert.equal(full.lastSyncedAt, '2026-10-01T12:00:00Z');
  assert.equal(full.roundsTotal, 2);
  assert.equal(full.rounds.length, 1);
  assert.equal(full.rounds[0].stage, 'Series B');
  assert.equal(full.rounds[0].sources.length, 1);
  assert.equal(full.rounds[0].sources[0], 'https://news.test/round');
  assert.deepEqual(full.rounds[0].investors, [{ name: 'Apex Ventures', role: 'lead' }]);
  assert.equal(full.disclosures.length, 2);
  assert.equal(full.disclosures[0], 'Private data excluded');
  assert.equal(full.disclosures[1], '{"complex":true}');
});

test('fetchMarket captures predictable detail-validation error when endpoint returns malformed response', async () => {
  const fetchImpl = async url => {
    if (url.startsWith(API + '?')) {
      return Response.json({
        data: [{ slug: 'co-valid', name: 'Valid Co' }, { slug: 'co-malformed', name: 'Malformed Co' }],
        pagination: { total: 2 },
      });
    }
    if (url.endsWith('/co-valid')) {
      return Response.json({ data: { slug: 'co-valid', name: 'Valid Co', fundingHistory: [] } });
    }
    if (url.endsWith('/co-malformed')) {
      // Returns error object without data wrapper
      return Response.json({ error: 'Organization not found' });
    }
    throw new Error('Unexpected URL: ' + url);
  };

  const res = await fetchMarket({ pages: 1, detailLimit: 2, fetchImpl, sleep: async () => {} });
  assert.equal(res.companies.length, 2);
  assert.ok(res.details['co-valid']);
  assert.equal(res.details['co-malformed'], undefined);
  assert.ok(res.errors.includes('co-malformed: Invalid detail response'));
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
  assert.equal(r.errors.length, 2); // 1 malformed listing row + 1 failed detail fetch
  assert.ok(r.errors.some(e => e.includes('no slug')));
  assert.ok(r.errors.some(e => e.includes('co-1')));
  assert.equal(r.total, 51); assert.equal(r.license, 'CC BY 4.0');
});

test('daily fetch fails loudly when the first page is unavailable (no sample data)', async () => {
  await assert.rejects(fetchMarket({ fetchImpl: async () => new Response('down', { status: 503 }), sleep: async () => {} }), /HTTP 503/);
});

test('validateSnapshot accepts valid market objects and rejects primitives, arrays, and missing companies', () => {
  assert.equal(validateSnapshot({ companies: [] }), true);
  assert.equal(validateSnapshot({ companies: [company(1)] }), true);
  assert.equal(validateSnapshot(null), false);
  assert.equal(validateSnapshot([]), false);
  assert.equal(validateSnapshot({}), false);
  assert.equal(validateSnapshot('string'), false);
});

test('readSnapshot detects missing, valid, and corrupt snapshot files', async () => {
  await withTempDir(async (dir) => {
    const missing = path.join(dir, 'missing.json');
    assert.deepEqual(readSnapshot(missing), { exists: false, valid: false, data: null });

    const validFile = path.join(dir, 'valid.json');
    fs.writeFileSync(validFile, JSON.stringify({ companies: [company(1)], details: {} }));
    const readValid = readSnapshot(validFile);
    assert.equal(readValid.exists, true);
    assert.equal(readValid.valid, true);
    assert.equal(readValid.data.companies.length, 1);

    const corruptFile = path.join(dir, 'corrupt.json');
    fs.writeFileSync(corruptFile, '{bad json');
    const readCorrupt = readSnapshot(corruptFile);
    assert.equal(readCorrupt.exists, true);
    assert.equal(readCorrupt.valid, false);
    assert.ok(readCorrupt.error);
  });
});

test('successful complete refresh updates snapshot with fresh data and exit code 0', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const fetchImpl = async (url) => {
      if (url.startsWith(API + '?')) {
        return Response.json({ data: [company(1), company(2)], pagination: { total: 2 } });
      }
      return Response.json({ data: { slug: 'co-1', name: 'Company 1', fundingHistory: [] } });
    };
    const logger = makeLogger();
    const res = await updateMarketFile({ outFile, fetchImpl, sleep: async () => {}, logger });
    assert.equal(res.status, 'success');
    assert.equal(res.exitCode, 0);

    const saved = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(saved.stale, false);
    assert.equal(saved.companies.length, 2);
    assert.ok(saved.fetchedAt);
    assert.ok(logger.logs.some(l => l.includes('saved 2 companies')));
  });
});

test('refresh failure with valid prior snapshot preserves data and marks stale in default mode', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const initial = { source: 'StartupDB', stale: false, companies: [company(1)], details: {} };
    fs.writeFileSync(outFile, JSON.stringify(initial));

    const fetchImpl = async () => new Response('down', { status: 503 });
    const logger = makeLogger();
    const res = await updateMarketFile({
      outFile,
      fetchImpl,
      sleep: async () => {},
      logger,
      strict: false,
      now: () => '2026-10-14T12:00:00.000Z',
    });

    assert.equal(res.status, 'degraded');
    assert.equal(res.exitCode, 0);
    assert.equal(res.error, 'StartupDB returned HTTP 503');

    const updated = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(updated.stale, true);
    assert.equal(updated.companies.length, 1);
    assert.equal(updated.companies[0].slug, 'co-1');
    assert.equal(updated.lastError, 'StartupDB returned HTTP 503');
    assert.equal(updated.lastAttemptAt, '2026-10-14T12:00:00.000Z');

    assert.ok(logger.warns.some(w => w.includes('StartupDB unavailable; kept previous data and marked it stale')));
    assert.ok(logger.logs.some(l => l.includes('::warning::StartupDB refresh failed')));
  });
});

test('refresh failure with valid prior snapshot returns exit code 1 when strict mode is enabled', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const initial = { source: 'StartupDB', stale: false, companies: [company(1)], details: {} };
    fs.writeFileSync(outFile, JSON.stringify(initial));

    const fetchImpl = async () => new Response('down', { status: 503 });
    const logger = makeLogger();
    const res = await updateMarketFile({
      outFile,
      fetchImpl,
      sleep: async () => {},
      logger,
      strict: true,
    });

    assert.equal(res.status, 'degraded');
    assert.equal(res.exitCode, 1);

    const updated = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(updated.stale, true);
    assert.equal(updated.companies[0].slug, 'co-1'); // Data preserved
    assert.ok(logger.errors.some(e => e.includes('Strict mode enabled')));
  });
});

test('first-page failure with no prior snapshot fails explicitly with exit code 1', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const fetchImpl = async () => new Response('down', { status: 503 });
    const logger = makeLogger();
    const res = await updateMarketFile({ outFile, fetchImpl, sleep: async () => {}, logger });

    assert.equal(res.status, 'missing_snapshot');
    assert.equal(res.exitCode, 1);
    assert.equal(fs.existsSync(outFile), false);
    assert.ok(logger.errors.some(e => e.includes('no previous data exists')));
    assert.ok(logger.logs.some(l => l.includes('::warning::StartupDB refresh failed and no previous data exists')));
  });
});

test('later-page pagination failure does not overwrite complete snapshot with partial data', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const initialCompanies = Array.from({ length: 100 }, (_, i) => company(i));
    fs.writeFileSync(outFile, JSON.stringify({ source: 'StartupDB', stale: false, companies: initialCompanies, details: {} }));

    const fetchImpl = async (url) => {
      const offset = Number(new URL(url).searchParams.get('offset'));
      if (offset === 0) {
        return Response.json({ data: Array.from({ length: 50 }, (_, i) => company(i + 500)), pagination: { total: 100 } });
      }
      return new Response('page 2 fail', { status: 500 });
    };

    const logger = makeLogger();
    const res = await updateMarketFile({ outFile, pages: 3, fetchImpl, sleep: async () => {}, logger });
    assert.equal(res.status, 'degraded');
    assert.equal(res.exitCode, 0);

    const preserved = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(preserved.companies.length, 100); // 100 original companies preserved!
    assert.equal(preserved.stale, true);
    assert.ok(preserved.lastError.includes('Pagination failed on later page'));
  });
});

test('partial pagination failure with no prior snapshot fails explicitly without saving incomplete data', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const fetchImpl = async (url) => {
      const offset = Number(new URL(url).searchParams.get('offset'));
      if (offset === 0) {
        return Response.json({ data: Array.from({ length: 50 }, (_, i) => company(i)), pagination: { total: 100 } });
      }
      return new Response('page 2 fail', { status: 500 });
    };

    const logger = makeLogger();
    const res = await updateMarketFile({ outFile, pages: 3, fetchImpl, sleep: async () => {}, logger });
    assert.equal(res.status, 'missing_snapshot');
    assert.equal(res.exitCode, 1);
    assert.equal(fs.existsSync(outFile), false);
  });
});

test('corrupt snapshot file is not overwritten and fails explicitly with exit code 1', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const corruptContent = '{broken-json-content: 123';
    fs.writeFileSync(outFile, corruptContent);

    const fetchImpl = async () => new Response('down', { status: 503 });
    const logger = makeLogger();
    const res = await updateMarketFile({ outFile, fetchImpl, sleep: async () => {}, logger });

    assert.equal(res.status, 'corrupt_snapshot');
    assert.equal(res.exitCode, 1);
    assert.equal(fs.readFileSync(outFile, 'utf8'), corruptContent); // Corrupt file kept intact
    assert.ok(logger.errors.some(e => e.includes('existing snapshot is corrupt')));
  });
});

test('repeated refresh failures update lastAttemptAt and lastError while keeping initial companies', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    fs.writeFileSync(outFile, JSON.stringify({ source: 'StartupDB', stale: false, companies: [company(1)], details: {} }));

    await updateMarketFile({
      outFile,
      fetchImpl: async () => new Response('down 503', { status: 503 }),
      sleep: async () => {},
      logger: makeLogger(),
      now: () => '2026-10-14T01:00:00.000Z',
    });

    const firstUpdate = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(firstUpdate.lastError, 'StartupDB returned HTTP 503');
    assert.equal(firstUpdate.lastAttemptAt, '2026-10-14T01:00:00.000Z');

    await updateMarketFile({
      outFile,
      fetchImpl: async () => new Response('down 502', { status: 502 }),
      sleep: async () => {},
      logger: makeLogger(),
      now: () => '2026-10-14T02:00:00.000Z',
    });

    const secondUpdate = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(secondUpdate.companies.length, 1);
    assert.equal(secondUpdate.lastError, 'StartupDB returned HTTP 502');
    assert.equal(secondUpdate.lastAttemptAt, '2026-10-14T02:00:00.000Z');
  });
});

test('safeWriteJSON ensures atomic writes and cleans up temporary files', async () => {
  await withTempDir(async (dir) => {
    const target = path.join(dir, 'atomic.json');
    const initialData = { companies: [company(1)] };
    safeWriteJSON(target, initialData);
    assert.deepEqual(JSON.parse(fs.readFileSync(target, 'utf8')), initialData);

    // Overwrite safely
    const nextData = { companies: [company(2)] };
    safeWriteJSON(target, nextData);
    assert.deepEqual(JSON.parse(fs.readFileSync(target, 'utf8')), nextData);

    // Verify no stray .tmp files exist in the directory
    const files = fs.readdirSync(dir);
    assert.deepEqual(files, ['atomic.json']);
  });
});

test('safeWriteJSON propagates rename errors, preserves existing snapshot, and cleans up temp files', async () => {
  await withTempDir(async (dir) => {
    const target = path.join(dir, 'preserved.json');
    const originalData = { companies: [company(1)], name: 'original' };
    safeWriteJSON(target, originalData);
    assert.deepEqual(JSON.parse(fs.readFileSync(target, 'utf8')), originalData);

    const mockFs = {
      ...fs,
      renameSync: () => {
        throw new Error('EPERM: simulated locked destination');
      },
    };

    assert.throws(
      () => safeWriteJSON(target, { companies: [company(2)], name: 'new' }, { fsImpl: mockFs }),
      /EPERM: simulated locked destination/
    );

    // Verify original snapshot is preserved and untouched
    assert.deepEqual(JSON.parse(fs.readFileSync(target, 'utf8')), originalData);

    // Verify temp file was cleaned up and not left in the directory
    const remaining = fs.readdirSync(dir);
    assert.deepEqual(remaining, ['preserved.json']);
  });
});

test('safeWriteJSON propagates writeFileSync errors without corrupting existing snapshot', async () => {
  await withTempDir(async (dir) => {
    const target = path.join(dir, 'preserved.json');
    const originalData = { companies: [company(1)] };
    safeWriteJSON(target, originalData);

    const mockFs = {
      ...fs,
      writeFileSync: () => {
        throw new Error('ENOSPC: simulated disk full');
      },
    };

    assert.throws(
      () => safeWriteJSON(target, { companies: [company(2)] }, { fsImpl: mockFs }),
      /ENOSPC: simulated disk full/
    );

    // Original data remains valid
    assert.deepEqual(JSON.parse(fs.readFileSync(target, 'utf8')), originalData);
  });
});


test('successful refresh returning zero companies updates snapshot with exit code 0 under data contract', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const fetchImpl = async (url) => {
      if (url.startsWith(API + '?')) {
        return Response.json({ data: [], pagination: { total: 0 } });
      }
      return Response.json({ data: {} });
    };
    const logger = makeLogger();
    const res = await updateMarketFile({ outFile, fetchImpl, sleep: async () => {}, logger });
    assert.equal(res.status, 'success');
    assert.equal(res.exitCode, 0);

    const saved = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(saved.stale, false);
    assert.equal(saved.companies.length, 0);
    assert.deepEqual(saved.companies, []);
    assert.equal(validateSnapshot(saved), true);
  });
});

test('scripts/update-market.mjs CLI execution handles --out, --strict, and exit codes correctly with isolated mock', async () => {
  await withTempDir(async (dir) => {
    const scriptPath = path.resolve('scripts/update-market.mjs');
    // Place mock module completely inside isolated temp directory, NOT in the repository
    const mockModule = path.join(dir, 'mock-failing-fetch.mjs');
    fs.writeFileSync(mockModule, 'globalThis.fetch = async () => new Response("down", { status: 503 });');
    const mockUrl = pathToFileURL(mockModule).href;

    // 1. Missing snapshot -> exit code 1
    const missingOut = path.join(dir, 'missing-market.json');
    const r1 = spawnSync(process.execPath, ['--import', mockUrl, scriptPath, '--out', missingOut], { encoding: 'utf8' });
    assert.equal(r1.status, 1);

    // 2. Valid snapshot in default mode -> exit code 0
    const validOut = path.join(dir, 'valid-market.json');
    fs.writeFileSync(validOut, JSON.stringify({ companies: [company(1)], details: {} }));
    const r2 = spawnSync(process.execPath, ['--import', mockUrl, scriptPath, '--out', validOut], { encoding: 'utf8' });
    assert.equal(r2.status, 0);
    const updated = JSON.parse(fs.readFileSync(validOut, 'utf8'));
    assert.equal(updated.stale, true);

    // 3. Valid snapshot with --strict -> exit code 1
    const r3 = spawnSync(process.execPath, ['--import', mockUrl, scriptPath, '--out', validOut, '--strict'], { encoding: 'utf8' });
    assert.equal(r3.status, 1);
  });
});

test('listing response schema validation rejects unexpected payloads, null, and non-array data', async () => {
  const invalidPayloads = [
    { error: 'throttled' },
    {},
    { data: null },
    { data: 'invalid' },
    { data: { not: 'an array' } },
  ];

  for (const payload of invalidPayloads) {
    const fetchImpl = async () => Response.json(payload);
    await assert.rejects(
      fetchMarket({ fetchImpl, sleep: async () => {} }),
      /StartupDB returned invalid listing payload: missing data array/
    );
  }

  // Valid empty array should be accepted without throwing
  const validFetch = async () => Response.json({ data: [], pagination: { total: 0 } });
  const res = await fetchMarket({ fetchImpl: validFetch, sleep: async () => {} });
  assert.equal(res.companies.length, 0);
  assert.equal(res.stale, false);
});

test('first-page listing schema failure preserves existing snapshot and marks it stale', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const initialData = {
      source: 'StartupDB',
      stale: false,
      companies: Array.from({ length: 100 }, (_, i) => company(i)),
      details: {},
    };
    fs.writeFileSync(outFile, JSON.stringify(initialData));

    const fetchImpl = async () => Response.json({ error: 'throttled' });
    const logger = makeLogger();
    const res = await updateMarketFile({ outFile, fetchImpl, sleep: async () => {}, logger });

    assert.equal(res.status, 'degraded');
    assert.equal(res.exitCode, 0);
    assert.ok(res.error.includes('StartupDB returned invalid listing payload: missing data array'));

    const preserved = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(preserved.companies.length, 100);
    assert.equal(preserved.stale, true);
    assert.ok(preserved.lastError.includes('missing data array'));
    assert.ok(logger.warns.some(w => w.includes('StartupDB unavailable; kept previous data and marked it stale')));
  });
});

test('later-page listing schema failure does not overwrite complete snapshot with partial data', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const initialData = {
      source: 'StartupDB',
      stale: false,
      companies: Array.from({ length: 100 }, (_, i) => company(i)),
      details: {},
    };
    fs.writeFileSync(outFile, JSON.stringify(initialData));

    // Page 0 returns 50 companies; Page 1 returns {"error": "throttled"}
    const fetchImpl = async (url) => {
      const offset = Number(new URL(url).searchParams.get('offset'));
      if (offset === 0) {
        return Response.json({
          data: Array.from({ length: 50 }, (_, i) => company(i + 500)),
          pagination: { total: 200 }
        });
      }
      return Response.json({ error: 'throttled' });
    };

    const logger = makeLogger();
    const res = await updateMarketFile({ outFile, pages: 3, fetchImpl, sleep: async () => {}, logger });

    assert.equal(res.status, 'degraded');
    assert.equal(res.exitCode, 0);
    assert.ok(res.error.includes('Pagination failed on later page'));
    assert.ok(res.error.includes('missing data array'));

    const preserved = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(preserved.companies.length, 100); // All 100 original companies preserved, NOT truncated to 50
    assert.equal(preserved.stale, true);
    assert.ok(preserved.lastError.includes('Pagination failed on later page'));
    assert.ok(preserved.lastError.includes('missing data array'));
  });
});

test('listing schema failure with no prior snapshot fails explicitly with exit code 1', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');

    // Case A: First page returns unexpected payload
    const fetchImplFirstPage = async () => Response.json({ error: 'throttled' });
    const loggerA = makeLogger();
    const resA = await updateMarketFile({ outFile, fetchImpl: fetchImplFirstPage, sleep: async () => {}, logger: loggerA });
    assert.equal(resA.status, 'missing_snapshot');
    assert.equal(resA.exitCode, 1);
    assert.equal(fs.existsSync(outFile), false);

    // Case B: Later page returns unexpected payload
    const fetchImplLaterPage = async (url) => {
      const offset = Number(new URL(url).searchParams.get('offset'));
      if (offset === 0) {
        return Response.json({
          data: Array.from({ length: 50 }, (_, i) => company(i)),
          pagination: { total: 100 }
        });
      }
      return Response.json({ error: 'throttled' });
    };
    const loggerB = makeLogger();
    const resB = await updateMarketFile({ outFile, pages: 3, fetchImpl: fetchImplLaterPage, sleep: async () => {}, logger: loggerB });
    assert.equal(resB.status, 'missing_snapshot');
    assert.equal(resB.exitCode, 1);
    assert.equal(fs.existsSync(outFile), false);
  });
});

test('listing schema failure returns exit code 1 when strict mode is enabled', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    fs.writeFileSync(outFile, JSON.stringify({
      source: 'StartupDB',
      stale: false,
      companies: [company(1)],
      details: {}
    }));

    const fetchImpl = async () => Response.json({ error: 'throttled' });
    const logger = makeLogger();
    const res = await updateMarketFile({
      outFile,
      strict: true,
      fetchImpl,
      sleep: async () => {},
      logger
    });

    assert.equal(res.status, 'degraded');
    assert.equal(res.exitCode, 1);

    const preserved = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(preserved.companies.length, 1);
    assert.equal(preserved.stale, true);
    assert.ok(logger.errors.some(e => e.includes('Strict mode enabled')));
  });
});

test('mixed valid and malformed listing rows retain valid companies and record bounded diagnostics', async () => {
  const fetchImpl = async () => Response.json({
    data: [
      company(1),
      { name: 'missing slug' },
      null,
      company(2),
      { slug: 'missing name' },
    ],
    pagination: { total: 5 }
  });
  const res = await fetchMarket({ pages: 1, detailLimit: 0, fetchImpl, sleep: async () => {} });
  assert.equal(res.companies.length, 2);
  assert.equal(res.companies[0].slug, 'co-1');
  assert.equal(res.companies[1].slug, 'co-2');
  assert.equal(res.stale, false);
  assert.equal(res.errors.length, 3);
  assert.ok(res.errors.some(e => e.includes('missing slug')));
  assert.ok(res.errors.some(e => e.includes('missing name')));
});

test('first-page where all rows fail normalization preserves existing snapshot and marks it stale', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const initialData = {
      source: 'StartupDB',
      stale: false,
      companies: Array.from({ length: 100 }, (_, i) => company(i)),
      details: {},
    };
    fs.writeFileSync(outFile, JSON.stringify(initialData));

    // Return 50 rows where all rows fail normalization
    const fetchImpl = async () => Response.json({
      data: Array.from({ length: 50 }, () => ({ invalid: 'schema drift' })),
      pagination: { total: 50 }
    });
    const logger = makeLogger();
    const res = await updateMarketFile({ outFile, fetchImpl, sleep: async () => {}, logger });

    assert.equal(res.status, 'degraded');
    assert.equal(res.exitCode, 0);
    assert.ok(res.error.includes('0 of 50 rows valid'));

    const preserved = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(preserved.companies.length, 100);
    assert.equal(preserved.stale, true);
    assert.ok(preserved.lastError.includes('failed normalization on page 1'));
    assert.ok(logger.warns.some(w => w.includes('kept previous data and marked it stale')));
  });
});

test('first-page where all rows fail normalization with no prior snapshot fails with exit code 1', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    const fetchImpl = async () => Response.json({
      data: [{ invalid: 'row' }, { bad: 'record' }]
    });
    const logger = makeLogger();
    const res = await updateMarketFile({ outFile, fetchImpl, sleep: async () => {}, logger });

    assert.equal(res.status, 'missing_snapshot');
    assert.equal(res.exitCode, 1);
    assert.ok(res.error.includes('0 of 2 rows valid'));
    assert.equal(fs.existsSync(outFile), false);
  });
});

test('first-page where all rows fail normalization fails with exit code 1 in strict mode', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    fs.writeFileSync(outFile, JSON.stringify({
      source: 'StartupDB',
      stale: false,
      companies: [company(1)],
      details: {}
    }));

    const fetchImpl = async () => Response.json({
      data: [{ invalid: 'row' }]
    });
    const logger = makeLogger();
    const res = await updateMarketFile({
      outFile,
      strict: true,
      fetchImpl,
      sleep: async () => {},
      logger
    });

    assert.equal(res.status, 'degraded');
    assert.equal(res.exitCode, 1);

    const preserved = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(preserved.companies.length, 1);
    assert.equal(preserved.stale, true);
    assert.ok(logger.errors.some(e => e.includes('Strict mode enabled')));
  });
});

test('later-page where all rows fail normalization halts pagination and preserves complete prior snapshot', async () => {
  await withTempDir(async (dir) => {
    const outFile = path.join(dir, 'market.json');
    fs.writeFileSync(outFile, JSON.stringify({
      source: 'StartupDB',
      stale: false,
      companies: Array.from({ length: 100 }, (_, i) => company(i)),
      details: {}
    }));

    // Page 0 returns 50 valid companies; Page 1 returns 50 malformed companies
    const fetchImpl = async (url) => {
      const offset = Number(new URL(url).searchParams.get('offset'));
      if (offset === 0) {
        return Response.json({
          data: Array.from({ length: 50 }, (_, i) => company(i + 500)),
          pagination: { total: 200 }
        });
      }
      return Response.json({
        data: Array.from({ length: 50 }, () => ({ malformed: 'row' }))
      });
    };

    const logger = makeLogger();
    const res = await updateMarketFile({ outFile, pages: 3, fetchImpl, sleep: async () => {}, logger });

    assert.equal(res.status, 'degraded');
    assert.equal(res.exitCode, 0);
    assert.ok(res.error.includes('Pagination failed on later page'));
    assert.ok(res.error.includes('failed normalization on page 2'));

    const preserved = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(preserved.companies.length, 100);
    assert.equal(preserved.stale, true);
    assert.ok(preserved.lastError.includes('failed normalization on page 2'));
  });
});
