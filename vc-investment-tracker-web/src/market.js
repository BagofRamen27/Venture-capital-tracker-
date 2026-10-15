import fs from 'node:fs';
import path from 'node:path';

/* StartupDB adapter used by the daily data update (scripts/update-market.mjs).
   StartupDB facts are published under CC BY 4.0; attribution and source links are kept. */
export const API = 'https://startupdb.com/api/v1/startups';

const text = (v, max = 250) => typeof v === 'string' ? v.slice(0, max) : '';
export function safeURL(value) {
  try { const u = new URL(value); if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password) return ''; return u.href; } catch { return ''; }
}
const amount = a => a && a.original !== null && Number.isFinite(Number(a.original))
  ? { value: Number(a.original), currency: text(a.currency, 8), qualifier: text(a.qualifier, 30) } : null;

export function normalizeCompany(c) {
  if (!c || !c.slug || !c.name) throw Error('Invalid company response');
  return {
    slug: text(c.slug, 150), name: text(c.name, 160), website: safeURL(c.websiteUrl || ''),
    industry: text(c.profile?.sectorTags?.[0]?.value || c.profile?.sourceIndustryLabels?.[0]?.value || 'Other', 100),
    location: text(c.profile?.headquartersLocation), stage: text(c.latestFunding?.roundLabel || c.fundingHistory?.[0]?.roundLabel || 'Not disclosed', 60),
    latestDate: text(c.latestFundingDate, 30), latestAmount: amount(c.latestFunding?.amount), source: 'StartupDB',
    sourceURL: 'https://startupdb.com/organizations/' + encodeURIComponent(c.slug),
  };
}

export function normalizeDetail(j) {
  const c = j.data;
  const rounds = (c.fundingHistory || []).map(r => ({
    date: text(r.eventDate, 40), stage: text(r.roundLabel, 80), amount: amount(r.amount), amountMeaning: text(r.amountMeaning, 60),
    status: text(r.eventStatus, 60), sources: (r.sourceUrls || []).map(safeURL).filter(Boolean).slice(0, 8),
    investors: (r.participants || []).map(i => ({ name: text(i.name, 120), role: text(i.role, 40) })), attribution: text(r.attribution, 60),
  }));
  return {
    ...normalizeCompany(c), totalRaised: text(c.fundingTotalRaised, 100), lastSyncedAt: text(c.lastSyncedAt, 100), rounds,
    roundsTotal: c.fundingHistoryTotal ?? rounds.length, valuation: null, revenue: null,
    coverage: 'This feed supplies reported funding rounds, not structured valuations or revenue. Missing data is not zero.',
    disclosures: (c.scopeDisclosures || []).map(x => typeof x === 'string' ? x : JSON.stringify(x)).slice(0, 10),
  };
}

/* Download the newest `pages` x 50 companies and up to `detailLimit` funding histories.
   Pauses between requests; a failed detail is skipped, a failed list page stops paging. */
export async function fetchMarket({ pages = 4, detailLimit = 200, fetchImpl = fetch, pauseMs = 1000, sleep = ms => new Promise(r => setTimeout(r, ms)) } = {}) {
  const get = async url => {
    const r = await fetchImpl(url, { headers: { Accept: 'application/json', 'User-Agent': 'VentureScout/1.0 (open-source research site; https://github.com/BagofRamen27/Venture-capital-tracker-)' }, signal: AbortSignal.timeout(20000) });
    if (!r.ok) throw Error('StartupDB returned HTTP ' + r.status);
    return r.json();
  };
  const companies = [], details = {}, errors = [];
  let total = null;
  let paginationError = null;
  for (let page = 0; page < pages; page++) {
    let j;
    try {
      j = await get(`${API}?limit=50&offset=${page * 50}`);
      if (!Array.isArray(j?.data)) {
        throw Error('StartupDB returned invalid listing payload: missing data array');
      }
    }
    catch (e) {
      if (page === 0) throw e;
      paginationError = e.message;
      errors.push(e.message);
      break;
    }
    total = j.pagination?.total ?? total;
    for (const c of j.data) { try { companies.push(normalizeCompany(c)); } catch { /* skip malformed rows */ } }
    if (j.data.length < 50) break;
    await sleep(pauseMs);
  }
  for (const c of companies.slice(0, detailLimit)) {
    try { details[c.slug] = normalizeDetail(await get(`${API}/${encodeURIComponent(c.slug)}`)); }
    catch (e) { errors.push(c.slug + ': ' + e.message); }
    await sleep(pauseMs);
  }
  return {
    source: 'StartupDB',
    license: 'CC BY 4.0',
    fetchedAt: new Date().toISOString(),
    stale: false,
    total,
    companies,
    details,
    errors: errors.slice(0, 20),
    ...(paginationError ? { paginationError, partial: true } : {}),
  };
}

