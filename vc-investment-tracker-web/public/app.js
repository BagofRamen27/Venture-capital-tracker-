/* VentureScout: app code (derived fields, views, charts, local edits). */
function boot(D, SOURCE) {
/* Imported research snapshot; edits are local to this browser. */
(function () {
  const b = document.getElementById("modebadge");
  b.textContent = "Research & personal tracking";
  b.setAttribute("data-tip", "Discovery and funding data refresh daily. Your saved companies, scores and pipeline edits stay in this browser.");
})();
const S = D.settings, T = S.thresholds, W = S.weights;
const CRIT = S.criteria.map(c => ({ key: c[0], name: c[1], r1: c[2], r3: c[3], r5: c[4], ev: c[5] }));
const TOTAL_W = Object.values(W).reduce((a, b) => a + b, 0);
const DD = [["dd_form_c_review", "Form C review"], ["dd_terms_verified", "Terms verified"], ["dd_financials_reviewed", "Financials reviewed"], ["dd_founder_references", "Founder references"], ["dd_customer_references", "Customer references"], ["dd_legal_cap_table", "Legal & cap table"]];

/* ---------- helpers ---------- */
const $ = s => document.querySelector(s);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = v => (v === "" || v == null || isNaN(+v)) ? null : +v;
const blank = v => v == null || v === "";
function money(n, compact) {
  if (n == null) return null;
  if (compact) {
    const a = Math.abs(n);
    if (a >= 1e6) return "$" + parseFloat((n / 1e6).toFixed(a >= 1e7 ? 1 : 2)) + "M";
    if (a >= 1e3) return "$" + parseFloat((n / 1e3).toFixed(a >= 1e5 ? 0 : 1)) + "K";
  }
  return "$" + n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}
const pct = (f, d = 0) => f == null ? null : (f * 100).toFixed(d) + "%";
const mult = x => x == null ? null : (x >= 100 ? Math.round(x).toLocaleString("en-US") : x.toFixed(1)) + "x";
const na = t => `<span class="na">${esc(t || "Not disclosed")}</span>`;
function fmtDate(d) { if (!d) return null; const [y, m, dd] = d.split("-"); return `${["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+m - 1]} ${+dd}, ${y}`; }
const TODAY = (() => { const t = new Date(); return new Date(t.getFullYear(), t.getMonth(), t.getDate()); })();
const daysTo = d => d ? Math.round((new Date(d + "T00:00:00") - TODAY) / 864e5) : null;
const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

/* ---------- local edits (browser only) ---------- */
const LS = "vctracker.edits.v1";
let EDITS = { scores: {}, pipeline: {}, log: [] };
try { const j = JSON.parse(localStorage.getItem(LS) || "null"); if (j && j.log) EDITS = j; } catch (e) {}
const save = () => { try { localStorage.setItem(LS, JSON.stringify(EDITS)); } catch (e) {} };
let UI = { directory: { q: "", view: "table", sort: "deadline", f: {} }, pipeView: "board", scoreId: "DS-001" };
try { const u = JSON.parse(localStorage.getItem(LS + ".ui") || "null"); if (u) UI = Object.assign(UI, u); } catch (e) {}
const saveUI = () => { try { localStorage.setItem(LS + ".ui", JSON.stringify(UI)); } catch (e) {} };

/* ---------- data access ---------- */
const STARTUPS = D.startups;
const BYID = Object.fromEntries(STARTUPS.map(s => [s.startup_id, s]));
if (!Object.hasOwn(BYID, UI.scoreId)) UI.scoreId = STARTUPS[0]?.startup_id || '';
const ROUNDS = id => D.rounds.filter(r => r.startup_id === id);
const CUR = Object.fromEntries(D.rounds.filter(r => r.is_current_round === "Yes").map(r => [r.startup_id, r]));
const CLAIMS = id => D.claims.filter(c => c.startup_id === id);
const UNV = new Set(["Platform-reported", "Company-stated (unverified)", "Conflicting sources"]);
const isUnv = c => UNV.has(c.verification_status);
const isConf = c => c.verification_status === "Conflicting sources";
const isVer = c => c.verification_status.startsWith("Verified");
/* evidence level of a figure: verified | reported | conflicting | none */
function evidence(id, keys) {
  const cs = CLAIMS(id).filter(c => keys.some(k => c.field_name.includes(k)));
  if (cs.some(isConf)) return "conflicting";
  if (cs.some(isUnv)) return "reported";
  if (cs.some(isVer)) return "verified";
  return "none";
}
const basePipe = Object.fromEntries(D.pipeline.map(p => [p.startup_id, p]));
const baseScore = Object.fromEntries(D.scores.map(p => [p.startup_id, p]));
const pipe = id => Object.assign({}, basePipe[id], EDITS.pipeline[id] || {});
const scoreRow = id => Object.assign({}, baseScore[id], EDITS.scores[id] || {});

function setField(tab, id, field, value) {
  const cur = tab === "Deal Pipeline" ? pipe(id) : scoreRow(id);
  const before = cur[field] ?? "";
  if (String(before) === String(value)) return false;
  const store = tab === "Deal Pipeline" ? EDITS.pipeline : EDITS.scores;
  store[id] = store[id] || {};
  store[id][field] = value;
  if (tab === "Deal Pipeline") { store[id].last_updated = new Date().toISOString().slice(0, 10); store[id].updated_by = "browser prototype"; }
  const n = EDITS.log.length + 1;
  EDITS.log.push({ request_id: "CR-" + String(n).padStart(5, "0"), submitted_at: new Date().toISOString(), submitted_by: "browser prototype", target_tab: tab, record_id: id, field_name: field, current_value: before, proposed_value: value, status: "Applied", record_version_at_submit: BYID[id].record_version });
  save(); updateLogCount();
  return true;
}

/* ---------- derived fields (schema section 2) ---------- */
function flags(id) {
  const cs = CLAIMS(id);
  return { unverified: cs.filter(isUnv).length, conflicts: cs.filter(c => isConf(c) && c.review_status !== "Resolved").length };
}
function finance(s) {
  const id = s.startup_id, r = CUR[id] || {};
  const rev = num(s.latest_fy_revenue_usd), arr = num(s.current_arr_usd), emp = num(s.employees), ltd = num(s.long_term_debt_usd);
  const raised = num(r.capital_raised_usd), val = num(r.valuation_amount_usd);
  const prior = ROUNDS(id).filter(x => x.is_current_round !== "Yes").map(x => num(x.capital_raised_usd)).filter(x => x != null);
  const avail = [rev, arr, emp, ltd, raised, val].filter(x => x != null).length;
  const cov = avail / 6;
  return {
    rev, arr, emp, ltd, raised, val, revToDate: num(s.revenue_to_date_usd),
    prior: prior.length ? prior.reduce((a, b) => a + b, 0) : null,
    valRev: (val == null || rev == null) ? null : rev === 0 ? "n/m" : val / rev,
    valArr: (val == null || arr == null) ? null : arr === 0 ? "n/m" : val / arr,
    avail, cov, insufficient: cov < T.financial_coverage,
  };
}
function score(id) {
  const r = scoreRow(id); let pts = 0, wScored = 0; const ie = [], missingEv = []; let notRev = 0;
  for (const c of CRIT) {
    const v = r[c.key + "_score"];
    if (blank(v)) { notRev++; continue; }
    if (v === "IE") { ie.push(labelOf(c.key)); continue; }
    const n = +v; pts += n / 5 * W[c.key]; wScored += W[c.key];
    if (blank((r[c.key + "_evidence"] || "").trim())) missingEv.push(labelOf(c.key));
  }
  const s100 = wScored ? Math.round(pts / wScored * 1000) / 10 : null;
  const cov = wScored / TOTAL_W;
  let rating;
  if (notRev === CRIT.length) rating = "Not scored";
  else if (cov < T.min_evidence_coverage) rating = "Insufficient evidence";
  else rating = s100 >= T.strong ? "Strong candidate" : s100 >= T.promising ? "Promising" : s100 >= T.watchlist ? "Watchlist" : "Below threshold";
  return { s100, wScored, cov, ie, notRev, rating, missingEv, pts };
}
function labelOf(k) { return { market: "Market", traction: "Traction", team: "Team", moat: "Moat", financials: "Financials" }[k]; }
function ddPct(p) {
  const v = DD.map(d => p[d[0]]); const den = 6 - v.filter(x => x === "N/A").length;
  return den ? v.filter(x => x === "Done").length / den : null;
}

/* figure markers: Source Verification claims backing a field */
function claimFor(id, keys) {
  const cs = CLAIMS(id).filter(c => keys.some(k => c.field_name.includes(k)));
  return cs.find(isConf) || cs.find(isUnv) || cs[0] || null;
}
function marker(id, keys) {
  const cs = CLAIMS(id).filter(c => keys.some(k => c.field_name.includes(k)));
  const conf = cs.find(isConf);
  if (conf) return ` <span class="b b-conf" tabindex="0" data-tip="${esc(conf.conflict_note || "Sources disagree") + " (" + conf.claim_id + ")"}"><i>▲</i>Conflicting sources</span>`;
  const u = cs.find(isUnv);
  if (u) return ` <span class="b b-unv" tabindex="0" data-tip="${esc(u.verification_status + " · " + u.source_type + " (" + u.claim_id + "). Reported by the platform or company, not independently verified.")}"><i>◆</i>Unverified · ${u.verification_status === "Platform-reported" ? "platform-reported" : "company-stated"}</span>`;
  const v = cs.find(isVer);
  if (v) return ` <span class="b b-ok" tabindex="0" data-tip="${esc(v.verification_status + " · " + v.source_type + " (" + v.claim_id + ")")}"><i>✓</i>Verified · ${v.verification_status === "Verified - SEC filing" ? "SEC filing" : "primary source"}</span>`;
  return "";
}
function srcLink(id, keys, fallbackUrl, fallbackLabel) {
  const c = claimFor(id, keys);
  const url = c?.source_url || fallbackUrl;
  if (!url) return "";
  const label = c ? `${c.source_type} · ${c.claim_id}` : (fallbackLabel || "Source");
  return `<span class="src"><a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a></span>`;
}

/* badges */
function statusBadge(st) {
  const cls = { "Open": "b-open", "Testing the Waters": "b-ttw", "Closed": "b-closed", "No Active Round Known": "b-none" }[st] || "b-plain";
  return `<span class="b ${cls}" data-tip="Fundraising status: state of the round">${esc(st)}</span>`;
}
function confBadge(c) {
  const m = { High: ["b-high", "●"], Medium: ["b-medium", "◐"], Low: ["b-low", "○"] }[c] || ["b-plain", "·"];
  return `<span class="b ${m[0]}" data-tip="Verification confidence: how well sourced the record is"><i>${m[1]}</i>${esc(c)} confidence</span>`;
}
function ratingBadge(r) {
  const cls = { "Strong candidate": "b-strong", "Promising": "b-prom", "Watchlist": "b-watch", "Below threshold": "b-below", "Insufficient evidence": "b-plain", "Not scored": "b-plain" }[r];
  return `<span class="b ${cls}">${esc(r)}</span>`;
}
function valuationText(r, compact) {
  const v = num(r?.valuation_amount_usd);
  if (v == null) return na(r?.valuation_type && r.valuation_type !== "" ? r.valuation_type : "Not disclosed");
  return `<span class="num">${money(v, compact)}</span> <span class="small muted">${esc((r.valuation_type || "").replace("(pre/post not stated)", "(pre/post n/s)"))}</span>`;
}
function raisedText(s, compact) {
  const r = CUR[s.startup_id] || {};
  const v = num(r.capital_raised_usd);
  return v == null ? na(r.capital_raised_status || "Not disclosed") : `<span class="num">${money(v, compact)}</span>`;
}
function deadlineText(r) {
  if (!r?.offering_deadline) return na(r?.round_status === "Closed" || r?.round_status === "Historical" ? "N/A (" + r.round_status.toLowerCase() + ")" : "No deadline");
  const d = daysTo(r.offering_deadline);
  const left = d < 0 ? `${-d}d ago` : `${d}d left`;
  return `<span class="num">${r.offering_deadline}</span><span class="sub ${d >= 0 && d <= T.alert_days ? "" : ""}">${left}</span>`;
}

/* ---------- tooltip ---------- */
const tip = $("#tip");
function showTip(el) {
  const t = el.getAttribute("data-tip"); if (!t) return;
  tip.textContent = t; tip.hidden = false;
  const r = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
  let x = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8);
  let y = r.top - h - 8; if (y < 8) y = r.bottom + 8;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
document.addEventListener("mouseover", e => { const el = e.target.closest("[data-tip]"); if (el) showTip(el); else tip.hidden = true; });
document.addEventListener("focusin", e => { const el = e.target.closest("[data-tip]"); if (el) showTip(el); });
document.addEventListener("focusout", () => tip.hidden = true);
addEventListener("scroll", () => tip.hidden = true, { passive: true });

function toast(msg) {
  const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; document.body.appendChild(t);
  setTimeout(() => t.remove(), 2200);
}

/* ---------- charts ---------- */
function barList(items, { max, fmt = v => v, ticks, alt, tickVal, link } = {}) {
  const m = max ?? Math.max(1, ...items.map(i => i.value ?? 0));
  const rows = items.map(i => {
    const w = i.value == null ? 0 : Math.max(0, i.value) / m * 100;
    const tk = i.tick != null ? `<span class="tick" style="left:calc(${Math.min(100, i.tick / m * 100)}% - 1px)"></span>` : "";
    return `<div class="bar-row${link && i.id ? " link" : ""}" ${i.id && link ? `data-go="${i.id}"` : ""} data-tip="${esc(i.tip || (i.label + ": " + (i.value == null ? "not disclosed" : fmt(i.value))))}">
      <span class="lab">${esc(i.label)}</span>
      <span class="track">${(ticks || []).map(t => `<span class="grid-line" style="left:${t / m * 100}%"></span>`).join("")}${i.value == null ? "" : `<span class="fill${i.alt ? " alt" : ""}" style="width:${w}%"></span>`}${tk}</span>
      <span class="val">${i.value == null ? `<span class="na">${esc(i.naText || "n/a")}</span>` : esc(i.display ?? fmt(i.value))}</span></div>`;
  }).join("");
  const axis = ticks ? `<div class="axis"><span></span><span class="ticks">${ticks.map(t => `<span style="left:${t / m * 100}%">${esc(fmt(t))}</span>`).join("")}</span><span></span></div>` : "";
  return `<div class="bars">${rows}${axis}</div>`;
}
function countBy(list, fn, order) {
  const m = new Map(); (order || []).forEach(k => m.set(k, 0));
  list.forEach(x => { const k = fn(x); m.set(k, (m.get(k) || 0) + 1); });
  return [...m.entries()].map(([label, value]) => ({ label, value }));
}
function niceTicks(max, n = 4) {
  const raw = max / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 2.5, 5, 10].map(s => s * mag).find(s => s >= raw);
  const out = []; for (let v = 0; v <= max + 1e-9; v += step) out.push(v); if (out[out.length - 1] < max) out.push(out[out.length - 1] + step);
  return out;
}

