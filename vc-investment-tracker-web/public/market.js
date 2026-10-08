/* Dashboard and Financials views. Data comes from static files refreshed once a day by GitHub Actions:
   data/market.json (StartupDB funding records) and data/news.json (classified funding headlines). */
window.createMarketUI = function ({ esc, render, track, count }) {
  const PAGE = 50;
  const m = { q: '', offset: 0, market: null, marketError: '', news: null, newsError: '', loading: false, loaded: false, slug: '' };
  const active = () => ['#dashboard', '#financials', '', '#'].includes(location.hash);
  const redraw = () => { if (active()) render(); };
  const cash = a => a && a.value != null ? (a.qualifier && a.qualifier !== 'exact' ? esc(a.qualifier) + ' ' : '') + esc(a.currency) + ' ' + Number(a.value).toLocaleString(undefined, { maximumFractionDigits: 0 }) : 'Not disclosed';
  const credit = `<p class="note">Funding facts: <a href="https://startupdb.com" target="_blank" rel="noopener">StartupDB</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a>. Reformatted for VentureScout. Coverage is incomplete; source-reported figures are not independently verified here.</p>`;
  const when = d => d ? new Date(d).toLocaleString() : 'unknown time';
  const freshness = d => d ? `<p class="note">Updated ${esc(when(d.fetchedAt || d.generated_at))}${d.stale ? ` · The source was unavailable at the last update (${esc(when(d.lastAttemptAt))}); showing the previous data` : ''}. Refreshed automatically once a day.</p>` : '';

  async function getJSON(file) {
    const r = await fetch('data/' + file, { cache: 'no-cache' });
    if (r.status === 404) throw Error('Not available yet: the first daily update has not run.');
    if (!r.ok) throw Error('Could not load ' + file + '.');
    return r.json();
  }
  async function load() {
    if (m.loading || m.loaded) return;
    m.loading = true; redraw();
    const [market, news] = await Promise.allSettled([getJSON('market.json'), getJSON('news.json')]);
    if (market.status === 'fulfilled') m.market = market.value; else m.marketError = market.reason.message;
    if (news.status === 'fulfilled') m.news = news.value; else m.newsError = news.reason.message;
    m.loading = false; m.loaded = true; redraw();
  }
  const matches = () => m.market ? window.VentureScout.searchMarket(m.market.companies, m.q) : [];
  const detail = () => m.market && m.slug ? m.market.details?.[m.slug] || null : null;

  function search() { return `<form id="market-search" class="panel scout-search"><label>Find a company<input name="q" value="${esc(m.q)}" maxlength="100" placeholder="Company name, website, industry or city"></label><button class="btn primary">Search companies</button></form>`; }
  function listings() {
    if (m.loading) return '<p role="status">Loading company records…</p>';
    if (m.marketError) return `<p class="panel" role="alert">${esc(m.marketError)}</p>`;
    if (!m.market) return '';
    const all = matches(), page = all.slice(m.offset, m.offset + PAGE);
    return `${freshness(m.market)}<p>${all.length.toLocaleString()} of the ${m.market.companies.length.toLocaleString()} most recently funded companies${m.market.total ? ` (StartupDB lists ${esc(m.market.total.toLocaleString())} in total)` : ''}${all.length ? ` · showing ${m.offset + 1}–${m.offset + page.length}` : ''}</p>
    <div class="scout-grid">${page.map(c => `<article class="panel scout-card"><span class="eyebrow">${esc(c.industry.replaceAll('_', ' '))}</span><h2>${esc(c.name)}</h2><p>${esc(c.location || 'Location not disclosed')}</p><dl class="market-facts"><dt>Latest reported round</dt><dd>${esc(c.stage)} · ${cash(c.latestAmount)}</dd><dt>Round date</dt><dd>${esc(c.latestDate || 'Not disclosed')}</dd></dl><div class="controls">${m.market.details?.[c.slug] ? `<button class="btn primary" data-market-detail="${esc(c.slug)}">Funding & financials</button>` : `<a class="btn" href="${esc(c.sourceURL)}" target="_blank" rel="noopener">View on StartupDB</a>`}<button class="btn" data-market-track="${esc(c.slug)}">Track</button></div></article>`).join('') || '<p class="panel">No matching companies in today\'s data. Try another name, or search StartupDB directly.</p>'}</div>
    <div class="scout-pagination"><button class="btn" data-market-offset="${Math.max(0, m.offset - PAGE)}" ${m.offset === 0 ? 'disabled' : ''}>Previous</button><span>Page ${Math.floor(m.offset / PAGE) + 1}</span><button class="btn" data-market-offset="${m.offset + PAGE}" ${m.offset + PAGE >= all.length ? 'disabled' : ''}>Next</button></div>`;
  }
  function newsPanel() {
    const n = m.news;
    return `<section class="panel"><h2>Funding & startup news</h2>${m.newsError ? `<p role="alert">${esc(m.newsError)}</p>` : ''}${n ? `${freshness(n)}<div class="news-list">${n.articles.slice(0, 25).map(a => `<article><a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">${esc(a.title)}</a><p class="muted">${esc(a.publisher || 'Source')} · ${esc(a.published_at ? new Date(a.published_at + 'Z').toLocaleDateString() : 'Date not supplied')}${a.event_types?.length ? ' · ' + a.event_types.map(esc).join(', ') : ''}${a.companies?.length ? ' · ' + a.companies.map(esc).join(', ') : ''}</p></article>`).join('') || '<p>No headlines yet.</p>'}</div><p class="note">Headlines link to the original reporting; publication time is not the date a round closed. Event tags come from keyword rules and describe the headline, not investment quality.</p>` : ''}</section>`;
  }
  function dashboard() {
    queueMicrotask(load);
    return `<div class="pagehead"><div><span class="eyebrow">Daily source data</span><h1>Startup market</h1><p>Explore reported funding activity and discover companies to track.</p></div><button class="btn" data-nav="discover">Discovered startups</button></div>
    <section class="kpis"><div class="kpi"><span class="v">${m.market ? esc(m.market.companies.length.toLocaleString()) : '—'}</span><span class="l">Recently funded companies</span><span class="s">StartupDB coverage, not the entire market</span></div><div class="kpi"><span class="v">${count()}</span><span class="l">Your saved startups</span><span class="s">Saved in this browser</span></div><div class="kpi"><span class="v">${m.news?.articles.length ?? '—'}</span><span class="l">Recent headlines</span><span class="s">News feeds, classified daily</span></div></section>
    <p class="note">These are daily source records, not real-time prices. Private-company revenue and valuation are not supplied by these feeds.</p>${search()}${listings()}${credit}${newsPanel()}`;
  }
  function financials() {
    queueMicrotask(load);
    const d = detail();
    return `<div class="pagehead"><div><h1>Funding & financials</h1><p>Search a company and inspect its reported rounds and underlying sources.</p></div></div>${search()}${m.slug && !d && m.loaded ? '<section class="panel" role="alert">No funding history was downloaded for this company today. Use its StartupDB link instead.</section>' : ''}${d ? `<section class="panel"><h2>${esc(d.name)}</h2><p>${esc(d.location)} · ${esc(d.stage)}</p>${freshness(m.market)}<p class="note">Source last checked this company: ${esc(d.lastSyncedAt || 'Not supplied')}</p><div class="kpis"><div class="kpi"><span class="v">${esc(d.totalRaised || 'Not disclosed')}</span><span class="l">Total funding reported by source</span></div><div class="kpi"><span class="v">Not supplied</span><span class="l">Valuation</span></div><div class="kpi"><span class="v">Not supplied</span><span class="l">Revenue</span></div></div><p class="note">${esc(d.coverage)} Funding raised is not valuation, revenue, or cash balance.</p><div class="controls"><a class="btn" href="${esc(d.sourceURL)}" target="_blank" rel="noopener">View source profile</a><button class="btn primary" id="track-market-detail">Track company</button></div><h3>Reported funding rounds (${d.rounds.length} shown of ${esc(d.roundsTotal)})</h3>${d.rounds.map(r => `<article class="funding-round"><h3>${esc(r.stage || 'Round not specified')} · ${cash(r.amount)}</h3><p>${esc(r.date || 'Date not supplied')} · ${esc(r.amountMeaning || 'Amount meaning not supplied')} · Status: ${esc(r.status || 'Not supplied')}</p><p>${r.investors.map(i => esc(i.name) + ' (' + esc(i.role) + ')').join(', ') || 'Investors not supplied'}</p><p>${r.sources.map((s, i) => `<a href="${esc(s)}" target="_blank" rel="noopener noreferrer">Source ${i + 1}</a>`).join(' · ') || 'No underlying source link supplied'}</p><p class="muted">Source classification: ${esc(r.attribution || 'Unspecified')}</p></article>`).join('') || '<p>No rounds supplied; this does not establish that no funding occurred.</p>'}${d.disclosures.length ? `<details><summary>Source coverage notes</summary>${d.disclosures.map(s => `<p>${esc(s)}</p>`).join('')}</details>` : ''}</section>` : ''}${credit}${listings()}`;
  }
  const findCompany = slug => m.market?.details?.[slug] || m.market?.companies.find(c => c.slug === slug);
  document.addEventListener('submit', e => { if (e.target.id === 'market-search') { e.preventDefault(); m.q = String(new FormData(e.target).get('q') || ''); m.offset = 0; render(); } });
  document.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.marketDetail) { m.slug = b.dataset.marketDetail; location.hash = 'financials'; render(); scrollTo(0, 0); }
    if (b.dataset.marketTrack !== undefined) track(findCompany(b.dataset.marketTrack));
    if (b.id === 'track-market-detail') track(detail());
    if (b.dataset.marketOffset !== undefined) { m.offset = Number(b.dataset.marketOffset); render(); scrollTo(0, 0); }
  });
  return { dashboard, financials };
};
