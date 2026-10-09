/* VentureScout shared logic: saved companies (browser storage) and filtering of the daily data files.
   Pure functions only, so they run in the browser and in `node --test`. */
(function (root) {
  const STORAGE_KEY = 'venturescout.companies.v1';
  const STAGES = ['Not disclosed', 'Pre-seed', 'Seed', 'Series A', 'Series B', 'Series C+', 'Growth', 'Bootstrapped'];

  function safeURL(value) {
    try {
      const u = new URL(value);
      if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password) return '';
      return u.href;
    } catch { return ''; }
  }

  // Hall of contributors: entries come from public/contributors/contributors.json (added by pull request).
  const CONTRIBUTOR_PHOTO_MAX_BYTES = 300 * 1024;
  function validateContributor(input) {
    const clean = (key, max) => typeof input?.[key] === 'string' ? input[key].trim().slice(0, max) : '';
    const name = clean('name', 60);
    if (!name) throw new Error('Each contributor needs a name.');
    const github = clean('github', 39);
    if (github && !/^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/.test(github)) throw new Error(`${name}: "github" must be a GitHub username.`);
    // Photos must be files in public/contributors/, never links to other sites.
    const photo = clean('photo', 80);
    if (photo && !/^[a-z0-9][a-z0-9._-]*\.(jpe?g|png|webp)$/i.test(photo)) throw new Error(`${name}: "photo" must be a .jpg, .png or .webp file name in public/contributors/.`);
    const joined = clean('joined', 10);
    if (joined && !/^\d{4}-\d{2}(-\d{2})?$/.test(joined)) throw new Error(`${name}: "joined" must look like 2026-10.`);
    return { name, role: clean('role', 40) || 'Contributor', github, photo, joined, contribution: clean('contribution', 200) };
  }

  // Map view: startups with a looked-up city (places.json) become points; the rest are left off the map.
  function formatMoney(a) {
    if (!a || a.value == null) return '';
    const q = a.qualifier && a.qualifier !== 'exact' ? a.qualifier + ' ' : '';
    return q + (a.currency || '') + ' ' + Number(a.value).toLocaleString('en-US', { maximumFractionDigits: 0 });
  }
  function mapPoints(discovery, market, places) {
    const points = [], seen = new Set();
    const add = (p, loc) => {
      const key = p.name.trim().toLowerCase();
      if (!loc || !Number.isFinite(loc.lat) || !Number.isFinite(loc.lon) || seen.has(key)) return;
      seen.add(key);
      points.push({ ...p, lat: loc.lat, lon: loc.lon, place: loc.place || '', country: loc.country || '' });
    };
    for (const c of discovery?.companies || []) {
      const lf = c.latest_funding || {}, tf = c.total_funding || {};
      add({ kind: 'discovery', id: c.id, name: c.name || '', industry: c.industry || '', stage: c.funding_stage || '',
        amount: lf.amount != null ? 'Latest round ' + lf.display : tf.amount != null ? 'Total ' + tf.display : '' },
        places?.discovery?.[String(c.id)]);
    }
    for (const c of market?.companies || []) {
      add({ kind: 'market', id: c.slug, name: c.name || '', industry: (c.industry || '').replaceAll('_', ' '), stage: c.stage || '',
        amount: c.latestAmount?.value != null ? 'Latest round ' + formatMoney(c.latestAmount) : '', url: safeURL(c.sourceURL || ''),
        detail: Boolean(market.details?.[c.slug]) },
        places?.market?.[c.slug]);
    }
    return points;
  }
  function filterMapPoints(points, f = {}) {
    const q = (f.q || '').trim().toLowerCase();
    return points.filter(p => (!q || [p.name, p.industry, p.place].some(v => v.toLowerCase().includes(q)))
      && (!f.country || p.country === f.country) && (!f.industry || p.industry.toLowerCase() === f.industry.toLowerCase()));
  }

  function companyIdentity(record) { return new URL(record.website).hostname.toLowerCase().replace(/^www\./, ''); }

  function validateCompany(input) {
    const clean = (key, max) => typeof input[key] === 'string' ? input[key].trim().slice(0, max) : '';
    const name = clean('name', 140), website = safeURL(clean('website', 500));
    if (!name) throw new Error('Enter a company name.');
    if (!website) throw new Error('Enter a valid company website starting with https:// or http://.');
    return {
      name, website, industry: clean('industry', 80) || 'Other', location: clean('location', 140),
      stage: STAGES.includes(input.stage) ? input.stage : 'Not disclosed', notes: clean('notes', 2000),
      source: clean('source', 60) || 'Added by you', sourceURL: safeURL(clean('sourceURL', 600)),
      checkedAt: new Date().toISOString(),
    };
  }

  function loadSaved(storage) {
    try {
      const list = JSON.parse(storage.getItem(STORAGE_KEY) || '[]');
      return Array.isArray(list) ? list.filter(c => c && c.id && c.name && safeURL(c.website)) : [];
    } catch { return []; }
  }

  function writeSaved(storage, list) { storage.setItem(STORAGE_KEY, JSON.stringify(list)); }

  /* Add or update a company. Throws on invalid input or a duplicate website. Returns the new list. */
  function upsertCompany(list, input, now = new Date().toISOString(), newId = () => 'VS-' + Math.random().toString(36).slice(2, 10)) {
    const record = validateCompany(input), identity = companyIdentity(record);
    const duplicate = list.find(c => companyIdentity(c) === identity && c.id !== input.id);
    if (duplicate) throw new Error('You are already tracking this website (' + duplicate.name + ').');
    if (input.id) {
      if (!list.some(c => c.id === input.id)) throw new Error('Startup not found.');
      return list.map(c => c.id === input.id ? { ...c, ...record, id: c.id, createdAt: c.createdAt, updatedAt: now } : c);
    }
    return [{ ...record, id: newId(), createdAt: now, updatedAt: now }, ...list];
  }

  function removeCompany(list, id) { return list.filter(c => c.id !== id); }

  /* Merge a backup file into the list; skips invalid rows and websites already saved. */
  function importBackup(list, data) {
    const rows = Array.isArray(data) ? data : Array.isArray(data?.companies) ? data.companies : null;
    if (!rows) throw new Error('This file is not a VentureScout backup.');
    let out = list, added = 0, skipped = 0;
    for (const row of rows) {
      try { out = upsertCompany(out, { ...row, id: undefined }, row.createdAt || undefined); added++; } catch { skipped++; }
    }
    return { list: out, added, skipped };
  }

  function filterDiscovery(companies, f = {}) {
    const q = (f.q || '').trim().toLowerCase();
    let out = companies.filter(c =>
      (!q || [c.name, c.description, c.industry, c.headquarters].some(v => (v || '').toLowerCase().includes(q))) &&
      (!f.industry || c.industry === f.industry) &&
      (!f.stage || c.funding_stage === f.stage) &&
      (!f.evidence || c.latest_funding?.evidence_status === f.evidence) &&
      (f.minConfidence == null || f.minConfidence === '' || (c.confidence?.score ?? -1) >= Number(f.minConfidence)) &&
      (f.minScore == null || f.minScore === '' || (c.investment_score?.total ?? -1) >= Number(f.minScore)));
    const by = {
      newest: (a, b) => (b.first_discovered_at || '').localeCompare(a.first_discovered_at || ''),
      score: (a, b) => (b.investment_score?.total ?? -1) - (a.investment_score?.total ?? -1),
      confidence: (a, b) => (b.confidence?.score ?? -1) - (a.confidence?.score ?? -1),
      funding: (a, b) => (b.latest_funding?.amount ?? -1) - (a.latest_funding?.amount ?? -1),
      name: (a, b) => a.name.localeCompare(b.name),
    }[f.sort || 'newest'];
    return [...out].sort(by);
  }

  function searchMarket(companies, q) {
    const s = (q || '').trim().toLowerCase();
    if (!s) return companies;
    return companies.filter(c => [c.name, c.website, c.industry, c.location].some(v => (v || '').toLowerCase().includes(s)));
  }

  root.VentureScout = { STORAGE_KEY, STAGES, CONTRIBUTOR_PHOTO_MAX_BYTES, validateContributor, formatMoney, mapPoints, filterMapPoints, safeURL, companyIdentity, validateCompany, loadSaved, writeSaved,
    upsertCompany, removeCompany, importBackup, filterDiscovery, searchMarket };
})(typeof window !== 'undefined' ? window : globalThis);
