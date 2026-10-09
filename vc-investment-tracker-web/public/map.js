/* Map view: where the startups in VentureScout are, at the city each record states.
   Data: data/discovery.json, data/market.json and data/places.json (coordinates looked up once a day on
   OpenStreetMap Nominatim). Leaflet and its clustering plugin are bundled in vendor/leaflet and only loaded
   when the map is opened. */
window.createMapUI = function ({ esc, render, isActive, openDiscovered, openMarket }) {
  const VS = window.VentureScout;
  const M = { points: null, error: '', loading: false, f: { q: '', country: '', industry: '' }, map: null, layer: null };
  const TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  const OSM = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors';

  let leaflet = null;
  function loadLeaflet() {
    const add = (tag, attrs) => new Promise((ok, fail) => { const el = Object.assign(document.createElement(tag), attrs); el.onload = ok; el.onerror = () => fail(Error('Could not load the map library.')); document.head.append(el); });
    leaflet ||= add('link', { rel: 'stylesheet', href: 'vendor/leaflet/leaflet.css' })
      .then(() => add('script', { src: 'vendor/leaflet/leaflet.js' }))
      .then(() => Promise.all([add('script', { src: 'vendor/leaflet/leaflet.markercluster.js' }), add('link', { rel: 'stylesheet', href: 'vendor/leaflet/MarkerCluster.css' })]));
    return leaflet;
  }

  async function load() {
    if (M.loading || M.points) return;
    M.loading = true;
    const get = async (f, optional) => { const r = await fetch('data/' + f, { cache: 'no-cache' }); if (r.ok) return r.json(); if (optional) return null; throw Error(r.status === 404 ? 'Map locations are not available yet; they are added by the next daily update.' : 'Could not load ' + f + '.'); };
    try {
      const [places, discovery, market] = await Promise.all([get('places.json'), get('discovery.json', true), get('market.json', true), loadLeaflet()]);
      M.points = VS.mapPoints(discovery, market, places);
      // Unique companies across both sources (a company can be in both), for the "not on the map" count.
      M.total = new Set([...(discovery?.companies || []), ...(market?.companies || [])].map(c => (c.name || '').trim().toLowerCase())).size;
    } catch (e) { M.error = e.message; }
    M.loading = false;
    if (isActive()) render();
  }

  const options = (values, current, all) => `<option value="">${all}</option>` + values.map(v => `<option${v === current ? ' selected' : ''}>${esc(v)}</option>`).join('');
  const uniq = key => [...new Map(M.points.filter(p => p[key]).map(p => [p[key].toLowerCase(), p[key]])).values()].sort((a, b) => a.localeCompare(b));

  function popup(p) {
    const where = p.place || p.country;
    return `<div class="map-card"><strong>${esc(p.name)}</strong>${where ? `<span>${esc(where)}</span>` : ''}
      <dl><dt>Industry</dt><dd>${esc(p.industry || 'Not disclosed')}</dd><dt>Stage</dt><dd>${esc(p.stage || 'Not disclosed')}</dd><dt>Raised</dt><dd>${esc(p.amount || 'Not disclosed')}</dd></dl>
      <button type="button" class="btn primary" data-map-open="${esc(p.kind)}" data-map-id="${esc(p.id)}">View startup</button></div>`;
  }

  function draw(fit) {
    if (!M.map || !M.points) return;
    const shown = VS.filterMapPoints(M.points, M.f);
    M.layer.clearLayers();
    M.layer.addLayers(shown.map(p => L.marker([p.lat, p.lon], { title: p.name, alt: p.name, icon: L.divIcon({ className: 'vs-pin', iconSize: [14, 14] }) }).bindPopup(popup(p), { maxWidth: 260 })));
    if (fit && shown.length) M.map.fitBounds(L.latLngBounds(shown.map(p => [p.lat, p.lon])), { padding: [30, 30], maxZoom: 6 });
    const count = document.getElementById('map-count');
    if (count) count.textContent = `Showing ${shown.length} of ${M.points.length} startups with a known city. ${Math.max(0, M.total - M.points.length)} more have no usable location yet and are not on the map.`;
  }

  function mount() {
    const el = document.getElementById('vs-map');
    if (!el || !window.L || !M.points) return;
    if (M.map && M.map.getContainer() !== el) { M.map.remove(); M.map = null; }
    if (!M.map) {
      M.map = L.map(el, { worldCopyJump: true, scrollWheelZoom: false, minZoom: 2 }).setView([25, 0], 2);
      L.tileLayer(TILES, { maxZoom: 18, attribution: OSM }).addTo(M.map);
      M.map.once('focus', () => M.map.scrollWheelZoom.enable());  // don't hijack page scrolling until the map is used
      M.layer = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45,
        iconCreateFunction: c => L.divIcon({ html: `<span>${c.getChildCount()}</span>`, className: 'vs-cluster', iconSize: [34, 34] }) }).addTo(M.map);
    }
    draw(true);
  }

  function view() {
    queueMicrotask(() => { load(); mount(); });
    const head = `<div class="pagehead"><div><span class="eyebrow">Map</span><h1>Where the startups are</h1><p>Each pin is a startup at the city its record states. Startups without a known city are not placed on the map.</p></div></div>`;
    if (M.error) return head + `<div class="panel" role="alert">${esc(M.error)}</div>`;
    if (!M.points) return head + '<div class="panel" role="status">Loading the map…</div>';
    return head + `<form id="map-filters" class="panel map-filters" role="search">
        <label>Search startups<input name="q" value="${esc(M.f.q)}" maxlength="100" placeholder="Name, industry or city"></label>
        <label>Country<select name="country">${options(uniq('country'), M.f.country, 'All countries')}</select></label>
        <label>Industry<select name="industry">${options(uniq('industry'), M.f.industry, 'All industries')}</select></label>
        <button type="button" class="btn" id="map-reset">Reset</button>
      </form>
      <div id="vs-map" class="vs-map" role="region" aria-label="Map of startup locations"></div>
      <p class="note" id="map-count" aria-live="polite"></p>
      <p class="note">Pins mark the city, not a street address. Locations: OpenStreetMap contributors (Nominatim), from the city each source states.</p>`;
  }

  const setFilters = form => { Object.assign(M.f, Object.fromEntries(new FormData(form))); draw(true); };
  document.addEventListener('input', e => { const f = e.target.closest?.('#map-filters'); if (f && e.target.name === 'q') setFilters(f); });
  document.addEventListener('change', e => { const f = e.target.closest?.('#map-filters'); if (f && e.target.name !== 'q') setFilters(f); });
  document.addEventListener('submit', e => { if (e.target.id === 'map-filters') e.preventDefault(); });
  document.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.id === 'map-reset') { M.f = { q: '', country: '', industry: '' }; b.form.reset(); b.form.querySelectorAll('select').forEach(s => { s.value = ''; }); b.form.q.value = ''; draw(true); }
    if (b.dataset.mapOpen === 'discovery') openDiscovered(Number(b.dataset.mapId));
    if (b.dataset.mapOpen === 'market') openMarket(M.points.find(p => p.kind === 'market' && p.id === b.dataset.mapId));
  });
  return { view };
};