export function validateSnapshot(data) {
  return Boolean(
    data &&
    typeof data === 'object' &&
    !Array.isArray(data) &&
    Array.isArray(data.companies)
  );
}

export function readSnapshot(filePath, { fsImpl = fs } = {}) {
  if (!fsImpl.existsSync(filePath)) {
    return { exists: false, valid: false, data: null };
  }
  try {
    const raw = fsImpl.readFileSync(filePath, 'utf8');
    const parsed = JSON.parse(raw);
    if (validateSnapshot(parsed)) {
      return { exists: true, valid: true, data: parsed };
    }
    return { exists: true, valid: false, data: null, error: 'Snapshot does not match market schema (missing companies array)' };
  } catch (err) {
    return { exists: true, valid: false, data: null, error: err.message };
  }
}

export function safeWriteJSON(filePath, data, { fsImpl = fs } = {}) {
  const tmp = filePath + '.' + process.pid + '.' + Date.now() + '.tmp';
  const content = JSON.stringify(data);
  fsImpl.mkdirSync(path.dirname(filePath), { recursive: true });
  fsImpl.writeFileSync(tmp, content, 'utf8');
  try {
    fsImpl.renameSync(tmp, filePath);
  } finally {
    try {
      if (fsImpl.existsSync(tmp)) fsImpl.unlinkSync(tmp);
    } catch {}
  }
}

export async function updateMarketFile({
  outFile,
  pages = 4,
  detailLimit = 200,
  strict = false,
  fetchImpl = fetch,
  pauseMs = 1000,
  sleep = ms => new Promise(r => setTimeout(r, ms)),
  now = () => new Date().toISOString(),
  logger = console,
  fsImpl = fs,
} = {}) {
  if (!outFile) throw new Error('outFile is required');
  const existing = readSnapshot(outFile, { fsImpl });
  let data = null;
  let refreshError = null;

  try {
    data = await fetchMarket({ pages, detailLimit, fetchImpl, pauseMs, sleep });
    if (data.paginationError) {
      refreshError = new Error('Pagination failed on later page: ' + data.paginationError);
    }
  } catch (err) {
    refreshError = err;
  }

  if (!refreshError) {
    safeWriteJSON(outFile, data, { fsImpl });
    logger.log(
      `StartupDB: saved ${data.companies.length} companies and ${Object.keys(data.details).length} funding histories` +
      (data.errors.length ? ` (${data.errors.length} skipped)` : '')
    );
    return { status: 'success', exitCode: 0, data };
  }

  const errorMessage = refreshError.message;

  if (existing.exists && !existing.valid) {
    logger.error(`StartupDB unavailable and existing snapshot is corrupt: ${errorMessage} (Snapshot error: ${existing.error})`);
    logger.log(`::warning::StartupDB refresh failed and existing snapshot is corrupt: ${errorMessage}`);
    return { status: 'corrupt_snapshot', exitCode: 1, error: errorMessage };
  }

  if (existing.exists && existing.valid) {
    const updated = {
      ...existing.data,
      stale: true,
      lastError: errorMessage,
      lastAttemptAt: now(),
    };
    safeWriteJSON(outFile, updated, { fsImpl });
    logger.warn(`StartupDB unavailable; kept previous data and marked it stale: ${errorMessage}`);
    logger.log(`::warning::StartupDB refresh failed (${errorMessage}); retained previous snapshot marked stale`);
    if (strict) {
      logger.error(`Strict mode enabled: market refresh failed with exit code 1`);
      return { status: 'degraded', exitCode: 1, error: errorMessage, data: updated };
    }
    return { status: 'degraded', exitCode: 0, error: errorMessage, data: updated };
  }

  logger.error(`StartupDB unavailable and no previous data exists: ${errorMessage}`);
  logger.log(`::warning::StartupDB refresh failed and no previous data exists: ${errorMessage}`);
  return { status: 'missing_snapshot', exitCode: 1, error: errorMessage };
}
