/* Competitive analysis: compare one startup with the incumbents, rivals and substitutes in its field.
   Everything is entered by the researcher and saved only in this browser (no accounts, no server).
   Scores are deterministic: each factor is rated 0-5 with written evidence, and a score is shown only
   when enough of the factors are evidenced (see score()). The weights are a proposed method from
   docs/competitive-analysis-spec.md (section 5), not an empirically validated model. */
(function (root) {
  const STORAGE_KEY = 'venturescout.analyses.v1';
  const CS = [
    ['diff', 'Product differentiation and customer value', 20],
    ['traction', 'Adoption, traction and evidence of demand', 20],
    ['econ', 'Unit economics and business-model viability', 15],
    ['moat', 'Defensibility and moats', 20],
    ['gtm', 'Distribution and go-to-market', 15],
    ['exec', 'Ability to execute under regulatory and capital constraints', 10],
  ];
  const DP = [
    ['segment', 'Starts with underserved customers or non-consumers', 20],
    ['access', 'Shift in access, affordability or convenience', 20],
    ['model', 'Structural business-model advantage', 20],
    ['upmarket', 'Plausible path upmarket or into adjacent markets', 15],
    ['disincentive', 'Incumbents have reasons not to respond', 15],
    ['substitution', 'Evidence of expanding adoption or substitution', 10],
  ];
  const ROLES = ['Established leader', 'Direct startup rival', 'Indirect substitute', 'Adjacent giant', 'Doing nothing (inertia)'];
  const EXPOSURE = ['unknown', 'low', 'moderate', 'high'];
  const FORCES = [['rivalry', 'Rivalry among existing competitors'], ['entrants', 'Threat of new entrants'], ['substitutes', 'Threat of substitutes'],
    ['buyers', 'Buyer power'], ['suppliers', 'Supplier power']];
  const LEVELS = ['Unknown', 'Low', 'Medium', 'High'];
  const CHRISTENSEN = [['lowend', 'Starts with overserved low-end customers or people who were not buying at all?'],
    ['worse', 'Worse on the incumbents’ main measure but better on a new one (price, convenience, access)?'],
    ['ignore', 'Do incumbents have a rational profit reason to ignore it?'], ['upmarket', 'Is there a clear path to improve and move upmarket?']];
  const TYPES = [['insufficient_evidence', 'Insufficient evidence'], ['low_end_disruption', 'Low-end disruption'], ['new_market_disruption', 'New-market disruption'],
    ['sustaining_innovation', 'Sustaining innovation (better product for mainstream customers)'], ['other_structural_innovation', 'Other structural innovation'],
    ['feature_risk', 'Feature risk (an incumbent could ship it as a feature)']];
  const FIELDS = [['use', 'Core use case'], ['buyers', 'Target buyers'], ['pricing', 'Entry pricing (currency, unit, date)'], ['capabilities', 'Key capabilities'],
    ['revenue', 'Revenue / growth (period)'], ['moat', 'Moat'], ['switching', 'Switching costs'], ['regulation', 'Regulatory constraints']];
  const MAX_COMPETITORS = 6;

  const str = (v, max) => typeof v === 'string' ? v.slice(0, max) : '';
  const pick = (v, list, fallback) => list.includes(v) ? v : fallback;
  const url = v => { try { const u = new URL(str(v, 600)); return ['http:', 'https:'].includes(u.protocol) && !u.username && !u.password ? u.href : ''; } catch { return ''; } };
  const factor = f => ({ rating: pick(String(f?.rating ?? ''), ['', '0', '1', '2', '3', '4', '5'], ''), evidence: str(f?.evidence, 1000), source: str(f?.source, 600), self: f?.self === true });
  const factors = (defs, input) => Object.fromEntries(defs.map(([k]) => [k, factor(input?.[k])]));

  function newAnalysis(now = new Date().toISOString(), id = 'CA-' + Math.random().toString(36).slice(2, 10)) {
    return normalize({ id, createdAt: now, updatedAt: now });
  }

  /* Clean a stored or imported analysis: unknown keys are dropped, text is length-capped, choices are validated. */
  function normalize(a) {
    a = a && typeof a === 'object' ? a : {};
    const s = a.startup || {};
    return {
      id: str(a.id, 40) || 'CA-' + Math.random().toString(36).slice(2, 10), createdAt: str(a.createdAt, 40), updatedAt: str(a.updatedAt, 40),
      startup: { name: str(s.name, 140), website: str(s.website, 500), industry: str(s.industry, 80), segment: str(s.segment, 140), geography: str(s.geography, 80), stage: str(s.stage, 40), summary: str(s.summary, 2000) },
      competitors: (Array.isArray(a.competitors) ? a.competitors : []).slice(0, MAX_COMPETITORS).map(c => ({
        name: str(c?.name, 140), role: pick(c?.role, ROLES, ROLES[0]), website: str(c?.website, 500), unit: str(c?.unit, 140),
        exposure: pick(c?.exposure, EXPOSURE, 'unknown'), why: str(c?.why, 1000), counter: str(c?.counter, 1000) })),
      table: Object.fromEntries(FIELDS.map(([k]) => [k, {
        cells: Array.from({ length: MAX_COMPETITORS + 1 }, (_, i) => str(a.table?.[k]?.cells?.[i], 300)), source: str(a.table?.[k]?.source, 600) }])),
      forces: Object.fromEntries(FORCES.map(([k]) => [k, { level: pick(a.forces?.[k]?.level, LEVELS, 'Unknown'), evidence: str(a.forces?.[k]?.evidence, 600) }])),
      cs: factors(CS, a.cs), dp: factors(DP, a.dp),
      christensen: Object.fromEntries(CHRISTENSEN.map(([k]) => [k, pick(a.christensen?.[k], ['', 'yes', 'no'], '')])),
      type: pick(a.type, TYPES.map(t => t[0]), 'insufficient_evidence'), risk: str(a.risk, 1500),
    };
  }

  /* Weighted 0-100 score over the evidenced factors. A factor counts only when it has a rating AND written
     evidence. No score unless >= 70% of the weight and >= 4 factors are evidenced; missing factors are never
     counted as zero, the score is normalised over what was observed and the coverage is reported with it. */
  function score(defs, values) {
    const total = defs.reduce((s, d) => s + d[2], 0);
    let w = 0, sum = 0, n = 0, sourced = 0, self = 0;
    for (const [k, , weight] of defs) {
      const f = values?.[k];
      if (!f || f.rating === '' || !f.evidence.trim()) continue;
      w += weight; sum += weight * Number(f.rating) / 5; n++;
      if (url(f.source)) sourced += weight;
      if (f.self) self += weight;
    }
    const coverage = w / total;
    const enough = coverage >= 0.7 && n >= 4;
    const sourcedShare = w ? sourced / w : 0, selfShare = w ? self / w : 0;
    const confidence = enough && coverage >= 0.9 && sourcedShare === 1 && selfShare < 0.5 ? 'high' : enough && sourcedShare >= 0.5 ? 'medium' : 'low';
    return { score: enough ? Math.round(100 * sum / w) : null, coverage, factors: n, confidence, mostlySelfReported: selfShare > 0.5,
      missing: defs.filter(([k]) => !(values?.[k]?.rating !== '' && values?.[k]?.evidence.trim())).map(d => d[1]) };
  }

  function christensenSummary(answers) {
    const v = CHRISTENSEN.map(([k]) => answers?.[k] || '');
    const yes = v.filter(x => x === 'yes').length, unknown = v.filter(x => !x).length;
    if (unknown) return `${yes} of 4 yes, ${unknown} not answered yet`;
    return yes === 4 ? 'All 4 yes: fits Christensen’s disruption pattern' : `${yes} of 4 yes: not disruption in Christensen’s sense (may still be a strong sustaining competitor)`;
  }

  function load(storage) {
    try { const list = JSON.parse(storage.getItem(STORAGE_KEY) || '[]'); return Array.isArray(list) ? list.map(normalize) : []; } catch { return []; }
  }
  function save(storage, list) { storage.setItem(STORAGE_KEY, JSON.stringify(list)); }

  /* Merge analyses from a backup file; an analysis with the same id is replaced by the backup copy. */
  function merge(list, incoming) {
    if (!Array.isArray(incoming)) return { list, added: 0 };
    const clean = incoming.filter(a => a && typeof a === 'object').map(normalize), ids = new Set(clean.map(a => a.id));
    return { list: [...clean, ...list.filter(a => !ids.has(a.id))], added: clean.length };
  }

  function toMarkdown(a, now = new Date().toISOString()) {
    const cell = v => (v || 'Unknown').replace(/\|/g, '/').replace(/\n/g, ' ');
    const names = [a.startup.name || 'Startup', ...a.competitors.map(c => c.name || 'Unnamed')];
    const scoreLine = (label, defs, values) => {
      const r = score(defs, values);
      return `**${label}:** ${r.score == null ? 'Insufficient data' : r.score + ' / 100'} (evidence coverage ${Math.round(r.coverage * 100)}%, confidence ${r.confidence}${r.mostlySelfReported ? ', mostly self-reported' : ''})`;
    };
    const factorRows = (defs, values) => defs.map(([k, label, w]) => { const f = values[k]; return `| ${label} | ${w}% | ${f.rating === '' ? 'Unknown' : f.rating + '/5'} | ${cell(f.evidence)} | ${f.source || ''}${f.self ? ' (self-reported)' : ''} |`; }).join('\n');
    return `# ${a.startup.name || 'Startup'} — competitive analysis

${a.startup.industry ? `Industry: ${a.startup.industry} · ` : ''}${a.startup.segment ? `Segment: ${a.startup.segment} · ` : ''}${a.startup.geography ? `Geography: ${a.startup.geography} · ` : ''}Exported ${now.slice(0, 10)}

${a.startup.summary || ''}

${scoreLine('Competitive strength', CS, a.cs)}
${scoreLine('Disruption potential', DP, a.dp)}
**Disruption type:** ${TYPES.find(t => t[0] === a.type)[1]} · Christensen checklist: ${christensenSummary(a.christensen)}

## Biggest risk
${a.risk || 'Not written yet.'}

## Competitors
${a.competitors.map(c => `- **${c.name || 'Unnamed'}** (${c.role}${c.unit ? ', ' + c.unit : ''}) — exposure: ${c.exposure}. ${c.why}${c.counter ? ' Counterargument: ' + c.counter : ''}`).join('\n') || 'None added.'}

## Side-by-side
| | ${names.map(cell).join(' | ')} | Source |
|${'---|'.repeat(names.length + 2)}
${FIELDS.map(([k, label]) => `| ${label} | ${names.map((_, i) => cell(a.table[k].cells[i])).join(' | ')} | ${a.table[k].source || ''} |`).join('\n')}

## Industry forces (Porter)
${FORCES.map(([k, label]) => `- ${label}: ${a.forces[k].level}${a.forces[k].evidence ? ' — ' + a.forces[k].evidence : ''}`).join('\n')}

## Competitive strength factors
| Factor | Weight | Rating | Evidence | Source |
|---|---|---|---|---|
${factorRows(CS, a.cs)}

## Disruption potential factors
| Factor | Weight | Rating | Evidence | Source |
|---|---|---|---|---|
${factorRows(DP, a.dp)}

## Method
Each factor is rated 0–5 with written evidence. Score = 100 × Σ(weight × rating / 5) over evidenced factors, normalised by their total weight. No score is shown unless at least 70% of the weight and 4 factors are evidenced; missing factors are never counted as zero. Confidence is a separate heuristic (coverage, share of factors with a source link, self-reported share). These are research indicators, not investment advice or probabilities.
`;
  }

  root.VentureCompete = { STORAGE_KEY, CS, DP, ROLES, EXPOSURE, FORCES, LEVELS, CHRISTENSEN, TYPES, FIELDS, MAX_COMPETITORS, newAnalysis, normalize, score, christensenSummary, load, save, merge, toMarkdown, url };

  if (typeof document === 'undefined') return;

  /* ---------- page ---------- */
  root.createCompeteUI = function ({ esc, render, isActive, startups }) {
    const C = root.VentureCompete;
    const S = { list: C.load(localStorage), openId: null, error: '' };
    const current = () => S.list.find(a => a.id === S.openId);
    const persist = () => { try { C.save(localStorage, S.list); S.error = ''; } catch { S.error = 'This browser blocked saving (private mode or storage full). Export your analysis to keep it.'; } };
    const opt = (list, v) => list.map(x => { const [val, label] = Array.isArray(x) ? x : [x, x]; return `<option value="${esc(val)}"${val === v ? ' selected' : ''}>${esc(label)}</option>`; }).join('');
    const inp = (path, v, attrs = '') => `<input data-ca="${path}" value="${esc(v)}" ${attrs}>`;
    const area = (path, v, attrs = '') => `<textarea data-ca="${path}" rows="2" ${attrs}>${esc(v)}</textarea>`;
    const sel = (path, list, v, label) => `<select data-ca="${path}" aria-label="${esc(label)}">${opt(list, v)}</select>`;

    function scoreCard(title, defs, values) {
      const r = C.score(defs, values), pct = Math.round(r.coverage * 100);
      return `<div class="ca-score"><h3>${title}</h3>
        <p class="ca-num">${r.score == null ? '<span>Insufficient data</span>' : r.score + '<small>/100</small>'}</p>
        <div class="ca-cov" role="img" aria-label="Evidence coverage ${pct}%"><span style="width:${pct}%"></span></div>
        <p class="note">Evidence coverage ${pct}% · ${r.factors} of ${defs.length} factors · confidence <b>${r.confidence}</b>${r.mostlySelfReported ? ' · <b>mostly self-reported</b>' : ''}</p>
        ${r.score == null ? `<p class="note">A score needs written evidence for at least 70% of the weight and 4 factors.${r.missing.length ? ' Missing: ' + esc(r.missing.join(', ')) + '.' : ''}</p>` : ''}</div>`;
    }
    const scores = a => scoreCard('Competitive strength', C.CS, a.cs) + scoreCard('Disruption potential', C.DP, a.dp);

    function factorTable(key, defs, values) {
      return `<div class="tw"><table class="ca-factors"><thead><tr><th>Factor</th><th>Weight</th><th>Rating</th><th>Evidence (required to count)</th><th>Source link</th><th>Self-reported?</th></tr></thead><tbody>
        ${defs.map(([k, label, w]) => { const f = values[k]; return `<tr><th scope="row">${esc(label)}</th><td>${w}%</td>
          <td>${sel(`${key}.${k}.rating`, [['', 'Unknown'], '0', '1', '2', '3', '4', '5'], f.rating, label + ' rating')}</td>
          <td>${area(`${key}.${k}.evidence`, f.evidence, `aria-label="${esc(label)} evidence" maxlength="1000"`)}</td>
          <td>${inp(`${key}.${k}.source`, f.source, `type="url" placeholder="https://" aria-label="${esc(label)} source" maxlength="600"`)}</td>
          <td><input type="checkbox" data-ca="${key}.${k}.self"${f.self ? ' checked' : ''} aria-label="${esc(label)} evidence is self-reported by the company"></td></tr>`; }).join('')}
      </tbody></table></div>`;
    }

    function editor(a) {
      const names = [a.startup.name || 'Startup', ...a.competitors.map((c, i) => c.name || 'Competitor ' + (i + 1))];
      const list = startups();
      return `<div class="pagehead"><div><span class="eyebrow">Competitive analysis</span><h1>${esc(a.startup.name || 'New analysis')}</h1>
        <p>Can this startup win against the established companies in its field, and could it change how the industry works? Fill in what you can find; unknowns stay unknown.</p></div>
        <div class="ca-actions"><button type="button" class="btn" id="ca-back">All analyses</button><button type="button" class="btn" id="ca-md">Export Markdown</button><button type="button" class="btn" id="ca-json">Export JSON</button></div></div>
        ${S.error ? `<div class="panel" role="alert">${esc(S.error)}</div>` : ''}
        <section class="panel ca-sec"><h2>1. The startup</h2>
          <div class="ca-grid">
            <label>Startup name ${inp('startup.name', a.startup.name, 'list="ca-startups" maxlength="140" autocomplete="off"')}</label>
            <datalist id="ca-startups">${list.map(s => `<option value="${esc(s.name)}">`).join('')}</datalist>
            <label>Website ${inp('startup.website', a.startup.website, 'type="url" placeholder="https://" maxlength="500"')}</label>
            <label>Industry ${inp('startup.industry', a.startup.industry, 'maxlength="80"')}</label>
            <label>Customer segment ${inp('startup.segment', a.startup.segment, 'maxlength="140" placeholder="Who buys it"')}</label>
            <label>Geography ${inp('startup.geography', a.startup.geography, 'maxlength="80"')}</label>
            <label>Stage ${inp('startup.stage', a.startup.stage, 'maxlength="40"')}</label>
          </div>
          <label>Summary: what it does and how it is different ${area('startup.summary', a.startup.summary, 'maxlength="2000" rows="3"')}</label>
        </section>
        <section class="panel ca-sec"><h2>2. Competitors</h2>
          <p class="note">Aim for 3–5. Include the companies customers would otherwise use, substitutes, and “doing nothing”. A company counts when it shares at least two of: the same customer, the same problem, a comparable solution.</p>
          ${a.competitors.map((c, i) => `<div class="ca-comp"><div class="ca-grid">
            <label>Name ${inp(`competitors.${i}.name`, c.name, 'maxlength="140"')}</label>
            <label>Type ${sel(`competitors.${i}.role`, C.ROLES, c.role, 'Competitor type')}</label>
            <label>Product or business unit ${inp(`competitors.${i}.unit`, c.unit, 'maxlength="140" placeholder="The part that competes"')}</label>
            <label>Website ${inp(`competitors.${i}.website`, c.website, 'type="url" placeholder="https://" maxlength="500"')}</label>
            <label>How exposed to this startup? ${sel(`competitors.${i}.exposure`, C.EXPOSURE.map(x => [x, x[0].toUpperCase() + x.slice(1)]), c.exposure, 'Exposure')}</label></div>
            <label>Why (overlap, pricing, incentive to defend) ${area(`competitors.${i}.why`, c.why, 'maxlength="1000"')}</label>
            <label>Counterargument: how it could defend itself ${area(`competitors.${i}.counter`, c.counter, 'maxlength="1000"')}</label>
            <button type="button" class="btn" data-ca-remove="${i}">Remove ${esc(c.name || 'competitor')}</button></div>`).join('')}
          ${a.competitors.length < C.MAX_COMPETITORS ? '<button type="button" class="btn primary" id="ca-add">Add competitor</button>' : ''}
        </section>
        <section class="panel ca-sec"><h2>3. Side by side</h2>
          <p class="note">Leave a cell empty when the fact is not public; it is shown as Unknown. Never estimate private revenue from a funding amount.</p>
          <div class="tw"><table class="ca-table"><thead><tr><th></th>${names.map(n => `<th scope="col">${esc(n)}</th>`).join('')}<th>Source link</th></tr></thead><tbody>
            ${C.FIELDS.map(([k, label]) => `<tr><th scope="row">${esc(label)}</th>${names.map((n, i) => `<td>${inp(`table.${k}.cells.${i}`, a.table[k].cells[i], `placeholder="Unknown" aria-label="${esc(label)}: ${esc(n)}" maxlength="300"`)}</td>`).join('')}
              <td>${inp(`table.${k}.source`, a.table[k].source, `type="url" placeholder="https://" aria-label="${esc(label)} source" maxlength="600"`)}</td></tr>`).join('')}
          </tbody></table></div>
        </section>
        <section class="panel ca-sec"><h2>4. Industry forces</h2>
          <p class="note">Porter’s five forces describe the industry, not the startup. Note which force the startup weakens or depends on.</p>
          <div class="ca-forces">${C.FORCES.map(([k, label]) => `<label>${esc(label)} ${sel(`forces.${k}.level`, C.LEVELS, a.forces[k].level, label)}${inp(`forces.${k}.evidence`, a.forces[k].evidence, `placeholder="Evidence" aria-label="${esc(label)} evidence" maxlength="600"`)}</label>`).join('')}</div>
        </section>
        <section class="panel ca-sec"><h2>5. Scores</h2>
          <div class="ca-scores" id="ca-scores">${scores(a)}</div>
          <p class="note">Rate each factor 0–5 and write the evidence. A factor without evidence does not count. Scores are research indicators, not investment advice or probabilities of success.</p>
          <h3>Competitive strength: can it win and defend customers?</h3>${factorTable('cs', C.CS, a.cs)}
          <h3>Disruption potential: could it change how the industry works?</h3>${factorTable('dp', C.DP, a.dp)}
        </section>
        <section class="panel ca-sec"><h2>6. Disruption test</h2>
          <div class="ca-forces">${C.CHRISTENSEN.map(([k, q]) => `<label>${esc(q)} ${sel(`christensen.${k}`, [['', 'Not answered'], ['yes', 'Yes'], ['no', 'No']], a.christensen[k], q)}</label>`).join('')}</div>
          <p class="note" id="ca-christensen">${esc(C.christensenSummary(a.christensen))}. Treat this as one input: most successful startups are not disruptive in this narrow sense.</p>
          <label>Your classification ${sel('type', C.TYPES, a.type, 'Disruption type')}</label>
        </section>
        <section class="panel ca-sec"><h2>7. Biggest risk</h2>
          <p class="note">Always publish the biggest risk next to the score. A score without the risk reads like promotion, not analysis.</p>
          ${area('risk', a.risk, 'maxlength="1500" rows="3" aria-label="Biggest risk"')}
        </section>
        <p class="note">Saved automatically in this browser only. Use Export, or the backup on My startups, to keep a copy.</p>`;
    }

    function index() {
      return `<div class="pagehead"><div><span class="eyebrow">Research</span><h1>Competitive analysis</h1>
        <p>Compare a startup with the established companies, rivals and substitutes in its field. Rate the evidence, see two transparent scores, and export a report.</p></div>
        <div class="ca-actions"><button type="button" class="btn primary" id="ca-new">New analysis</button></div></div>
        ${S.error ? `<div class="panel" role="alert">${esc(S.error)}</div>` : ''}
        ${S.list.length ? `<div class="ca-list">${S.list.map(a => { const cs = C.score(C.CS, a.cs), dp = C.score(C.DP, a.dp);
          return `<article class="panel"><h2>${esc(a.startup.name || 'Untitled analysis')}</h2>
            <p class="note">${esc(a.startup.industry || 'Industry not set')} · ${a.competitors.length} competitor${a.competitors.length === 1 ? '' : 's'} · updated ${esc((a.updatedAt || '').slice(0, 10))}</p>
            <p>Competitive strength: <b>${cs.score ?? 'insufficient data'}</b> · Disruption potential: <b>${dp.score ?? 'insufficient data'}</b></p>
            <button type="button" class="btn primary" data-ca-open="${esc(a.id)}">Open</button> <button type="button" class="btn" data-ca-delete="${esc(a.id)}">Delete</button></article>`; }).join('')}</div>`
          : '<div class="panel"><p>No analyses yet. Start one with <b>New analysis</b>; you can pick a startup from Discover or My startups, or type any name.</p></div>'}
        <p class="note">Method: docs/competitive-analysis.md and docs/competitive-analysis-spec.md in the repository. Analyses are saved only in this browser.</p>`;
    }

    function view() { const a = current(); return a ? editor(a) : index(); }

    function setPath(a, path, value) {
      const keys = path.split('.'), last = keys.pop();
      let o = a; for (const k of keys) o = o[k];
      o[last] = value;
    }
    const download = (name, text, type) => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click(); URL.revokeObjectURL(a.href); };
    const slug = a => (a.startup.name || 'analysis').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'analysis';

    function onEdit(e) {
      const el = e.target.closest?.('[data-ca]'), a = current();
      if (!el || !a || !isActive()) return;
      setPath(a, el.dataset.ca, el.type === 'checkbox' ? el.checked : el.value);
      if (e.type === 'change' && /^competitors\.\d+\.name$/.test(el.dataset.ca)) { a.updatedAt = new Date().toISOString(); persist(); render(); return; } // table headers use the names
      if (el.dataset.ca === 'startup.name' && e.type === 'change') {
        const m = startups().find(s => s.name.toLowerCase() === el.value.trim().toLowerCase());
        if (m) { for (const k of ['website', 'industry', 'stage']) if (!a.startup[k] && m[k]) a.startup[k] = m[k]; }
        a.updatedAt = new Date().toISOString(); persist(); render(); return;
      }
      a.updatedAt = new Date().toISOString(); persist();
      const box = document.getElementById('ca-scores'); if (box) box.innerHTML = scores(a);
      const ch = document.getElementById('ca-christensen'); if (ch && el.dataset.ca.startsWith('christensen.')) ch.textContent = C.christensenSummary(a.christensen) + '. Treat this as one input: most successful startups are not disruptive in this narrow sense.';
    }
    document.addEventListener('input', onEdit);
    document.addEventListener('change', onEdit);
    document.addEventListener('click', e => {
      const b = e.target.closest?.('button'); if (!b || !isActive()) return;
      const a = current();
      if (b.id === 'ca-new') { const n = C.newAnalysis(); S.list.unshift(n); S.openId = n.id; persist(); render(); scrollTo(0, 0); }
      else if (b.dataset.caOpen) { S.openId = b.dataset.caOpen; render(); scrollTo(0, 0); }
      else if (b.dataset.caDelete) { const d = S.list.find(x => x.id === b.dataset.caDelete); if (d && confirm(`Delete the analysis of ${d.startup.name || 'this startup'}?`)) { S.list = S.list.filter(x => x !== d); persist(); render(); } }
      else if (b.id === 'ca-back') { S.openId = null; render(); scrollTo(0, 0); }
      else if (b.id === 'ca-add' && a && a.competitors.length < C.MAX_COMPETITORS) { a.competitors.push(C.normalize({ competitors: [{}] }).competitors[0]); persist(); render(); }
      else if (b.dataset.caRemove != null && a) {
        const i = Number(b.dataset.caRemove);
        a.competitors.splice(i, 1);
        for (const [k] of C.FIELDS) { a.table[k].cells.splice(i + 1, 1); a.table[k].cells.push(''); } // keep columns aligned with competitors
        persist(); render();
      }
      else if (b.id === 'ca-md' && a) download(`competitive-analysis-${slug(a)}.md`, C.toMarkdown(a), 'text/markdown');
      else if (b.id === 'ca-json' && a) download(`competitive-analysis-${slug(a)}.json`, JSON.stringify({ app: 'VentureScout', kind: 'competitive-analysis', schema_version: 1, exportedAt: new Date().toISOString(), analyses: [a] }, null, 1), 'application/json');
    });

    return { view, all: () => S.list, restore(incoming) { const r = C.merge(S.list, incoming); S.list = r.list; persist(); return r.added; } };
  };
})(typeof window !== 'undefined' ? window : globalThis);