/* ---------- routing ---------- */
let route = { view: "dashboard", id: null };
function parseHash() {
  const h = (location.hash || "").slice(1);
  if (Object.hasOwn(BYID,h)) return { view: "profile", id: h };
  if (["dashboard", "directory", "scorecard", "pipeline", "financials", "changes", "discover", "tracking", "status"].includes(h)) return { view: h };
  return { view: "dashboard" };
}
function go(view, id) {
  const token = view === "profile" ? id : view;
  route = view === "profile" ? { view, id } : { view };
  try { if (location.hash.slice(1) !== token) history.pushState(null, "", "#" + token); } catch (e) {}
  render(); scrollTo(0, 0);
}
addEventListener("popstate", () => { route = parseHash(); render(); });
addEventListener("hashchange", () => { const r = parseHash(); if (r.view !== route.view || r.id !== route.id) { route = r; render(); } });

function updateLogCount() { $("#logn").textContent = EDITS.log.length; }

function render() {
  tip.hidden = true;
  const active = route.view === "profile" ? "directory" : route.view;
  document.querySelectorAll("#tabs button").forEach(b => { if (b.dataset.nav === active) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  const v = { dashboard: marketUI.dashboard, directory: viewDirectory, profile: viewProfile, scorecard: viewScorecard, pipeline: viewPipeline, financials: marketUI.financials, changes: viewChanges, discover: viewDiscover, tracking: viewTracking, status: viewStatus }[route.view];
  $("#app").innerHTML = v(route.id);
  document.title = route.view === "profile" ? BYID[route.id].company_name + " · VentureScout" : "VentureScout";
  updateLogCount();
}

/* ---------- DASHBOARD ---------- */
function viewDashboard() {
  const all = STARTUPS;
  const cur = all.map(s => CUR[s.startup_id]).filter(Boolean);
  const regcf = cur.filter(r => r.regulation.startsWith("Reg CF"));
  const regcfVals = regcf.map(r => num(r.capital_raised_usd)).filter(v => v != null);
  const priv = cur.filter(r => r.regulation === "Private placement");
  const privVals = priv.map(r => num(r.capital_raised_usd)).filter(v => v != null);
  const vals = cur.map(r => num(r.valuation_amount_usd)).filter(v => v != null);
  const openOff = all.filter(s => s.fundraising_status === "Open").length;
  const ttw = all.filter(s => s.fundraising_status === "Testing the Waters").length;
  const watch = all.map(s => ({ s, r: CUR[s.startup_id] })).filter(x => x.r && x.r.offering_deadline && ["Open", "Testing the Waters"].includes(x.s.fundraising_status)).sort((a, b) => a.r.offering_deadline.localeCompare(b.r.offering_deadline) || a.s.startup_id.localeCompare(b.s.startup_id));
  const closing = watch.filter(x => { const d = daysTo(x.r.offering_deadline); return d >= 0 && d <= T.alert_days; });
  const fl = all.map(s => flags(s.startup_id));
  const unv = fl.reduce((a, b) => a + b.unverified, 0), conf = fl.reduce((a, b) => a + b.conflicts, 0);
  const insuff = all.filter(s => finance(s).insufficient).length;
  const scs = all.map(s => score(s.startup_id));
  const scored = scs.filter(x => x.s100 != null && x.rating !== "Insufficient evidence");
  const ddv = all.map(s => ddPct(pipe(s.startup_id))).filter(v => v != null);
  const ddAvg = ddv.length ? ddv.reduce((a, b) => a + b, 0) / ddv.length : null;

  const kpi = (v, l, s, cls = "") => `<div class="kpi ${cls}"><span class="v">${v}</span><span class="l">${l}</span>${s ? `<span class="s">${s}</span>` : ""}</div>`;

  // sector
  const sectors = [...new Set(all.map(s => s.sector))].sort();
  const sectorItems = sectors.map(sec => {
    const ss = all.filter(s => s.sector === sec);
    const raisedVals = ss.map(s => num(CUR[s.startup_id]?.capital_raised_usd)).filter(v => v != null);
    return { label: sec, value: ss.length, tip: `${sec}: ${ss.length} startup${ss.length > 1 ? "s" : ""} (${ss.map(s => s.company_name).join(", ")}). Raised in current rounds: ${raisedVals.length ? money(raisedVals.reduce((a, b) => a + b, 0)) : "not disclosed"}` };
  }).sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));

  const platforms = [...new Set(cur.map(r => r.platform))];
  const platItems = platforms.map(p => {
    const rs = cur.filter(r => r.platform === p); const v = rs.map(r => num(r.capital_raised_usd)).filter(x => x != null);
    return { label: p, value: rs.length, tip: `${p}: ${rs.length} current round${rs.length > 1 ? "s" : ""}; raised ${v.length ? money(v.reduce((a, b) => a + b, 0)) : "not disclosed"}${v.length < rs.length ? ` (${rs.length - v.length} not disclosed)` : ""}` };
  }).sort((a, b) => b.value - a.value);

  // raised vs min target
  const raisedItems = all.map(s => ({ s, r: CUR[s.startup_id] })).filter(x => x.r && x.r.regulation.startsWith("Reg CF"))
    .map(x => ({ id: x.s.startup_id, label: x.s.company_name, value: num(x.r.capital_raised_usd), tick: num(x.r.min_target_usd), naText: x.r.capital_raised_status || "Not disclosed",
      tip: `${x.s.company_name}: raised ${num(x.r.capital_raised_usd) == null ? (x.r.capital_raised_status || "not disclosed") : money(num(x.r.capital_raised_usd))} (${x.r.capital_raised_status}); minimum target ${money(num(x.r.min_target_usd)) || "n/a"}; max ${money(num(x.r.max_target_usd)) || "n/a"}`,
      display: num(x.r.capital_raised_usd) == null ? null : money(num(x.r.capital_raised_usd), true) }))
    .sort((a, b) => (b.value ?? -1) - (a.value ?? -1));
  const rMax = Math.max(...raisedItems.map(i => Math.max(i.value || 0, i.tick || 0)));
  const rTicks = niceTicks(rMax, 4);

  const stageOrder = ["Pre-seed", "Pre-seed / Seed", "Seed", "Series A", "Series B+"];
  const pipeItems = countBy(all, s => pipe(s.startup_id).pipeline_stage, S.pipeline_stage);
  const ratingItems = countBy(scs, x => x.rating, ["Strong candidate", "Promising", "Watchlist", "Below threshold", "Insufficient evidence", "Not scored"]);

  return `
  <div class="pagehead"><div><span class="eyebrow">Portfolio overview</span><h1>Venture dashboard</h1>
    <p>${all.length} startups sourced from Reg CF filings, platform listings and YC. Capital and valuation figures are as reported; unavailable values are left out of totals and medians, and the count left out is shown.</p></div></div>

  <section class="kpis" aria-label="Deal flow">
    ${kpi(all.length, "Startups tracked", `${openOff} open · ${ttw} testing the waters · ${all.length - openOff - ttw} closed or no active round`)}
    ${kpi(money(regcfVals.reduce((a, b) => a + b, 0), true), "Raised in current Reg CF offerings", `Platform-reported, incl. flagged · ${regcfVals.length} of ${regcf.length} disclosed`)}
    ${kpi(money(privVals.reduce((a, b) => a + b, 0), true), "Raised in current private rounds", `Press-reported · ${privVals.length} of ${priv.length} disclosed`)}
    ${kpi(money(median(vals), true), "Median valuation or cap", `Disclosed only · ${vals.length} of ${cur.length}; mixes SAFE caps and priced rounds`)}
    ${kpi(closing.length, "Rounds closing within " + T.alert_days + " days", closing.map(x => x.s.company_name).join(", ") || "None", closing.length ? "alert" : "")}
  </section>
  <section class="kpis" aria-label="Data quality and review">
    ${kpi(unv, "Unverified claims", "Platform-reported, company-stated or conflicting", "warnk")}
    ${kpi(conf, "Open source conflicts", "Claims with conflicting sources, not resolved", conf ? "alert" : "")}
    ${kpi(insuff, "Insufficient financial data", `Under ${pct(T.financial_coverage)} of 6 key financial fields`)}
    ${kpi(`${scored.length}<span class="small muted"> / ${all.length}</span>`, "Startups scored", scored.length ? `Average ${(scored.reduce((a, b) => a + b.s100, 0) / scored.length).toFixed(1)} · ${scs.filter(x => x.rating === "Insufficient evidence").length} held back for evidence` : "No analyst scores yet")}
    ${kpi(ddAvg == null ? "–" : pct(ddAvg), "Average due-diligence completion", "Done ÷ applicable checks")}
  </section>

  <section class="panel">
    <div class="ph"><h2>Deadline watch</h2><span class="small muted">Open offerings by Form C deadline · highlighted rows close within ${T.alert_days} days</span></div>
    <div class="tw"><table><thead><tr><th>Company</th><th>Deadline</th><th class="r">Days left</th><th class="r">Raised</th><th class="r">% of min</th><th>Round status</th></tr></thead><tbody>
    ${watch.map(({ s, r }) => { const d = daysTo(r.offering_deadline), rv = num(r.capital_raised_usd), mn = num(r.min_target_usd);
      return `<tr class="click ${d >= 0 && d <= T.alert_days ? "alert" : ""}" data-go="${s.startup_id}"><td><span class="cname">${esc(s.company_name)}</span><span class="sub">${esc(s.sector)}</span></td>
      <td class="num">${r.offering_deadline}${r.deadline_alt_date ? ` <span class="b b-conf" data-tip="Platform page shows ${esc(r.deadline_alt_date)}">▲ alt ${esc(r.deadline_alt_date)}</span>` : ""}</td>
      <td class="r num">${d}</td><td class="r">${rv == null ? na(r.capital_raised_status) : `<span class="num">${money(rv)}</span>`}${marker(s.startup_id, ["capital_raised_usd"])}</td>
      <td class="r num">${rv != null && mn ? pct(rv / mn) : "–"}</td><td>${esc(r.round_status)}</td></tr>`; }).join("")}
    </tbody></table></div>
  </section>

  ${evidencePanel()}

  <section class="panel">
    <div class="ph"><h2>Capital raised against minimum target</h2><span class="small muted">Current Reg CF offerings · bar = raised, line = minimum target · click a row to open</span></div>
    ${barList(raisedItems, { max: rTicks[rTicks.length - 1], ticks: rTicks, fmt: v => money(v, true), link: true })}
    <div class="legend"><span><i class="sw"></i>Raised (platform-reported)</span><span><i class="sw tk"></i>Minimum target (Form C)</span></div>
  </section>

  <div class="grid g2">
    <section class="panel"><div class="ph"><h2>By sector</h2><span class="small muted">Startups</span></div>${barList(sectorItems)}</section>
    <section class="panel"><div class="ph"><h2>By platform</h2><span class="small muted">Current rounds</span></div>${barList(platItems)}</section>
    <section class="panel"><div class="ph"><h2>By fundraising status</h2><span class="small muted">Startups</span></div>${barList(countBy(all, s => s.fundraising_status, ["Open", "Testing the Waters", "Closed", "No Active Round Known"]))}</section>
    <section class="panel"><div class="ph"><h2>By funding stage</h2><span class="small muted">Startups</span></div>${barList(countBy(all, s => s.funding_stage, stageOrder).filter(i => i.value))}</section>
    <section class="panel"><div class="ph"><h2>By verification confidence</h2><span class="small muted">Startups</span></div>${barList(countBy(all, s => s.verification_confidence, ["High", "Medium", "Low"]))}</section>
    <section class="panel"><div class="ph"><h2>Deal pipeline</h2><span class="small muted">Startups per stage</span></div>${barList(pipeItems)}</section>
    <section class="panel"><div class="ph"><h2>Screening ratings</h2><span class="small muted">From the scorecard</span></div>${barList(ratingItems)}</section>
    <section class="panel"><div class="ph"><h2>Claims by verification status</h2><span class="small muted">${D.claims.length} source claims</span></div>${barList(countBy(D.claims, c => c.verification_status, ["Verified - SEC filing", "Verified - primary source", "Platform-reported", "Company-stated (unverified)", "Conflicting sources", "Not disclosed"]))}</section>
  </div>`;
}

