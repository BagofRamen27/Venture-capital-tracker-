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

  const STATUS_KEY = 'venturescout.migration.status';

  const SHARED_HOSTS = new Set([
    'github.com',
    'gitlab.com',
    'github.io',
    'gitlab.io',
    'pages.dev',
    'netlify.app',
    'vercel.app',
    'substack.com',
    'medium.com',
    'notion.site',
    'linktr.ee',
    'linkedin.com',
    'twitter.com',
    'x.com',
    'facebook.com',
    'instagram.com',
    'youtube.com',
    'huggingface.co',
  ]);

  const REPO_HOSTS = new Set([
    'github.com',
    'gitlab.com',
    'huggingface.co',
  ]);

  const MULTI_LEVEL_TLDS = new Set([
    'co.uk', 'org.uk', 'gov.uk', 'ac.uk', 'me.uk', 'ltd.uk', 'plc.uk',
    'com.au', 'net.au', 'org.au', 'edu.au', 'gov.au',
    'co.nz', 'net.nz', 'org.nz',
    'co.jp', 'ne.jp', 'or.jp',
    'co.in', 'net.in', 'org.in', 'gen.in', 'firm.in', 'ind.in',
    'com.br', 'net.br', 'org.br',
    'com.sg', 'edu.sg', 'gov.sg',
    'co.za', 'org.za',
    'com.mx', 'org.mx',
  ]);

  function registrableDomain(value) {
    if (!value || typeof value !== 'string') return '';
    try {
      const u = new URL(value);
      if (!['http:', 'https:'].includes(u.protocol)) return '';
      if (u.username || u.password) return '';
      let host = u.hostname.toLowerCase();
      if (!host) return '';
      if (host.endsWith('.')) host = host.slice(0, -1);
      if (host.startsWith('www.')) host = host.slice(4);
      if (!host) return '';
      if (/^(\d{1,3}\.){3}\d{1,3}$/.test(host) || !host.includes('.')) return host;
      const parts = host.split('.');
      if (parts.length >= 3) {
        const twoLevel = parts.slice(-2).join('.');
        if (MULTI_LEVEL_TLDS.has(twoLevel)) {
          return parts.slice(-3).join('.');
        }
      }
      return parts.slice(-2).join('.');
    } catch {
      return '';
    }
  }

  function canonicalCompanyKey(company) {
    if (!company || typeof company !== 'object') return '';
    const rawCik = company.secCik ?? company.cik ?? company.sec_cik;
    if (rawCik != null && rawCik !== '') {
      const str = String(rawCik).trim();
      // Valid CIK format policy: optional 'CIK' prefix (with optional colon/space),
      // digits optionally separated by single hyphens or spaces (e.g. '0000320193', '32-0193', 'CIK 0000320193').
      // Arbitrary alphabetic characters, negative numbers, or malformed prefixes are strictly rejected.
      const match = str.match(/^(?:CIK\s*:?\s*)?(\d+(?:[\- ]\d+)*)$/i);
      if (match) {
        const digits = match[1].replace(/[\- ]/g, '');
        if (digits.length > 0 && digits.length <= 10 && Number(digits) > 0) {
          return 'cid:cik:' + digits.padStart(10, '0');
        }
      }
    }

    const website = typeof company.website === 'string' ? company.website.trim() : '';
    if (website) {
      const regDom = registrableDomain(website);
      if (regDom) {
        if (SHARED_HOSTS.has(regDom)) {
          try {
            const u = new URL(website);
            let host = u.hostname.toLowerCase().replace(/^www\./, '');
            if (host !== regDom && host.endsWith('.' + regDom)) {
              const sub = host.slice(0, -(regDom.length + 1));
              return 'cid:shared:' + regDom + '/' + sub;
            }
            const segs = u.pathname.split('/').filter(Boolean);
            if (segs.length > 0) {
              if (regDom === 'gitlab.com') {
                // GitLab projects support nested subgroup hierarchies (/group/subgroup/.../project).
                // GitLab internal feature views start with /-/ (e.g. /-/tree/main, /-/blob/main).
                const dashIndex = segs.indexOf('-');
                const projSegs = dashIndex !== -1 ? segs.slice(0, dashIndex) : segs;
                if (projSegs.length > 0) {
                  const parts = projSegs.map(s => s.toLowerCase());
                  parts[parts.length - 1] = parts[parts.length - 1].replace(/\.git$/i, '');
                  return 'cid:shared:' + regDom + '/' + parts.join('/');
                }
                return 'cid:shared:' + regDom;
              }
              // Code repository platforms with fixed 2-segment owner/repo paths (e.g. GitHub, Hugging Face).
              // Deeper subpaths (e.g. /tree/main), query parameters, and fragments are intentionally ignored.
              if (REPO_HOSTS.has(regDom) && segs.length >= 2) {
                const org = segs[0].toLowerCase();
                const repo = segs[1].toLowerCase().replace(/\.git$/i, '');
                return 'cid:shared:' + regDom + '/' + org + '/' + repo;
              }
              // Non-repository platforms (blogs, social handles, user spaces) use single-segment tenant identity.
              const tenant = segs[0].toLowerCase();
              return 'cid:shared:' + regDom + '/' + tenant;
            }
            return 'cid:shared:' + regDom;
          } catch {
            return 'cid:shared:' + regDom;
          }
        }
        return 'cid:domain:' + regDom;
      }
    }

    const rawName = typeof company.name === 'string' ? company.name : typeof company.company_name === 'string' ? company.company_name : '';
    const cleanName = rawName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    if (cleanName) {
      const rawLoc = typeof company.location === 'string' ? company.location : typeof company.hq_city === 'string' ? company.hq_city : typeof company.headquarters === 'string' ? company.headquarters : '';
      const cleanLoc = rawLoc.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
      return 'cid:name:' + cleanName + (cleanLoc ? ':' + cleanLoc : '');
    }

    return '';
  }

  function companyIdentity(record) {
    if (!record || !record.website) return '';
    try {
      const key = canonicalCompanyKey(record);
      if (key && !key.startsWith('cid:name:')) return key;
      return new URL(record.website).hostname.toLowerCase().replace(/^www\./, '');
    } catch {
      return '';
    }
  }

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
    const canonicalKey = canonicalCompanyKey({ ...record, ...input });
    if (input.id) {
      if (!list.some(c => c.id === input.id)) throw new Error('Startup not found.');
      return list.map(c => c.id === input.id ? { ...c, ...record, id: c.id, createdAt: c.createdAt, updatedAt: now, ...(canonicalKey ? { canonicalKey } : {}) } : c);
    }
    return [{ ...record, id: newId(), createdAt: now, updatedAt: now, ...(canonicalKey ? { canonicalKey } : {}) }, ...list];
  }

  function removeCompany(list, id) { return list.filter(c => c.id !== id); }

  /* Merge a backup file into the list; skips invalid rows and websites already saved. */
  function importBackup(list, data) {
    const rows = Array.isArray(data) ? data : Array.isArray(data?.companies) ? data.companies : null;
    if (!rows) throw new Error('This file is not a VentureScout backup.');
    let out = list, added = 0, skipped = 0;
    const existingIds = new Set(list.map(c => c.id));

    for (const row of rows) {
      try {
        const record = validateCompany(row);
        const identity = companyIdentity(record);
        const duplicate = out.find(c => companyIdentity(c) === identity);
        if (duplicate) {
          skipped++;
          continue;
        }

        let targetId = typeof row.id === 'string' && row.id.trim() ? row.id.trim() : null;
        if (targetId) {
          if (existingIds.has(targetId)) {
            let suffix = 1;
            let candidate = `${targetId}-imported`;
            while (existingIds.has(candidate)) {
              suffix++;
              candidate = `${targetId}-imported-${suffix}`;
            }
            targetId = candidate;
          }
        } else {
          let candidate = 'VS-' + Math.random().toString(36).slice(2, 10);
          while (existingIds.has(candidate)) {
            candidate = 'VS-' + Math.random().toString(36).slice(2, 10);
          }
          targetId = candidate;
        }

        existingIds.add(targetId);
        const now = new Date().toISOString();
        const createdAt = typeof row.createdAt === 'string' && row.createdAt ? row.createdAt : now;
        const canonicalKey = canonicalCompanyKey({ ...record, ...row });

        out = [{
          ...record,
          id: targetId,
          createdAt,
          updatedAt: now,
          ...(canonicalKey ? { canonicalKey } : {})
        }, ...out];
        added++;
      } catch {
        skipped++;
      }
    }
    return { list: out, added, skipped };
  }

  /* Non-destructively normalizes venturescout.companies.v1 in place, attaching canonicalKey and identifying duplicate candidates. */
  function normalizeWorkspaceStorage(storage) {
    if (!storage || typeof storage.getItem !== 'function' || typeof storage.setItem !== 'function') {
      return { ok: false, error: 'storage_access_denied', message: 'Storage is not accessible.' };
    }

    let raw;
    try {
      raw = storage.getItem(STORAGE_KEY);
    } catch (e) {
      return { ok: false, error: 'storage_read_error', message: e?.message || 'Failed to read from storage.' };
    }

    if (raw === null || raw === undefined) {
      try {
        const marker = { version: 1, phase: 'wp1_identity_normalized', completedAt: new Date().toISOString(), count: 0 };
        storage.setItem(STATUS_KEY, JSON.stringify(marker));
      } catch {}
      return { ok: true, status: 'empty', normalizedCount: 0, duplicateCandidates: [], conflicts: [] };
    }

    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      return { ok: false, error: 'malformed_json', raw, message: 'Existing company data in storage is malformed JSON; raw storage preserved.' };
    }

    if (!Array.isArray(parsed)) {
      return { ok: false, error: 'invalid_data_shape', message: 'Stored company data is not an array; raw storage preserved.' };
    }

    let rawStatus = null;
    try { rawStatus = storage.getItem(STATUS_KEY); } catch {}
    if (rawStatus) {
      try {
        const st = JSON.parse(rawStatus);
        if (st && st.phase === 'wp1_identity_normalized' && st.version === 1) {
          const isConsistent = parsed.every(c => c && typeof c === 'object' && c.id && c.canonicalKey);
          if (isConsistent) {
            return { ok: true, status: 'already_normalized', normalizedCount: parsed.length, duplicateCandidates: [], conflicts: [] };
          }
        }
      } catch {}
    }

    let modified = false;
    const normalizedList = [];
    const seenIds = new Set();
    const canonicalMap = new Map();
    const duplicateCandidates = [];

    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue;
      let id = typeof item.id === 'string' && item.id.trim() ? item.id.trim() : null;
      if (!id || seenIds.has(id)) {
        id = 'VS-' + Math.random().toString(36).slice(2, 10);
        while (seenIds.has(id)) {
          id = 'VS-' + Math.random().toString(36).slice(2, 10);
        }
        modified = true;
      }
      seenIds.add(id);

      const key = canonicalCompanyKey(item);
      if (item.canonicalKey !== key && key) {
        modified = true;
      }

      const enriched = {
        ...item,
        id,
        ...(key ? { canonicalKey: key } : {})
      };
      normalizedList.push(enriched);

      if (key && !key.startsWith('cid:name:')) {
        if (!canonicalMap.has(key)) canonicalMap.set(key, []);
        canonicalMap.get(key).push(enriched);
      }
    }

    for (const [key, group] of canonicalMap.entries()) {
      if (group.length > 1) {
        duplicateCandidates.push({
          canonicalKey: key,
          count: group.length,
          companies: group.map(x => ({ id: x.id, name: x.name, website: x.website }))
        });
      }
    }

    try {
      if (modified || !rawStatus) {
        storage.setItem(STORAGE_KEY, JSON.stringify(normalizedList));
      }
      const marker = {
        version: 1,
        phase: 'wp1_identity_normalized',
        completedAt: new Date().toISOString(),
        count: normalizedList.length,
        duplicateCount: duplicateCandidates.length
      };
      storage.setItem(STATUS_KEY, JSON.stringify(marker));
    } catch (e) {
      return { ok: false, error: 'write_failure', message: e?.message || 'Storage write failed during normalization.' };
    }

    return {
      ok: true,
      status: modified ? 'normalized' : 'consistent',
      normalizedCount: normalizedList.length,
      duplicateCandidates,
      conflicts: duplicateCandidates
    };
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

  root.VentureScout = { STORAGE_KEY, STATUS_KEY, STAGES, CONTRIBUTOR_PHOTO_MAX_BYTES, SHARED_HOSTS, REPO_HOSTS, MULTI_LEVEL_TLDS,
    validateContributor, formatMoney, mapPoints, filterMapPoints, safeURL, companyIdentity, validateCompany, loadSaved, writeSaved,
    registrableDomain, canonicalCompanyKey, normalizeWorkspaceStorage,
    upsertCompany, removeCompany, importBackup, filterDiscovery, searchMarket };
})(typeof window !== 'undefined' ? window : globalThis);