/* verified vs reported fundraising figures (current rounds) */
function evidencePanel() {
  const levels = [["verified", "Independently verified", "b-ok", "✓", "SEC filing or primary source"], ["reported", "Reported, not verified", "b-unv", "◆", "Platform page or company statement"], ["conflicting", "Conflicting sources", "b-conf", "▲", "Sources disagree; reconcile before relying"], ["none", "Not disclosed", "b-plain", "·", "No figure available"]];
  const fig = (field, keys) => {
    const out = Object.fromEntries(levels.map(l => [l[0], []]));
    STARTUPS.forEach(s => { const r = CUR[s.startup_id]; const v = num(r?.[field]); if (v == null) { out.none.push({ s, v }); return; } const lv = evidence(s.startup_id, keys); out[lv === "none" ? "reported" : lv].push({ s, v }); });
    return out;
  };
  const raised = fig("capital_raised_usd", ["capital_raised_usd"]), val = fig("valuation_amount_usd", ["valuation_or_cap"]);
  const cell = (list, sum) => { if (!list.length) return `<td class="r muted">–</td>`; const names = list.map(x => x.s.company_name + (x.v != null ? " " + money(x.v, true) : "")).join(", ");
    return `<td class="r" tabindex="0" data-tip="${esc(names)}"><span class="num">${list.length}</span>${sum ? `<span class="sub num">${money(list.reduce((a, b) => a + (b.v || 0), 0), true)}</span>` : ""}</td>`; };
  return `<section class="panel"><div class="ph"><h2>Verified vs reported fundraising figures</h2><span class="small muted">Current rounds, by the strongest evidence in Source Verification · hover a count for the companies</span></div>
    <div class="tw"><table><thead><tr><th>Evidence</th><th class="r">Capital raised<br><span style="text-transform:none">startups · total</span></th><th class="r">Valuation / cap<br><span style="text-transform:none">startups</span></th></tr></thead><tbody>
    ${levels.map(([k, l, cls, ic, d]) => `<tr><td><span class="b ${cls}"><i>${ic}</i>${l}</span><span class="sub">${d}</span></td>${cell(raised[k], k !== "none")}${cell(val[k], false)}</tr>`).join("")}
    </tbody></table></div>
    <p class="note">Every raised and valuation figure in the app carries one of these markers. Reg CF raised totals come from platform pages, not the Form C filing, so they count as reported until reconciled.</p></section>`;
}

/* ---------- DIRECTORY ---------- */
const FILTERS = [
  ["sector", "Sector", s => s.sector], ["funding_stage", "Stage", s => s.funding_stage], ["fundraising_status", "Fundraising status", s => s.fundraising_status],
  ["verification_confidence", "Confidence", s => s.verification_confidence], ["platform", "Platform", s => CUR[s.startup_id]?.platform || ""],
  ["regulation", "Regulation", s => CUR[s.startup_id]?.regulation || ""], ["rating", "Rating", s => score(s.startup_id).rating], ["pipeline_stage", "Pipeline stage", s => pipe(s.startup_id).pipeline_stage],
];
function filtered() {
  const st = UI.directory, q = st.q.trim().toLowerCase();
  let list = STARTUPS.filter(s => {
    if (q && ![s.company_name, s.legal_name, s.sub_sector, s.founders, s.business_model, s.notable_investors, s.sector].join(" ").toLowerCase().includes(q)) return false;
    for (const [k, , fn] of FILTERS) if (st.f[k] && fn(s) !== st.f[k]) return false;
    if (st.f.within) { const d = daysTo(CUR[s.startup_id]?.offering_deadline); if (d == null || d < 0 || d > +st.f.within) return false; }
    if (st.f.conflicts && !flags(s.startup_id).conflicts) return false;
    if (st.f.insuff && !finance(s).insufficient) return false;
    return true;
  });
  const key = {
    deadline: s => CUR[s.startup_id]?.offering_deadline || "9999",
    raised: s => -(num(CUR[s.startup_id]?.capital_raised_usd) ?? -1),
    valuation: s => -(num(CUR[s.startup_id]?.valuation_amount_usd) ?? -1),
    score: s => -(score(s.startup_id).s100 ?? -1),
    name: s => s.company_name.toLowerCase(),
    updated: s => (pipe(s.startup_id).last_updated || s.last_updated),
  }[st.sort];
  list.sort((a, b) => { const x = key(a), y = key(b); return (x < y ? -1 : x > y ? 1 : 0) || a.startup_id.localeCompare(b.startup_id); });
  if (st.sort === "updated") list.reverse();
  return list;
}
function viewDirectory() {
  const st = UI.directory;
  const opts = (k, fn) => [...new Set(STARTUPS.map(fn))].filter(Boolean).sort();
  const nActive = Object.values(st.f).filter(Boolean).length + (st.q ? 1 : 0);
  return `
  <div class="pagehead"><div><span class="eyebrow">Company directory</span><h1>Startups</h1><p>${STARTUPS.length} research profiles, including your saved companies. There is no 20-company limit.</p></div><div class="controls"><button class="btn primary" data-nav="discover">Discover more startups</button><button class="btn" data-nav="tracking">Add a startup</button></div></div>
  <section class="panel" style="display:flex;flex-direction:column;gap:12px">
    <div class="controls">
      <input id="q" class="search" type="search" placeholder="Search name, sub-sector, founders, business model, investors" value="${esc(st.q)}" aria-label="Search startups">
      <label class="chk">Sort <select id="sort" aria-label="Sort by">${[["deadline", "Deadline"], ["raised", "Capital raised"], ["valuation", "Valuation"], ["score", "Screening score"], ["updated", "Last updated"], ["name", "Name"]].map(([v, l]) => `<option value="${v}" ${st.sort === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <div class="seg" role="group" aria-label="View"><button type="button" data-view="table" aria-pressed="${st.view === "table"}">Table</button><button type="button" data-view="cards" aria-pressed="${st.view === "cards"}">Cards</button></div>
    </div>
    <div class="filters">
      ${FILTERS.map(([k, l, fn]) => `<label>${l}<select data-filter="${k}"><option value="">All</option>${opts(k, fn).map(o => `<option ${st.f[k] === o ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></label>`).join("")}
      <label>Deadline within (days)<input type="number" min="0" id="within" data-filter="within" placeholder="Any" value="${esc(st.f.within || "")}"></label>
    </div>
    <div class="controls">
      <label class="chk"><input type="checkbox" data-filter="conflicts" ${st.f.conflicts ? "checked" : ""}> Has open conflicts</label>
      <label class="chk"><input type="checkbox" data-filter="insuff" ${st.f.insuff ? "checked" : ""}> Insufficient financial data</label>
      <span id="dircount" class="small muted" style="margin-left:auto"></span>
      ${nActive ? `<button type="button" class="btn" id="clearf">Clear filters</button>` : ""}
    </div>
  </section>
  <div id="dirresults"></div>`;
}
function renderDirResults() {
  const list = filtered(), st = UI.directory, el = $("#dirresults"); if (!el) return;
  $("#dircount").textContent = `${list.length} of ${STARTUPS.length} startups`;
  if (!list.length) { el.innerHTML = `<div class="panel empty">No startups match these filters.</div>`; return; }
  const alertOf = s => { const d = daysTo(CUR[s.startup_id]?.offering_deadline); return d != null && d >= 0 && d <= T.alert_days && s.fundraising_status !== "Closed"; };
  if (st.view === "cards") {
    el.innerHTML = `<div class="cards">${list.map(s => { const r = CUR[s.startup_id], sc = score(s.startup_id);
      return `<button type="button" class="card ${alertOf(s) ? "alert" : ""}" data-go="${s.startup_id}">
        <div class="top"><div><div class="cname">${esc(s.company_name)}</div><div class="small muted">${esc(s.sector)} · ${esc(s.funding_stage)}</div></div><span class="mono small muted">${s.startup_id}</span></div>
        <div class="badges">${statusBadge(s.fundraising_status)}${confBadge(s.verification_confidence)}</div>
        <dl><dt>Raised</dt><dd>${raisedText(s, true)}</dd><dt>Valuation</dt><dd>${valuationText(r, true)}</dd><dt>Deadline</dt><dd>${r?.offering_deadline ? `<span class="num">${r.offering_deadline}</span> <span class="small muted">(${daysTo(r.offering_deadline)}d)</span>` : na("None")}</dd>
        <dt>Score</dt><dd>${sc.s100 != null ? `<span class="num">${sc.s100}</span> ` : ""}${ratingBadge(sc.rating)}</dd><dt>Pipeline</dt><dd>${esc(pipe(s.startup_id).pipeline_stage)}</dd></dl>
      </button>`; }).join("")}</div>`;
  } else {
    el.innerHTML = `<div class="tw"><table><thead><tr><th>Company</th><th>Sector · stage</th><th>Status</th><th>Confidence</th><th class="r">Raised</th><th>Valuation / cap</th><th>Deadline</th><th>Score</th><th>Pipeline</th></tr></thead><tbody>
    ${list.map(s => { const r = CUR[s.startup_id], sc = score(s.startup_id);
      return `<tr class="click ${alertOf(s) ? "alert" : ""}" data-go="${s.startup_id}">
      <td><span class="cname">${esc(s.company_name)}</span><span class="sub">${esc(s.sub_sector)}</span></td>
      <td>${esc(s.sector)}<span class="sub">${esc(s.funding_stage)}</span></td>
      <td>${statusBadge(s.fundraising_status)}</td><td>${confBadge(s.verification_confidence)}</td>
      <td class="r" style="white-space:nowrap">${raisedText(s, true)}${marker(s.startup_id, ["capital_raised_usd"]) ? `<br>${marker(s.startup_id, ["capital_raised_usd"])}` : ""}</td>
      <td>${valuationText(r, true)}</td><td style="white-space:nowrap">${deadlineText(r)}</td>
      <td>${sc.s100 != null ? `<span class="num">${sc.s100}</span><br>` : ""}${ratingBadge(sc.rating)}</td><td>${esc(pipe(s.startup_id).pipeline_stage)}</td></tr>`; }).join("")}
    </tbody></table></div>`;
  }
}

/* ---------- PROFILE ---------- */
function fact(k, v, extra = "", big) { return `<div class="fact"><span class="k">${k}</span><span class="v ${big ? "big" : ""}">${v}</span>${extra}</div>`; }
function viewProfile(id) {
  const s = BYID[id], r = CUR[id] || {}, f = finance(s), sc = score(id), p = pipe(id), fl = flags(id);
  const idx = STARTUPS.indexOf(s), prev = STARTUPS[(idx + STARTUPS.length - 1) % STARTUPS.length], next = STARTUPS[(idx + 1) % STARTUPS.length];
  const prior = ROUNDS(id).filter(x => x.is_current_round !== "Yes");
  const raised = num(r.capital_raised_usd), mn = num(r.min_target_usd), mx = num(r.max_target_usd);
  const claims = CLAIMS(id);
  const cats = ["Company profile", "Offering terms", "Capital raised", "Valuation", "Financials", "Traction", "Investors", "Prior funding"];
  const openItems = [];
  if (s.missing_fields && s.missing_fields !== "none") s.missing_fields.split(";").map(x => x.trim()).filter(Boolean).forEach(m => openItems.push(`<li>Missing from research: <span class="mono">${esc(m)}</span></li>`));
  claims.filter(isUnv).forEach(c => openItems.push(`<li><span class="mono small">${c.claim_id}</span> ${esc(c.field_name)}: ${esc(c.claimed_value)} <span class="b ${isConf(c) ? "b-conf" : "b-unv"}">${esc(c.verification_status)}</span>${c.conflict_note ? `<div class="small muted">${esc(c.conflict_note)}</div>` : ""}${c.next_check ? `<div class="small muted">Next check: ${esc(c.next_check)}</div>` : ""} <a class="small" href="${esc(c.source_url)}" target="_blank" rel="noopener">source</a></li>`));
  const log = EDITS.log.filter(l => l.record_id === id).slice().reverse();
  const raw = ["raw_industry", "raw_founded_year", "raw_funding_stage", "raw_round_status", "raw_platform", "raw_revenue_latest_fy", "raw_traction"];
  const rawRound = ["raw_security", "raw_min_target", "raw_max_target", "raw_capital_raised", "raw_investor_count", "raw_valuation", "raw_deadline"];
  const progRow = (label, target) => target ? `<div class="row"><span class="muted">${label} ${money(target, true)}</span><span class="meter ${raised >= target ? "over" : "low"}"><span style="width:${Math.min(100, raised / target * 100)}%"></span></span><span class="num">${pct(raised / target)}</span></div>` : "";

  return `
  <div class="crumb"><button type="button" data-nav="directory">← Directory</button><span class="muted">/</span><span class="mono muted">${id}</span>
    <span style="margin-left:auto;display:flex;gap:6px"><button type="button" class="btn" data-go="${prev.startup_id}" aria-label="Previous startup">← ${esc(prev.company_name)}</button><button type="button" class="btn" data-go="${next.startup_id}" aria-label="Next startup">${esc(next.company_name)} →</button></span></div>
  <section class="phead">
    <div><span class="eyebrow">${esc(s.sector)} · ${esc(s.sub_sector)}</span><h1>${esc(s.company_name)}</h1></div>
    <div class="badges">${statusBadge(s.fundraising_status)}${confBadge(s.verification_confidence)}${ratingBadge(sc.rating)}${fl.unverified ? `<span class="b b-unv">${fl.unverified} unverified claim${fl.unverified > 1 ? "s" : ""}</span>` : ""}${fl.conflicts ? `<span class="b b-conf">${fl.conflicts} open conflict${fl.conflicts > 1 ? "s" : ""}</span>` : ""}</div>
    <div class="meta">
      <span>${esc(s.legal_name)}</span>
      ${s.website ? `<a href="${esc(s.website)}" target="_blank" rel="noopener">${esc(s.website.replace(/^https?:\/\/(www\.)?/, ""))}</a>` : ""}
      <span>${esc(s.hq_city)}${s.hq_state ? ", " + esc(s.hq_state) : ""}</span>
      <span>${esc(s.founded_basis)} ${esc(s.founded_year)}</span>
      <span>${esc(s.funding_stage)}</span>
      ${s.accelerator ? `<span>${esc(s.accelerator)}</span>` : ""}
      <span>${s.verification_date ? 'Verified '+esc(s.verification_date) : 'Not yet reviewed'}</span>
    </div>
    <div class="small muted">${esc(s.verification_basis)}${s.fundraising_detail ? " · " + esc(s.fundraising_detail) : ""}</div>
  </section>
  <nav class="secnav" aria-label="Profile sections">${[["ov", "Overview"], ["round", "Current round"], ["prior", "Prior rounds"], ["fin", "Financials"], ["score", "Scorecard"], ["dd", "Diligence"], ["claims", "Sources"], ["open", "Open items"], ["hist", "Change history"]].map(([a, l]) => `<a href="#${a}" data-anchor="${a}">${l}</a>`).join("")}</nav>

  <section class="panel" id="ov"><h2>Overview</h2>
    <div class="facts">
      ${fact("Business model", esc(s.business_model))}
      ${fact("Traction", s.traction_summary === "Unavailable" ? na("Unavailable") : esc(s.traction_summary) + marker(id, ["traction"]), `<span class="src">${esc(s.traction_source)} ${srcLink(id, ["traction"])}</span>`)}
      ${fact("Founders", esc(s.founders).split("; ").join("<br>"))}
      ${fact("Notable investors", s.notable_investors === "Not disclosed" ? na() : esc(s.notable_investors) + marker(id, ["notable_investors"]), srcLink(id, ["notable_investors"]))}
    </div>
    ${s.data_flags && s.data_flags !== "none" ? `<p class="note">Research flag: ${esc(s.data_flags)}</p>` : ""}
    ${p.suggested_next_action ? `<p class="note"><b>Suggested next action:</b> ${esc(p.suggested_next_action)}</p>` : ""}
  </section>

  <section class="panel" id="round"><div class="ph"><h2>Current round</h2><span class="small muted mono">${esc(r.round_id || "")} · ${esc(r.round_label || "")}</span></div>
    <div class="facts">
      ${fact("Capital raised", raised == null ? na(r.capital_raised_status) : money(raised) + marker(id, ["capital_raised_usd"]), `<span class="src">${esc(r.capital_raised_status || "")} ${srcLink(id, ["capital_raised_usd"], r.source_url)}</span>${num(r.reserved_noncommitted_usd) != null ? `<span class="src">Reserved (non-binding): ${money(num(r.reserved_noncommitted_usd))}</span>` : ""}`, true)}
      ${fact("Valuation / cap", num(r.valuation_amount_usd) == null ? na(r.valuation_type || "Not disclosed") : money(num(r.valuation_amount_usd)) + marker(id, ["valuation_or_cap"]), `<span class="src">${esc(r.valuation_type || "")}</span>${r.valuation_terms_note ? `<span class="src">Tiers: ${esc(r.valuation_terms_note)}</span>` : ""}${num(r.valuation_next_tier_usd) != null ? `<span class="src">Next tier ${money(num(r.valuation_next_tier_usd))}</span>` : ""}${srcLink(id, ["valuation_or_cap"], r.source_url)}`, true)}
      ${fact("Investors", num(r.investor_count) == null ? na() : `<span class="num">${num(r.investor_count)}</span>` + marker(id, ["investor_count"]), `<span class="src">${esc(r.investor_count_note || "")}</span>`, true)}
      ${fact("Offering deadline", r.offering_deadline ? `${fmtDate(r.offering_deadline)} <span class="small muted">(${daysTo(r.offering_deadline)} days)</span>` + (r.deadline_alt_date ? ` <span class="b b-conf" tabindex="0" data-tip="${esc(r.deadline_source || "Form C")} says ${r.offering_deadline}; platform page shows ${r.deadline_alt_date}">▲ Platform shows ${esc(r.deadline_alt_date)}</span>` : "") : r.round_close_date ? `Closed ${fmtDate(r.round_close_date)}` : na("No deadline"), r.deadline_source ? `<span class="src">${esc(r.deadline_source)}</span>` : "")}
      ${fact("Security", esc(r.security_type || "Not disclosed") + marker(id, ["security"]), `${r.discount_pct ? `<span class="src">Discount ${pct(num(r.discount_pct))}</span>` : ""}${r.revenue_share_terms ? `<span class="src">Revenue share: ${esc(r.revenue_share_terms)}</span>` : ""}${num(r.price_per_share_usd) != null ? `<span class="src">Price per share $${num(r.price_per_share_usd)}</span>` : ""}`)}
      ${fact("Targets", mn == null && mx == null ? na("Not applicable") : `<span class="num">${money(mn, true) || "–"} min · ${money(mx, true) || "–"} max</span>`, `<span class="src">${esc(r.target_status || "")}</span>`)}
      ${fact("Platform · regulation", `${esc(r.platform || "")} · ${esc(r.regulation || "")}`, `<span class="src">${esc(r.round_type || "")} · ${esc(r.round_status || "")}</span>`)}
    </div>
    ${raised != null && (mn || mx) ? `<div class="prog" style="margin-top:16px">${progRow("Minimum", mn)}${progRow("Maximum", mx)}</div>` : ""}
    ${r.notes ? `<p class="note">${esc(r.notes)}</p>` : ""}
  </section>

  <section class="panel" id="prior"><h2>Prior rounds</h2>
    ${prior.length ? `<div class="tw"><table><thead><tr><th>Round</th><th>Type</th><th class="r">Raised</th><th>Status</th><th>Source</th></tr></thead><tbody>${prior.map(x => `<tr><td>${esc(x.round_label)}<span class="sub mono">${x.round_id}</span></td><td>${esc(x.round_type)}<span class="sub">${esc(x.security_type)}</span></td><td class="r">${num(x.capital_raised_usd) == null ? na() : `<span class="num">${money(num(x.capital_raised_usd))}</span>`}${marker(id, [x.round_label])}<span class="sub">${esc(x.capital_raised_status)}</span></td><td>${esc(x.round_status)}</td><td>${x.source_url ? `<a href="${esc(x.source_url)}" target="_blank" rel="noopener">${esc(x.source_type)}</a>` : esc(x.source_type)}</td></tr>`).join("")}</tbody></table></div><p class="note">Prior capital (company-stated): ${money(f.prior)}. ${prior.map(x => x.notes).filter(Boolean).map(esc).join(" ")}</p>` : `<p class="muted" style="margin:0">No prior rounds described in the research.</p>`}
  </section>

  <section class="panel" id="fin"><div class="ph"><h2>Financials</h2><span class="small muted">${esc(s.revenue_stage)}</span></div>
    <div class="split">
      <div class="compare hist"><span class="eyebrow">Historical · SEC Form C</span><span class="k small muted">Latest fiscal-year revenue</span>
        <span class="v big num" style="font-size:22px">${f.rev == null ? na(s.latest_fy_revenue_status) : money(f.rev)}</span>${marker(id, ["latest_fy_revenue_usd"])}
        <span class="small muted">${esc(s.latest_fy_revenue_source || s.latest_fy_revenue_status)}</span>${srcLink(id, ["latest_fy_revenue_usd"])}</div>
      <div class="compare claim"><span class="eyebrow">Current · company claim</span><span class="k small muted">ARR run-rate</span>
        <span class="v big num" style="font-size:22px">${f.arr == null ? na(s.current_arr_status) : money(f.arr)}</span>${f.arr != null ? `<span><span class="b b-unv"><i>◆</i>Unverified</span></span>` : ""}
        <span class="small muted">${esc(s.current_arr_status)}${s.current_arr_source ? " · " + esc(s.current_arr_source) : ""}</span></div>
    </div>
    <div class="facts" style="margin-top:16px">
      ${fact("Revenue to date", f.revToDate == null ? na(s.revenue_to_date_status || "Not disclosed") : money(f.revToDate) + marker(id, ["revenue_to_date_usd"]), `<span class="src">${esc(s.revenue_to_date_status)}</span>`)}
      ${fact("Employees", f.emp == null ? na(s.employees_status || "Not disclosed") : `<span class="num">${f.emp}</span>`)}
      ${fact("Long-term debt", f.ltd == null ? na(s.long_term_debt_status || "Not disclosed") : money(f.ltd) + marker(id, ["long_term_debt_usd"]), `<span class="src">${esc(s.long_term_debt_status)}</span>`)}
      ${fact("Valuation ÷ latest-FY revenue", f.valRev == null ? na("Inputs missing") : f.valRev === "n/m" ? na("n/m (no revenue)") : `<span class="num">${mult(f.valRev)}</span>`)}
      ${fact("Valuation ÷ ARR", f.valArr == null ? na("Inputs missing") : f.valArr === "n/m" ? na("n/m") : `<span class="num">${mult(f.valArr)}</span> <span class="b b-unv">ARR unverified</span>`)}
      ${fact("Form C balance sheet", esc(s.form_c_balance_sheet_status))}
    </div>
    <div style="margin-top:16px;max-width:460px"><div class="ph small"><span>Financial data coverage: <b class="num">${f.avail} of 6</b> key fields (${pct(f.cov)})</span>${f.insufficient ? `<span class="b b-low">Insufficient financial data</span>` : `<span class="b b-ok">Sufficient</span>`}</div>
      <div class="meter ${f.insufficient ? "low" : ""}" style="margin-top:6px"><span style="width:${f.cov * 100}%"></span></div></div>
    ${s.financial_notes ? `<p class="note">${esc(s.financial_notes)}</p>` : ""}
  </section>

  <section class="panel" id="score"><div class="ph"><h2>Investment scorecard</h2><button type="button" class="btn" data-scoreopen="${id}">Open in scorecard</button></div>
    ${scoreSummary(id)}
  </section>

  <section class="panel" id="dd"><div class="ph"><h2>Due diligence and pipeline</h2><span class="small muted">Completion ${ddPct(p) == null ? "–" : pct(ddPct(p))} · last updated ${esc(p.last_updated)} by ${esc(p.updated_by)}</span></div>
    ${pipelineForm(id)}
  </section>

  <section class="panel" id="claims"><div class="ph"><h2>Sources and claims</h2><span class="small muted">${claims.length} claims · ${fl.unverified} unverified · ${fl.conflicts} conflicting</span></div>
    <div class="grid g2">${cats.filter(c => claims.some(x => x.claim_category === c)).map(cat => `<div class="claimgrp"><h3>${cat}</h3>${claims.filter(x => x.claim_category === cat).map(c => `
      <div class="claim"><div class="cv"><span class="small muted mono">${esc(c.field_name)}</span><br>${esc(c.claimed_value)}</div>
        <div><span class="b ${isConf(c) ? "b-conf" : isUnv(c) ? "b-unv" : c.verification_status.startsWith("Verified") ? "b-ok" : "b-plain"}" ${c.conflict_note ? `tabindex="0" data-tip="${esc(c.conflict_note)}"` : ""}>${esc(c.verification_status)}</span></div>
        <div class="cm"><span class="mono">${c.claim_id}</span><span>${esc(c.confidence)} confidence</span><a href="${esc(c.source_url)}" target="_blank" rel="noopener">${esc(c.source_type)}</a><span>Review: ${esc(c.review_status)}</span>${c.next_check ? `<span>Next: ${esc(c.next_check)}</span>` : ""}</div></div>`).join("")}</div>`).join("")}</div>
  </section>

  <section class="panel" id="open"><h2>Open verification items</h2>
    ${openItems.length ? `<ul class="issues">${openItems.join("")}</ul>` : `<p class="muted" style="margin:0">No open items. Every claim is verified or marked not disclosed.</p>`}
  </section>

  <section class="panel"><details class="raw"><summary>Original research values</summary>
    <p class="note" style="margin-top:6px">Read-only. Values as they appeared in the source research, before standardizing.</p>
    <dl>${raw.map(k => `<dt>${k}</dt><dd>${esc(s[k]) || na("blank")}</dd>`).join("")}${rawRound.map(k => `<dt>${k}</dt><dd>${esc(r[k]) || na("blank")}</dd>`).join("")}</dl>
  </details></section>

  <section class="panel" id="hist"><h2>Change history</h2>
    ${log.length ? changeTable(log) : `<p class="muted" style="margin:0">No edits yet. Record version ${esc(s.record_version)}, last updated ${esc(s.last_updated)} by ${esc(s.updated_by)}.</p>`}
  </section>`;
}

function changeTable(log) {
  return `<div class="tw"><table><thead><tr><th>Request</th><th>When</th><th>Tab</th><th>Record</th><th>Field</th><th>From</th><th>To</th><th>Status</th></tr></thead><tbody>
  ${log.map(l => `<tr><td class="mono">${l.request_id}</td><td class="num small">${l.submitted_at.replace("T", " ").slice(0, 16)}</td><td>${esc(l.target_tab)}</td><td class="mono">${esc(l.record_id)}</td><td class="mono small">${esc(l.field_name)}</td><td>${esc(l.current_value) || na("blank")}</td><td>${esc(l.proposed_value) || na("blank")}</td><td><span class="b b-ok">${esc(l.status)}</span></td></tr>`).join("")}
  </tbody></table></div>`;
}

/* ---------- SCORECARD ---------- */
function scoreSummary(id) {
  const sc = score(id), r = scoreRow(id), f = finance(BYID[id]);
  return `<div class="grid g3">
    <div class="result"><span class="eyebrow">Screening score</span><span class="bigscore">${sc.s100 ?? "–"}<span class="small muted"> / 100</span></span><div>${ratingBadge(sc.rating)}</div></div>
    <div class="result small">
      <div>Evidence coverage <b class="num">${pct(sc.cov)}</b> <span class="muted">(${sc.wScored} of ${TOTAL_W} weight points scored; rating needs ${pct(T.min_evidence_coverage)})</span></div>
      <div class="meter ${sc.cov < T.min_evidence_coverage ? "low" : ""}"><span style="width:${sc.cov * 100}%"></span></div>
      <div>Insufficient evidence: <b>${sc.ie.length ? esc(sc.ie.join(", ")) : "None"}</b></div>
      <div>Not reviewed: <b class="num">${sc.notRev}</b> of 5 criteria</div>
    </div>
    <div class="result small">
      ${CRIT.map(c => `<div style="display:flex;justify-content:space-between;gap:8px"><span>${c.name} <span class="muted num">(${W[c.key]})</span></span><span class="num">${blank(r[c.key + "_score"]) ? "–" : esc(r[c.key + "_score"])}</span></div>`).join("")}
      <div class="muted">Financial data coverage ${pct(f.cov)} (context only, not part of the score)</div>
    </div></div>`;
}
function viewScorecard() {
  if (!STARTUPS.length) return `<div class="pagehead"><h1>Scorecard</h1></div><section class="panel"><p>Save a startup to begin reviewing it.</p><button class="btn primary" data-nav="discover">Discover startups</button></section>`;
  const id = UI.scoreId in BYID ? UI.scoreId : STARTUPS[0].startup_id, s = BYID[id], r = scoreRow(id), sc = score(id), f = finance(s);
  const all = STARTUPS.map(x => ({ s: x, sc: score(x.startup_id) }));
  const ranked = all.filter(x => x.sc.s100 != null && x.sc.rating !== "Insufficient evidence").sort((a, b) => b.sc.s100 - a.sc.s100);
  const insuff = all.filter(x => x.sc.rating === "Insufficient evidence");
  const unscored = all.filter(x => x.sc.rating === "Not scored");
  const row = (x, i) => `<tr class="click ${x.s.startup_id === id ? "alert" : ""}" data-scorepick="${x.s.startup_id}"><td class="num">${i ?? ""}</td><td><span class="cname">${esc(x.s.company_name)}</span><span class="sub">${esc(x.s.sector)}</span></td><td class="r num">${x.sc.s100 ?? "–"}</td><td>${ratingBadge(x.sc.rating)}</td><td class="r num">${pct(x.sc.cov)}</td><td>${x.sc.ie.length ? esc(x.sc.ie.join(", ")) : "None"}</td></tr>`;
  return `
  <div class="pagehead"><div><span class="eyebrow">Investment scoring</span><h1>Scorecard</h1>
    <p>Score each criterion 1 to 5, or IE when the evidence is undisclosed or unverified. IE and unreviewed criteria are left out of the score, never counted as low. Weights: ${CRIT.map(c => `${labelOf(c.key)} ${W[c.key]}`).join(", ")}.</p></div>
    <label class="chk">Startup <select id="scorepick">${STARTUPS.map(x => `<option value="${x.startup_id}" ${x.startup_id === id ? "selected" : ""}>${esc(x.company_name)} (${x.startup_id})</option>`).join("")}</select></label></div>

  <div class="scorelayout">
    <section class="panel">
      <div class="ph"><div><h2>${esc(s.company_name)}</h2><div class="small muted">${esc(s.sector)} · ${esc(s.funding_stage)} · ${esc(s.traction_summary)}</div></div><div class="badges">${statusBadge(s.fundraising_status)}${confBadge(s.verification_confidence)}</div></div>
      ${CRIT.map(c => { const v = r[c.key + "_score"] ?? "", ev = r[c.key + "_evidence"] ?? ""; return `
      <div class="crit">
        <div><h3>${c.name} <span class="muted num small">· weight ${W[c.key]}</span></h3>
          <div class="rubric"><b>1</b><span>${esc(c.r1)}</span><b>3</b><span>${esc(c.r3)}</span><b>5</b><span>${esc(c.r5)}</span><b>Cite</b><span>${esc(c.ev)}</span></div></div>
        <div style="display:flex;flex-direction:column;gap:8px;min-width:0">
          <div class="scorebtns" role="group" aria-label="${c.name} score">${["1", "2", "3", "4", "5", "IE"].map(o => `<button type="button" data-score="${c.key}" data-val="${o}" aria-pressed="${v === o}">${o}</button>`).join("")}<button type="button" class="clr" data-score="${c.key}" data-val="">Clear</button></div>
          <textarea id="ev-${c.key}" data-evidence="${c.key}" placeholder="Evidence (required with a score): cite a claim ID, filing or source" aria-label="${c.name} evidence">${esc(ev)}</textarea>
          ${v && v !== "IE" && !ev.trim() ? `<div class="warnline">Add a source to support this score.</div>` : ""}
          ${!blank(v) && v !== "IE" ? `<div class="small muted">Points: <span class="num">${(+v / 5 * W[c.key]).toFixed(1)}</span> of ${W[c.key]}</div>` : ""}
        </div></div>`; }).join("")}
      <div class="fieldgrid" style="margin-top:14px;border-top:1px solid var(--line);padding-top:14px">
        <label>Analyst<input type="text" id="sc-analyst" data-scfield="analyst" value="${esc(r.analyst || "")}" placeholder="Name or email"></label>
        <label>Scored on<input type="date" id="sc-date" data-scfield="scored_on" value="${esc(r.scored_on || "")}"></label>
      </div>
      <label class="small muted" style="display:flex;flex-direction:column;gap:4px;margin-top:10px">Analyst notes<textarea id="sc-notes" data-scfield="analyst_notes">${esc(r.analyst_notes || "")}</textarea></label>
    </section>
    <aside class="panel sticky"><h2>Result</h2><div id="scoreresult">${scoreSummaryCompact(id)}</div></aside>
  </div>

  <section class="panel"><div class="ph"><h2>Comparison</h2><span class="small muted">Ranked by screening score; insufficient-evidence and unscored startups are grouped separately</span></div>
    <div class="tw"><table><thead><tr><th>#</th><th>Company</th><th class="r">Score</th><th>Rating</th><th class="r">Coverage</th><th>IE criteria</th></tr></thead><tbody>
      ${ranked.length ? ranked.map((x, i) => row(x, i + 1)).join("") : `<tr><td colspan="6" class="muted">No startup has enough scored criteria for a rating yet. Pick one above and enter scores.</td></tr>`}
      ${insuff.length ? `<tr><th colspan="6">Insufficient evidence (${insuff.length})</th></tr>` + insuff.map(x => row(x)).join("") : ""}
      ${unscored.length ? `<tr><th colspan="6">Not scored (${unscored.length})</th></tr>` + unscored.map(x => row(x)).join("") : ""}
    </tbody></table></div>
  </section>`;
}
function scoreSummaryCompact(id) {
  const sc = score(id), f = finance(BYID[id]);
  return `<div class="result">
    <div><span class="bigscore">${sc.s100 ?? "–"}</span><span class="muted"> / 100</span></div>
    <div>${ratingBadge(sc.rating)}</div>
    <div class="small">Evidence coverage <b class="num">${pct(sc.cov)}</b> <span class="muted">· ${sc.wScored}/${TOTAL_W} weight</span></div>
    <div class="meter ${sc.cov < T.min_evidence_coverage ? "low" : ""}"><span style="width:${sc.cov * 100}%"></span></div>
    <div class="small">Insufficient evidence: <b>${sc.ie.length ? esc(sc.ie.join(", ")) : "None"}</b></div>
    <div class="small">Not reviewed: <b class="num">${sc.notRev}</b></div>
    ${sc.missingEv.length ? `<div class="warnline">Evidence missing for ${esc(sc.missingEv.join(", "))}</div>` : ""}
    <div class="small muted" style="border-top:1px solid var(--line);padding-top:10px">Thresholds: Strong ≥ ${T.strong}, Promising ≥ ${T.promising}, Watchlist ≥ ${T.watchlist}. Financial data coverage ${pct(f.cov)} is context only.</div>
  </div>`;
}

/* ---------- PIPELINE ---------- */
function sel(attrs, opts, v, blankLabel) {
  return `<select ${attrs}>${blankLabel != null ? `<option value="">${blankLabel}</option>` : ""}${opts.map(o => `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
}
function pipelineForm(id) {
  const p = pipe(id);
  return `<div class="fieldgrid">
    <label>Pipeline stage${sel(`data-pipe="${id}" data-field="pipeline_stage"`, S.pipeline_stage, p.pipeline_stage)}</label>
    <label>Priority${sel(`data-pipe="${id}" data-field="priority"`, S.priority, p.priority, "Not set")}</label>
    <label>Owner<input type="text" id="own-${id}" data-pipe="${id}" data-field="owner" value="${esc(p.owner || "")}" placeholder="Unassigned"></label>
    <label>Next action<input type="text" id="na-${id}" data-pipe="${id}" data-field="next_action" value="${esc(p.next_action || "")}" placeholder="${esc(p.suggested_next_action || "")}"></label>
    <label>Next action date<input type="date" id="nad-${id}" data-pipe="${id}" data-field="next_action_date" value="${esc(p.next_action_date || "")}"></label>
    <label>Decision${sel(`data-pipe="${id}" data-field="decision"`, S.decision, p.decision, "None")}</label>
    <label>Memo status${sel(`data-pipe="${id}" data-field="memo_status"`, S.memo_status, p.memo_status, "Not set")}</label>
  </div>
  <h3 style="margin:16px 0 8px">Diligence checks</h3>
  <div class="ddgrid">${DD.map(([k, l]) => `<label>${l}${sel(`data-pipe="${id}" data-field="${k}"`, S.dd_status, p[k])}</label>`).join("")}</div>`;
}
function ddDots(p) {
  return `<span class="dots" aria-hidden="true">${DD.map(([k, l]) => { const v = p[k] || ""; const c = v === "Done" ? "Done" : v === "In progress" ? "In" : v === "Blocked" ? "Blocked" : v === "N/A" ? "NA" : ""; return `<span class="dot ${c}" title="${l}: ${esc(v)}"></span>`; }).join("")}</span>`;
}
function viewPipeline() {
  const view = UI.pipeView;
  const head = `<div class="pagehead"><div><span class="eyebrow">Due diligence tracker</span><h1>Deal pipeline</h1>
    <p>Move startups between stages and track the six diligence checks. Changes are saved in this browser and logged as applied change requests, ready for the Sheets sync.</p></div>
    <div class="seg" role="group" aria-label="View"><button type="button" data-pview="board" aria-pressed="${view === "board"}">Board</button><button type="button" data-pview="table" aria-pressed="${view === "table"}">Table</button></div></div>`;
  if (view === "table") {
    return head + `<div class="tw"><table><thead><tr><th>Company</th><th>Stage</th><th>Priority</th><th>Owner</th>${DD.map(d => `<th>${d[1]}</th>`).join("")}<th class="r">Done</th><th>Suggested next action</th></tr></thead><tbody>
    ${STARTUPS.map(s => { const id = s.startup_id, p = pipe(id); return `<tr><td><button type="button" class="sortbtn cname" data-go="${id}">${esc(s.company_name)}</button><span class="sub">${esc(s.fundraising_status)}</span></td>
      <td>${sel(`data-pipe="${id}" data-field="pipeline_stage" aria-label="Stage"`, S.pipeline_stage, p.pipeline_stage)}</td>
      <td>${sel(`data-pipe="${id}" data-field="priority" aria-label="Priority"`, S.priority, p.priority, "–")}</td>
      <td><input type="text" id="tow-${id}" style="width:110px" data-pipe="${id}" data-field="owner" value="${esc(p.owner || "")}" aria-label="Owner"></td>
      ${DD.map(([k, l]) => `<td>${sel(`data-pipe="${id}" data-field="${k}" aria-label="${l}"`, S.dd_status, p[k])}</td>`).join("")}
      <td class="r num">${ddPct(p) == null ? "–" : pct(ddPct(p))}</td><td class="small" style="min-width:240px">${esc(p.suggested_next_action)}</td></tr>`; }).join("")}
    </tbody></table></div>`;
  }
  return head + `<div class="kanban">${S.pipeline_stage.map(stage => { const items = STARTUPS.filter(s => pipe(s.startup_id).pipeline_stage === stage);
    return `<section class="col" data-stage="${esc(stage)}"><h3>${esc(stage)} <span class="n">${items.length}</span></h3>
      ${items.length ? items.map(s => { const id = s.startup_id, p = pipe(id), r = CUR[id], d = daysTo(r?.offering_deadline), sc = score(id), dp = ddPct(p);
        return `<article class="kcard" draggable="true" data-drag="${id}">
          <div class="t"><button type="button" data-go="${id}">${esc(s.company_name)}</button>${p.priority ? `<span class="b ${p.priority === "High" ? "b-low" : p.priority === "Medium" ? "b-medium" : "b-plain"}">${esc(p.priority)}</span>` : ""}</div>
          <div class="badges">${statusBadge(s.fundraising_status)}${d != null && d >= 0 ? `<span class="b ${d <= T.alert_days ? "b-conf" : "b-plain"}">${d}d to deadline</span>` : ""}</div>
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">${ddDots(p)}<span class="num small">${dp == null ? "–" : pct(dp)} DD</span></div>
          <div class="small"><span class="muted">Owner</span> ${p.owner ? esc(p.owner) : `<span class="na">Unassigned</span>`}${sc.s100 != null ? ` · <span class="muted">Score</span> <span class="num">${sc.s100}</span>` : ""}</div>
          <div class="small">${p.next_action ? `<b>Next:</b> ${esc(p.next_action)}${p.next_action_date ? ` <span class="num muted">${esc(p.next_action_date)}</span>` : ""}` : `<span class="muted">Suggested:</span> ${esc(p.suggested_next_action)}`}</div>
          ${sel(`data-pipe="${id}" data-field="pipeline_stage" aria-label="Move ${esc(s.company_name)} to stage"`, S.pipeline_stage, p.pipeline_stage)}
        </article>`; }).join("") : `<div class="empty">Drag a card here or use its stage menu</div>`}
    </section>`; }).join("")}</div>`;
}

/* ---------- FINANCIALS ---------- */
function viewFinancials() {
  const rows = STARTUPS.map(s => ({ s, f: finance(s), r: CUR[s.startup_id] || {} }));
  const revReported = rows.filter(x => x.f.rev != null);
  const revPos = revReported.filter(x => x.f.rev > 0);
  const vals = rows.filter(x => x.f.val != null).sort((a, b) => b.f.val - a.f.val);
  const vMax = niceTicks(Math.max(...vals.map(x => x.f.val)), 5);
  const multRows = rows.filter(x => typeof x.f.valRev === "number").sort((a, b) => b.f.valRev - a.f.valRev);
  const nm = rows.filter(x => x.f.valRev === "n/m");
  const logMax = 5; // up to 100,000x
  const logTicks = [0, 1, 2, 3, 4, 5];
  const covItems = rows.map(x => ({ id: x.s.startup_id, label: x.s.company_name, value: x.f.avail, alt: x.f.insufficient, display: `${x.f.avail}/6`, tip: `${x.s.company_name}: ${x.f.avail} of 6 key fields (${pct(x.f.cov)})${x.f.insufficient ? " · insufficient financial data" : ""}` })).sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
  return `
  <div class="pagehead"><div><span class="eyebrow">Financial analysis</span><h1>Financials and valuation</h1>
    <p>Historical revenue comes from each company's SEC Form C (most recent fiscal year). ARR and revenue-to-date are company claims and stay unverified. Blank figures are unavailable and never counted as zero.</p></div></div>
  <section class="kpis">
    <div class="kpi"><span class="v">${revReported.length}</span><span class="l">Form C revenue reported</span><span class="s">${revPos.length} with revenue above $0 · ${revReported.length - revPos.length} reported $0</span></div>
    <div class="kpi"><span class="v">${rows.filter(x => x.f.arr != null).length}</span><span class="l">ARR claims</span><span class="s">Company-stated, unverified</span></div>
    <div class="kpi"><span class="v">${money(median(vals.map(x => x.f.val)), true)}</span><span class="l">Median valuation or cap</span><span class="s">${vals.length} disclosed · ${rows.length - vals.length} excluded</span></div>
    <div class="kpi"><span class="v">${rows.filter(x => x.f.ltd != null).length}</span><span class="l">Long-term debt reported</span><span class="s">From Form C</span></div>
    <div class="kpi warnk"><span class="v">${rows.filter(x => x.f.insufficient).length}</span><span class="l">Insufficient financial data</span><span class="s">Under ${pct(T.financial_coverage)} coverage</span></div>
  </section>

  <div class="grid g2">
    <section class="panel"><div class="ph"><h2>Current valuation or cap</h2><span class="small muted">${vals.length} disclosed of ${rows.length}</span></div>
      ${barList(vals.map(x => ({ id: x.s.startup_id, label: x.s.company_name, value: x.f.val, display: money(x.f.val, true), tip: `${x.s.company_name}: ${money(x.f.val)} ${x.r.valuation_type}${x.r.valuation_terms_note ? " · " + x.r.valuation_terms_note : ""}`, alt: !/SAFE/.test(x.r.valuation_type) })), { max: vMax[vMax.length - 1], ticks: vMax, fmt: v => money(v, true), link: true })}
      <div class="legend"><span><i class="sw"></i>SAFE cap</span><span><i class="sw alt"></i>Priced-round valuation</span></div>
      <p class="note">Not disclosed: ${rows.filter(x => x.f.val == null).map(x => esc(x.s.company_name)).join(", ")}.</p></section>

    <section class="panel"><div class="ph"><h2>Valuation ÷ latest-FY revenue</h2><span class="small muted">Log scale</span></div>
      ${barList(multRows.map(x => ({ id: x.s.startup_id, label: x.s.company_name, value: Math.log10(x.f.valRev), display: mult(x.f.valRev), tip: `${x.s.company_name}: ${money(x.f.val)} ÷ ${money(x.f.rev)} Form C revenue = ${mult(x.f.valRev)}` })), { max: logMax, ticks: logTicks, fmt: v => ["1x", "10x", "100x", "1Kx", "10Kx", "100Kx"][v] ?? "", link: true })}
      <p class="note">n/m (no revenue, $0 on Form C): ${nm.map(x => esc(x.s.company_name)).join(", ")}. Inputs missing: ${rows.filter(x => x.f.valRev == null).map(x => esc(x.s.company_name)).join(", ")}.</p>
      ${rows.filter(x => typeof x.f.valArr === "number").map(x => `<p class="note">${esc(x.s.company_name)} on company-stated ARR: ${mult(x.f.valArr)} (unverified).</p>`).join("")}</section>
  </div>

  <section class="panel"><div class="ph"><h2>Financial data coverage</h2><span class="small muted">Key fields with a number: FY revenue, ARR, employees, long-term debt, current raised, current valuation</span></div>
    ${barList(covItems, { max: 6, ticks: [0, 1, 2, 3, 4, 5, 6], fmt: v => String(v), link: true })}
    <div class="legend"><span><i class="sw"></i>Sufficient (≥ 3 of 6)</span><span><i class="sw alt"></i>Insufficient financial data</span></div></section>

  <section class="panel"><h2>All startups</h2>
    <div class="tw"><table><thead><tr><th>Company</th><th>Revenue stage</th><th class="r">Latest-FY revenue<br><span style="text-transform:none">Form C</span></th><th class="r">ARR<br><span style="text-transform:none">company claim</span></th><th class="r">Revenue to date</th><th class="r">Long-term debt</th><th class="r">Current raised</th><th>Valuation / cap</th><th class="r">Val ÷ rev</th><th class="r">Prior capital</th><th>Coverage</th></tr></thead><tbody>
    ${rows.map(({ s, f, r }) => `<tr class="click" data-go="${s.startup_id}"><td><span class="cname">${esc(s.company_name)}</span><span class="sub">${esc(s.sector)}</span></td><td class="small">${esc(s.revenue_stage)}</td>
      <td class="r">${f.rev == null ? na(s.latest_fy_revenue_status) : `<span class="num">${money(f.rev)}</span>`}</td>
      <td class="r">${f.arr == null ? na(s.current_arr_status) : `<span class="num">${money(f.arr)}</span> <span class="b b-unv">◆</span>`}</td>
      <td class="r">${f.revToDate == null ? na(s.revenue_to_date_status || "Not disclosed") : `<span class="num">${money(f.revToDate)}</span>`}</td>
      <td class="r">${f.ltd == null ? na(s.long_term_debt_status) : `<span class="num">${money(f.ltd, true)}</span>`}</td>
      <td class="r">${raisedText(s, true)}</td><td>${valuationText(r, true)}</td>
      <td class="r">${f.valRev == null ? na("–") : f.valRev === "n/m" ? na("n/m") : `<span class="num">${mult(f.valRev)}</span>`}</td>
      <td class="r">${f.prior == null ? na("–") : `<span class="num">${money(f.prior, true)}</span>`}</td>
      <td style="min-width:110px"><span class="num small">${f.avail}/6</span>${f.insufficient ? ` <span class="b b-low">Insufficient</span>` : ""}</td></tr>`).join("")}
    </tbody></table></div></section>`;
}

/* ---------- CHANGES ---------- */
let confirmReset = false;
function viewChanges() {
  const log = EDITS.log.slice().reverse();
  return `<div class="pagehead"><div><span class="eyebrow">Change Requests</span><h1>Local edits</h1>
    <p>Your score and pipeline edits are saved only in this browser. Copy them as CSV to share with teammates or keep a backup. Edits do not sync between devices.</p></div>
    <div class="controls"><button type="button" class="btn primary" id="copycsv" ${log.length ? "" : "disabled"}>Copy as CSV</button>${log.length ? `<button type="button" class="btn danger" id="resetask">Discard local edits</button>` : ""}</div></div>
  ${confirmReset ? `<div class="confirm">Discard all ${log.length} local edits and restore the imported data? <button type="button" class="btn danger" id="resetyes">Discard</button><button type="button" class="btn" id="resetno">Keep</button></div>` : ""}
  ${log.length ? changeTable(log) : `<div class="panel empty">No local edits yet. Score a startup or move one in the pipeline and it appears here.</div>`}`;
}
function logCSV() {
  const cols = ["request_id", "submitted_at", "submitted_by", "target_tab", "record_id", "field_name", "current_value", "proposed_value", "evidence_url", "rationale", "status", "reviewer", "reviewed_at", "review_note", "applied_at", "record_version_at_submit"];
  const q = v => { v = String(v ?? ""); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  return [cols.join(","), ...EDITS.log.map(l => cols.map(c => q(c === "applied_at" ? l.submitted_at : l[c])).join(","))].join("\n");
}

/* ---------- events ---------- */
document.addEventListener("click", e => {
  const t = e.target;
  const nav = t.closest("[data-nav]"); if (nav) { go(nav.dataset.nav); return; }
  if (t.closest("#logbtn")) { go("changes"); return; }
  const anchor = t.closest("[data-anchor]"); if (anchor) { e.preventDefault(); const el = document.getElementById(anchor.dataset.anchor); if (el) scrollTo({ top: el.getBoundingClientRect().top + scrollY - 140, behavior: "smooth" }); return; }
  if (t.closest("select, input, textarea, a")) return;
  const so = t.closest("[data-scoreopen]"); if (so) { UI.scoreId = so.dataset.scoreopen; saveUI(); go("scorecard"); return; }
  const sp = t.closest("[data-scorepick]"); if (sp) { UI.scoreId = sp.dataset.scorepick; saveUI(); render(); scrollTo(0, 0); return; }
  const g = t.closest("[data-go]"); if (g) { go("profile", g.dataset.go); return; }
  const vb = t.closest("[data-view]"); if (vb) { UI.directory.view = vb.dataset.view; saveUI(); render(); renderDirResults(); return; }
  const pv = t.closest("[data-pview]"); if (pv) { UI.pipeView = pv.dataset.pview; saveUI(); render(); return; }
  const sb = t.closest("[data-score]"); if (sb) { const ev = document.getElementById("ev-" + sb.dataset.score); if (ev) setField("Investment Scorecard", UI.scoreId, sb.dataset.score + "_evidence", ev.value); setField("Investment Scorecard", UI.scoreId, sb.dataset.score + "_score", sb.dataset.val); const y = scrollY; render(); scrollTo(0, y); return; }
  if (t.closest("#clearf")) { UI.directory.f = {}; UI.directory.q = ""; saveUI(); render(); renderDirResults(); return; }
  if (t.closest("#copycsv")) { const csv = logCSV(); navigator.clipboard.writeText(csv).then(() => toast("Copied " + EDITS.log.length + " change requests as CSV")).catch(() => { const ta = document.createElement("textarea"); ta.value = csv; ta.style.cssText = "width:100%;height:200px;margin-top:12px"; $("#app").appendChild(ta); ta.select(); toast("Select-all and copy the CSV below"); }); return; }
  if (t.closest("#resetask")) { confirmReset = true; render(); return; }
  if (t.closest("#resetno")) { confirmReset = false; render(); return; }
  if (t.closest("#resetyes")) { EDITS = { scores: {}, pipeline: {}, log: [] }; save(); confirmReset = false; render(); toast("Local edits discarded"); return; }
});
document.addEventListener("input", e => {
  const t = e.target;
  if (t.id === "q") { UI.directory.q = t.value; saveUI(); renderDirResults(); }
  if (t.id === "within") { UI.directory.f.within = t.value; saveUI(); renderDirResults(); }
});
document.addEventListener("change", e => {
  const t = e.target;
  if (t.id === "sort") { UI.directory.sort = t.value; saveUI(); renderDirResults(); return; }
  if (t.id === "scorepick") { UI.scoreId = t.value; saveUI(); render(); return; }
  if (t.dataset.filter && t.id !== "within") { UI.directory.f[t.dataset.filter] = t.type === "checkbox" ? t.checked : t.value; saveUI(); render(); renderDirResults(); return; }
  if (t.dataset.evidence) { if (setField("Investment Scorecard", UI.scoreId, t.dataset.evidence + "_evidence", t.value)) { const a = $("#scoreresult"); if (a) a.innerHTML = scoreSummaryCompact(UI.scoreId); } return; }
  if (t.dataset.scfield) { setField("Investment Scorecard", UI.scoreId, t.dataset.scfield, t.value); return; }
  if (t.dataset.pipe) { if (setField("Deal Pipeline", t.dataset.pipe, t.dataset.field, t.value)) { if (t.tagName === "SELECT") { const y = scrollY; render(); scrollTo(0, y); } toast("Saved " + t.dataset.field.replace(/_/g, " ") + " for " + BYID[t.dataset.pipe].company_name); } return; }
});
/* drag and drop on the board */
document.addEventListener("dragstart", e => { const c = e.target.closest?.("[data-drag]"); if (c) { e.dataTransfer.setData("text/plain", c.dataset.drag); e.dataTransfer.effectAllowed = "move"; } });
document.addEventListener("dragover", e => { const col = e.target.closest?.("[data-stage]"); if (col) { e.preventDefault(); document.querySelectorAll(".col.drop").forEach(x => x !== col && x.classList.remove("drop")); col.classList.add("drop"); } });
document.addEventListener("dragleave", e => { const col = e.target.closest?.("[data-stage]"); if (col && !col.contains(e.relatedTarget)) col.classList.remove("drop"); });
document.addEventListener("drop", e => { const col = e.target.closest?.("[data-stage]"); if (!col) return; e.preventDefault(); const id = e.dataTransfer.getData("text/plain"); if (BYID[id] && setField("Deal Pipeline", id, "pipeline_stage", col.dataset.stage)) { render(); toast(BYID[id].company_name + " moved to " + col.dataset.stage); } else render(); });

const VS = window.VentureScout;
const STAGES = VS.STAGES;
const SCOUT = { form:null,saveError:'',stageFilter:'',importMsg:'' };
const DISC = { data:null,status:null,error:'',statusError:'',loading:false,loaded:false,selected:null,f:{q:'',industry:'',stage:'',evidence:'',minConfidence:'',minScore:'',sort:'newest'},limit:60 };
const account = window.ventureAccount || {companies:[],error:''};
const options = (items,current,labels={}) => items.map(x=>`<option value="${esc(x)}" ${x===current?'selected':''}>${esc(labels[x]||x)}</option>`).join('');
const marketUI=window.createMarketUI({esc,render:()=>render(),count:()=>account.companies.length,track:c=>startTracking(c)});
function startTracking(c) {
  if(!c){toast('Company details are not available.');return;}
  SCOUT.form={name:c.name||'',website:c.website||'',industry:c.industry||'',location:c.location||c.headquarters||'',stage:STAGES.includes(c.stage||c.funding_stage)?(c.stage||c.funding_stage):'Not disclosed',notes:c.description||'',source:c.source||'VentureScout discovery',sourceURL:c.sourceURL||c.primary_source_url||''};
  SCOUT.saveError='';go('tracking');
}
const GITHUB_ACTIONS='https://github.com/BagofRamen27/Venture-capital-tracker-/actions/workflows/site.yml';
const EVIDENCE_LABEL={regulatory_filing:'SEC filing',confirmed:'Corroborated',company_announced:'Company-announced',reported:'Reported (1 source)',analyst_entered:'Analyst-entered',target:'Target (not raised)',rumor:'Rumour (unconfirmed)',community_sourced:'Community-sourced (Wikidata)'};
const evBadge=st=>st?`<span class="b ${st==='confirmed'||st==='regulatory_filing'?'b-ok':st==='rumor'||st==='target'?'b-conf':'b-unv'}" tabindex="0" data-tip="${esc(DISC.data?.evidence_statuses?.[st]||'')}">${esc(EVIDENCE_LABEL[st]||st)}</span>`:'';
const confB=c=>c?.label?`<span class="b b-${esc(c.label.toLowerCase())}" tabindex="0" data-tip="Data confidence ${esc(c.score)}/100: how well-supported this record is, not investment quality">${esc(c.label)} confidence</span>`:'';
const scoreB=s=>s?.total!=null?`<span class="b b-plain" tabindex="0" data-tip="Preliminary research indicator (coverage ${Math.round((s.coverage||0)*100)}% of weights). Not an investment recommendation.">Score ${esc(s.total)} · ${esc(s.rating)}</span>`:'';
const FLAG_TEXT={conflicting_funding:'Conflicting funding figures',possible_duplicate:'Possible duplicate',stale:'Stale information',name_collision:'Similar name to another company'};
async function loadDiscoveryData() {
  if(DISC.loading||DISC.loaded)return;
  DISC.loading=true;
  const get=async f=>{const r=await fetch('data/'+f,{cache:'no-cache'});if(r.status===404)throw new Error('Not available yet: the first daily update has not run.');if(!r.ok)throw new Error('Could not load '+f+'.');return r.json();};
  const [d,s]=await Promise.allSettled([get('discovery.json'),get('status.json')]);
  if(d.status==='fulfilled')DISC.data=d.value;else DISC.error=d.reason.message;
  if(s.status==='fulfilled')DISC.status=s.value;else DISC.statusError=s.reason.message;
  DISC.loading=false;DISC.loaded=true;if(['discover','status'].includes(route.view))render();
}
function viewDiscover() {
  queueMicrotask(loadDiscoveryData);
  const all=DISC.data?.companies||[], f=DISC.f;
  const rows=VS.filterDiscovery(all,f);
  const uniq=k=>[...new Set(all.map(c=>c[k]).filter(Boolean))].sort();
  const sel=all.find(c=>c.id===DISC.selected);
  return `<div class="pagehead"><div><span class="eyebrow">Automated discovery</span><h1>Discovered startups</h1><p>Companies found in startup news, press releases, Hacker News launches and SEC Form D filings. Updated daily.</p></div><button class="btn" data-nav="tracking">My startups (${account.companies.length})</button></div>
  ${DISC.loading?'<div class="panel" role="status">Loading discovered companies…</div>':''}
  ${DISC.error?`<div class="panel" role="alert">${esc(DISC.error)} <a href="${GITHUB_ACTIONS}" target="_blank" rel="noopener">Open the daily update</a></div>`:''}
  ${DISC.data?`<p class="note">Updated ${esc(new Date(DISC.data.generated_at+'Z').toLocaleString())}. ${esc(DISC.data.disclaimer)}</p>
  ${sel?discoveredProfile(sel):''}
  <form id="disc-filters" class="panel fieldgrid">
    <label>Search<input name="q" value="${esc(f.q)}" placeholder="Name, industry, city…" maxlength="100"></label>
    <label>Industry<select name="industry"><option value="">All</option>${options(uniq('industry'),f.industry)}</select></label>
    <label>Funding stage<select name="stage"><option value="">All</option>${options(uniq('funding_stage'),f.stage)}</select></label>
    <label>Funding evidence<select name="evidence"><option value="">All</option>${options(Object.keys(EVIDENCE_LABEL).filter(k=>k!=='community_sourced'),f.evidence,EVIDENCE_LABEL)}</select></label>
    <label>Min. data confidence<select name="minConfidence">${options(['','45','70'],f.minConfidence,{'':'Any','45':'Medium or higher','70':'High'})}</select></label>
    <label>Min. score<select name="minScore">${options(['','45','60','75'],f.minScore,{'':'Any','45':'45+','60':'60+','75':'75+'})}</select></label>
    <label>Sort by<select name="sort">${options(['newest','score','confidence','funding','name'],f.sort,{newest:'Newest discovered',score:'Investment score',confidence:'Data confidence',funding:'Latest funding amount',name:'Name'})}</select></label>
  </form>
  <p>${rows.length.toLocaleString()} of ${all.length.toLocaleString()} companies</p>
  <div class="scout-grid">${rows.slice(0,DISC.limit).map(c=>`<article class="panel scout-card"><span class="eyebrow">${esc(c.industry||'Industry not identified')} · ${esc(c.funding_stage||'Stage not disclosed')}</span><h2><button class="link" data-disc="${c.id}">${esc(c.name)}</button></h2>
    <p>${esc(c.headquarters||'Location not disclosed')}${c.founded_year?' · Founded '+esc(c.founded_year):''}</p>
    ${c.description?`<p class="muted">${esc(c.description)}</p>`:''}
    ${fundingLine(c)}
    <div class="badges">${confB(c.confidence)}${scoreB(c.investment_score)}${(c.flags||[]).map(x=>`<span class="b b-conf">${esc(FLAG_TEXT[x]||x)}</span>`).join('')}</div>
    <p class="muted small">Found via ${esc(c.discovered_via||'unknown')} · ${esc(c.first_discovered_at?new Date(c.first_discovered_at+'Z').toLocaleDateString():'')}</p>
    <div class="row"><button class="btn primary" data-disc="${c.id}">Research</button><button class="btn" data-disc-track="${c.id}">Track</button>${c.website?`<a href="${esc(c.website)}" target="_blank" rel="noopener noreferrer">Website</a>`:''}</div></article>`).join('')||'<div class="panel empty">No companies match these filters.</div>'}</div>
  ${rows.length>DISC.limit?`<div class="scout-pagination"><button class="btn" id="disc-more">Show more</button></div>`:''}`:''}`;
}
function fundingLine(c) {
  if(c.latest_funding.amount!=null)return `<p>Latest funding: <b>${esc(c.latest_funding.display)}</b> ${evBadge(c.latest_funding.evidence_status)}</p>`;
  const r=c.funding_rounds.find(x=>x.amount!=null);
  return r?`<p>Funding mentioned: <b>${esc(r.amount_display)}</b> ${evBadge(r.evidence_status)}</p>`:'<p>Latest funding: <b>Not disclosed</b></p>';
}
function discoveredProfile(c) {
  const sc=c.score;
  const link=(u,t)=>u?`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(t)}</a>`:esc(t);
  return `<section class="panel" id="disc-profile"><div class="ph"><div><span class="eyebrow">${esc(c.industry||'Industry not identified')} · ${esc(c.review_status)}</span><h2>${esc(c.name)}</h2></div><div class="controls"><button class="btn primary" data-disc-track="${c.id}">Track</button><button class="btn" id="disc-close">Close</button></div></div>
  <div class="badges">${confB(c.confidence)}${scoreB(c.investment_score)}${(c.flags||[]).map(x=>`<span class="b b-conf">${esc(FLAG_TEXT[x]||x)}</span>`).join('')}</div>
  <dl class="market-facts">
    <dt>Website</dt><dd>${c.website?link(c.website,c.website):'Not identified'}</dd>
    <dt>Headquarters · founded</dt><dd>${esc(c.headquarters||'Not disclosed')} · ${esc(c.founded_year||'Not disclosed')}</dd>
    <dt>Founders</dt><dd>${esc(c.founders||'Not disclosed')}</dd>
    ${c.key_people?`<dt>Executives listed on SEC filing</dt><dd>${esc(c.key_people)}</dd>`:''}
    <dt>Investors named in sources</dt><dd>${esc((c.investors||[]).join(', ')||'Not disclosed')}</dd>
    <dt>Total funding</dt><dd>${esc(c.total_funding.display)}<div class="small muted">${esc(c.total_funding.basis||'')}</div></dd>
    <dt>Valuation · revenue</dt><dd>${esc(c.valuation.display)} · ${esc(c.revenue.display)}</dd>
  </dl>
  ${sc?`<h3>Preliminary thesis</h3><p>${esc(sc.thesis)}</p>${sc.risks?.length?`<h3>Risks and gaps</h3><ul>${sc.risks.map(r=>`<li>${esc(r)}</li>`).join('')}</ul>`:''}
  <h3>Investment score: ${sc.total??'not scored'} <span class="muted small">(${esc(sc.rating)}, ${Math.round(sc.coverage*100)}% of weights scorable)</span></h3>
  <div class="tw"><table><thead><tr><th>Factor</th><th class="r">Weight</th><th class="r">Score</th><th>Evidence or reason</th></tr></thead><tbody>${sc.factors.map(x=>`<tr><td>${esc(x.label)}<div class="small muted">${esc(x.method)}</div></td><td class="r">${esc(x.weight)}%</td><td class="r">${x.score==null?'<span class="na">Unscorable</span>':esc(x.score)}${x.override?'<div class="small">analyst</div>':''}</td><td>${x.evidence.length?x.evidence.map(e=>`<div>${link(e.url,e.text)}</div>`).join(''):`<span class="muted">${esc(x.unscorable_reason||'')}</span>`}</td></tr>`).join('')}</tbody></table></div>
  <p class="note">${esc(sc.disclaimer)}</p>`:''}
  <h3>Funding history</h3>${c.funding_rounds.length?c.funding_rounds.map(r=>`<article class="funding-round"><h3>${esc(r.round_type||'Round not specified')} · ${esc(r.amount_display)} ${evBadge(r.evidence_status)}${r.conflict?' <span class="b b-conf">Conflict</span>':''}</h3><p>${esc(r.announced_date||'Date not supplied')}${r.publishers?.length?' · '+r.publishers.map(esc).join(', '):''}</p>${r.investors.length?`<p>${r.investors.map(i=>esc(i.name)+(i.is_lead?' (lead)':'')).join(', ')}</p>`:''}${r.conflict_note?`<p class="warnline">${esc(r.conflict_note)}</p>`:''}<p>${link(r.source_url,'Source')}</p></article>`).join(''):'<p class="muted">No funding information found.</p>'}
  ${c.sec_filings.length?`<h3>SEC filings</h3>${c.sec_filings.map(f=>`<article class="funding-round"><p>${link(f.filing_url,'Form '+f.form_type+' · '+(f.filing_date||''))} · ${esc(f.issuer_name)} · sold ${f.total_amount_sold==null?'not stated':'$'+Number(f.total_amount_sold).toLocaleString()} of ${f.offering_amount_indefinite?'an indefinite amount':f.total_offering_amount==null?'not stated':'$'+Number(f.total_offering_amount).toLocaleString()}${f.investor_count!=null?' · '+esc(f.investor_count)+' investors':''}</p>${(f.review_flags||[]).map(x=>`<p class="small warnline">${esc(x)}</p>`).join('')}<p class="small muted">${esc(f.disclaimer)}</p></article>`).join('')}`:''}
  ${c.news.length?`<h3>News</h3><div class="news-list">${c.news.map(a=>`<article>${link(a.url,a.title)}<p class="muted small">${esc(a.publisher||'')} · ${esc(a.published_at?new Date(a.published_at+'Z').toLocaleDateString():'')} · ${a.event_types.map(esc).join(', ')||'no event tags'} · tone: ${esc(a.sentiment)}${(a.classification_evidence?.positive_terms||[]).length||(a.classification_evidence?.negative_terms||[]).length?' ('+[...(a.classification_evidence.positive_terms||[]),...(a.classification_evidence.negative_terms||[])].map(esc).join(', ')+')':''}</p></article>`).join('')}</div><p class="note">Tone describes the wording of a headline, not investment quality.</p>`:''}
  <h3>Sources and citations</h3><ul>${c.citations.map(x=>`<li>${esc(x.field)}: ${esc(x.value||'')} ${evBadge(x.evidence_status)}${x.is_estimate?' <span class="b b-plain">algorithmic estimate</span>':''} · ${link(x.source_url,x.publisher||'source')} <span class="small muted">retrieved ${esc(x.retrieved_at?.slice(0,10)||'')}</span></li>`).join('')||'<li>No citations recorded.</li>'}</ul>
  <details><summary>Data confidence breakdown (${esc(c.confidence.score)}/100)</summary><ul>${(c.confidence_breakdown?.components||[]).map(p=>`<li>${esc(p.component)}: ${p.points>0?'+':''}${esc(p.points)} — ${esc(p.explanation)}</li>`).join('')}</ul></details></section>`;
}
function viewStatus() {
  queueMicrotask(loadDiscoveryData);
  const s=DISC.status;
  const health={ok:'b-ok',failed:'b-conf',disabled:'b-plain',never_run:'b-unv'};
  return `<div class="pagehead"><div><span class="eyebrow">Automation</span><h1>Data status</h1><p>The data refreshes automatically every day using GitHub Actions. No server is involved.</p></div><a class="btn primary" href="${GITHUB_ACTIONS}" target="_blank" rel="noopener">Run discovery now</a></div>
  <p class="note">"Run discovery now" opens the update on GitHub. Choose <b>Run workflow</b>; the site republishes when it finishes (about 5–10 minutes). Only the repository owner can start it.</p>
  ${DISC.statusError?`<div class="panel" role="alert">${esc(DISC.statusError)}</div>`:''}
  ${s?`<section class="kpis"><div class="kpi"><span class="v">${esc(s.counts.companies)}</span><span class="l">Companies in database</span></div><div class="kpi"><span class="v">${esc(s.counts.articles)}</span><span class="l">Articles collected</span></div><div class="kpi"><span class="v">${esc(s.counts.sec_filings)}</span><span class="l">SEC Form D filings</span></div><div class="kpi"><span class="v small">${esc(new Date(s.generated_at+'Z').toLocaleString())}</span><span class="l">Last update</span></div></section>
  <section class="panel"><h2>Sources</h2><div class="tw"><table><thead><tr><th>Source</th><th>Status</th><th>Last success</th><th>Notes</th></tr></thead><tbody>${s.sources.map(x=>`<tr><td>${esc(x.name)}<div class="small muted">${esc(x.group)}</div></td><td><span class="b ${health[x.health]||'b-unv'}">${esc(x.health.replace('_',' '))}</span></td><td>${esc(x.last_success?new Date(x.last_success+'Z').toLocaleString():'—')}</td><td class="small">${esc(x.last_error||x.disabled_reason||x.access_notes||'')}</td></tr>`).join('')}</tbody></table></div></section>
  <section class="panel"><h2>Recent runs</h2><div class="tw"><table><thead><tr><th>Started</th><th>Source</th><th>Result</th><th class="r">New items</th><th class="r">New companies</th><th>Error</th></tr></thead><tbody>${s.recent_jobs.map(j=>`<tr><td>${esc(new Date(j.started_at+'Z').toLocaleString())}</td><td>${esc(j.source_key||j.job)}</td><td>${esc(j.status)}</td><td class="r">${esc(j.items_new)}</td><td class="r">${esc(j.startups_created)}</td><td class="small">${esc(j.error||'')}</td></tr>`).join('')}</tbody></table></div></section>`:''}`;
}
function viewTracking() {
  const rows=account.companies.filter(c=>!SCOUT.stageFilter||c.stage===SCOUT.stageFilter);
  return `<div class="pagehead"><div><h1>My startups</h1><p>Your personal list. It is saved in this browser; use Back up to keep a copy or move it to another device.</p></div><button class="btn primary" id="add-company">Add a startup</button></div>
  ${account.error?`<div class="panel" role="alert">${esc(account.error)}</div>`:''}
  ${SCOUT.saveError&&!SCOUT.form?`<p class="panel" role="alert">${esc(SCOUT.saveError)}</p>`:''}
  ${SCOUT.form?companyForm(SCOUT.form):''}
  <div class="controls"><label>Funding stage <select id="tracked-stage"><option value="">All stages</option>${options(STAGES,SCOUT.stageFilter)}</select></label><span>${rows.length} saved ${rows.length===1?'company':'companies'}</span><button class="btn" data-nav="discover">Discover more</button><button class="btn" id="backup-export" ${account.companies.length?'':'disabled'}>Back up (download)</button><label class="btn">Restore backup<input type="file" id="backup-import" accept="application/json,.json" hidden></label></div>
  ${SCOUT.importMsg?`<p class="note" role="status">${esc(SCOUT.importMsg)}</p>`:''}
  <div class="scout-grid">${rows.map(c=>`<article class="panel scout-card"><span class="eyebrow">${esc(c.industry)} · ${esc(c.stage)}</span><h2><button class="link" data-go="${esc(c.id)}">${esc(c.name)}</button></h2><p>${esc(c.location||'Location not supplied')}</p>${c.notes?`<p>${esc(c.notes)}</p>`:''}<p class="muted">${esc(c.source)} · Added ${esc(new Date(c.createdAt).toLocaleDateString())}</p><div class="row"><a href="${esc(c.website)}" target="_blank" rel="noopener noreferrer">Website</a><button class="btn" data-edit-company="${esc(c.id)}">Edit details</button><button class="btn" data-go="${esc(c.id)}">Research & score</button><button class="btn" data-remove-company="${esc(c.id)}">Remove</button></div></article>`).join('')||'<section class="panel empty">No saved startups yet. Add a company or track one from Discover.</section>'}</div>
  <p class="note">Saved companies, scores and pipeline edits stay in this browser and do not sync between devices or people. Clearing browser data removes them; back up first.</p>`;
}
function companyForm(c) {
  return `<form id="company-form" class="panel"><h2>${c.id?'Edit company':'Add a startup'}</h2><div class="fieldgrid"><label>Company name<input name="name" required maxlength="140" value="${esc(c.name)}"></label><label>Website<input name="website" type="url" placeholder="https://example.com" required maxlength="500" value="${esc(c.website)}"></label><label>Industry<input name="industry" maxlength="80" value="${esc(c.industry)}"></label><label>Location<input name="location" maxlength="140" value="${esc(c.location)}"></label><label>Funding stage<select name="stage">${options(STAGES,c.stage||'Not disclosed')}</select></label><label>Research notes<textarea name="notes" maxlength="2000">${esc(c.notes)}</textarea></label></div><div class="controls"><button class="btn primary">Save company</button><button type="button" class="btn" id="cancel-company">Cancel</button></div><p id="company-error" role="alert" class="warnline">${esc(SCOUT.saveError)}</p></form>`;
}
function persist(list) {
  try {VS.writeSaved(localStorage,list);}catch{throw new Error('This browser blocked saving (private mode or storage full).');}
  account.companies=list;
}
function saveCompany(c) {
  try {persist(VS.upsertCompany(account.companies,c));SCOUT.form=null;SCOUT.saveError='';location.hash='tracking';location.reload();}
  catch(e){SCOUT.saveError=e.message;const error=document.getElementById('company-error');if(error)error.textContent=e.message;else render();}
}
document.addEventListener('submit',e=>{
  if(e.target.id==='company-form'){e.preventDefault();saveCompany({...SCOUT.form,...Object.fromEntries(new FormData(e.target))});}
});
document.addEventListener('change',e=>{
  if(e.target.id==='tracked-stage'){SCOUT.stageFilter=e.target.value;render();}
  if(e.target.closest?.('#disc-filters')){const f=Object.fromEntries(new FormData(e.target.closest('#disc-filters')));Object.assign(DISC.f,f);DISC.limit=60;render();}
  if(e.target.id==='backup-import'&&e.target.files[0]){e.target.files[0].text().then(t=>{const r=VS.importBackup(account.companies,JSON.parse(t));persist(r.list);SCOUT.importMsg=`Restored ${r.added} compan${r.added===1?'y':'ies'}${r.skipped?`, skipped ${r.skipped} (already saved or invalid)`:''}. Reloading…`;render();setTimeout(()=>location.reload(),900);}).catch(err=>{SCOUT.importMsg='Could not restore: '+(err.message||'invalid file');render();});}
});
document.addEventListener('input',e=>{if(e.target.name==='q'&&e.target.closest('#disc-filters')){DISC.f.q=e.target.value;DISC.limit=60;clearTimeout(DISC.t);DISC.t=setTimeout(()=>{const pos=e.target.selectionStart;render();const i=document.querySelector('#disc-filters input[name=q]');if(i){i.focus();i.setSelectionRange(pos,pos);}},250);}});
document.addEventListener('click',e=>{
  const t=e.target.closest('button');if(!t)return;
  if(t.id==='add-company'){SCOUT.form={};SCOUT.saveError='';render();}
  if(t.id==='cancel-company'){SCOUT.form=null;SCOUT.saveError='';render();}
  if(t.dataset.editCompany){SCOUT.form=account.companies.find(c=>c.id===t.dataset.editCompany);SCOUT.saveError='';render();scrollTo(0,0);}
  if(t.dataset.removeCompany){const c=account.companies.find(x=>x.id===t.dataset.removeCompany);if(c&&confirm('Remove '+c.name+' from your list?')){persist(VS.removeCompany(account.companies,c.id));location.hash='tracking';location.reload();}}
  if(t.id==='backup-export'){const blob=new Blob([JSON.stringify({app:'VentureScout',exportedAt:new Date().toISOString(),companies:account.companies},null,1)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='venturescout-backup-'+new Date().toISOString().slice(0,10)+'.json';a.click();URL.revokeObjectURL(a.href);}
  if(t.dataset.disc){DISC.selected=Number(t.dataset.disc);render();document.getElementById('disc-profile')?.scrollIntoView();}
  if(t.id==='disc-close'){DISC.selected=null;render();}
  if(t.dataset.discTrack){startTracking(DISC.data.companies.find(c=>c.id===Number(t.dataset.discTrack)));}
  if(t.id==='disc-more'){DISC.limit+=60;render();}
});

/* Browser agent tools use the same data and navigation as the visible UI. */
if (document.modelContext?.registerTool) {
  const lifecycle = new AbortController();
  addEventListener("pagehide", () => lifecycle.abort(), { once: true });
  const register = tool => {
    try { Promise.resolve(document.modelContext.registerTool(tool, { signal: lifecycle.signal })).catch(() => {}); }
    catch { /* The site remains usable when browser tools are unavailable. */ }
  };
  register({
    name: "search_startups", title: "Search startup research",
    description: "Read your saved companies, filtered by company name or sector.",
    inputSchema: { type: "object", properties: { query: { type: "string" } }, required: ["query"], additionalProperties: false },
    annotations: { readOnlyHint: true, untrustedContentHint: true },
    execute(input) {
      if (!input || typeof input.query !== "string") throw new Error("A text query is required.");
      const query = input.query.trim().toLowerCase();
      return STARTUPS.filter(s => (s.company_name + " " + s.sector).toLowerCase().includes(query))
        .map(s => ({ id: s.startup_id, company: s.company_name, sector: s.sector, stage: pipe(s.startup_id).pipeline_stage }));
    }
  });
  register({
    name: "open_startup_profile", title: "Open startup profile",
    description: "Navigate to a startup profile in the visible tracker without changing its records.",
    inputSchema: { type: "object", properties: { id: { type: "string" } }, required: ["id"], additionalProperties: false },
    annotations: { readOnlyHint: false, untrustedContentHint: false },
    execute(input) {
      if (!input || typeof input.id !== "string" || !Object.hasOwn(BYID, input.id)) throw new Error("Unknown startup ID.");
      go("profile", input.id);
      return { view: "profile", id: input.id, company: BYID[input.id].company_name };
    }
  });
}

/* boot */
const _render = render;
render = function () { _render(); if (route.view === "directory") renderDirResults(); };
route = parseHash();
render();
}

(async function load() {
  try {
    const response = await fetch("data/config.json");
    if (!response.ok) throw new Error("Snapshot unavailable");
    const config = await response.json();
    const data={settings:config.settings,startups:[],rounds:[],claims:[],pipeline:[],scores:[]};
    window.ventureAccount = {companies:[],error:''};
    try { window.ventureAccount.companies = window.VentureScout.loadSaved(localStorage); }
    catch { window.ventureAccount.error = 'This browser blocked access to saved data (private mode or storage disabled).'; }
    for(const c of window.ventureAccount.companies) {
      const s=Object.fromEntries(config.startupFields.map(k=>[k,'']));
      Object.assign(s,{startup_id:c.id,company_name:c.name,website:c.website,sector:c.industry,sub_sector:'',funding_stage:c.stage,hq_city:c.location,verification_confidence:'Low',fundraising_status:'Unknown',description:c.notes,record_version:'1',missing_fields:'Financials; funding rounds; verified evidence'});
      data.startups.push(s);
      const p=Object.fromEntries(config.pipelineFields.map(k=>[k,'']));
      Object.assign(p,{startup_id:c.id,pipeline_stage:'Sourced',dd_form_c_review:'Not started',dd_terms_verified:'Not started',dd_financials_reviewed:'Not started',dd_founder_references:'Not started',dd_customer_references:'Not started',dd_legal_cap_table:'Not started'});data.pipeline.push(p);
      data.scores.push({startup_id:c.id});
    }
    boot(data, { kind: "snapshot" });
  } catch {
    document.getElementById("modebadge").textContent = "Data unavailable";
    const message = document.createElement("p");
    message.className = "panel";
    message.textContent = "The research data could not be loaded. Reload this page to try again.";
    document.getElementById("app").replaceChildren(message);
  }
})();
