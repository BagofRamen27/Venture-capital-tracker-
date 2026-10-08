"""Transparent startup investment scoring (0-100).

Principles:
* Each factor returns a score with the evidence behind it, or `None` ("unscorable") with the
  reason. Unscorable factors are left out of the average; they are never filled with guesses.
* The total is the weighted average of the scorable factors. `coverage` shows how much of
  the total weight could be scored. Low coverage gives the rating "Insufficient evidence".
* Media volume is not rewarded: events are counted once per type per week, however many
  articles repeat them.
* Pre-revenue companies are not penalised: missing revenue makes financial evidence
  unscorable rather than zero.
* Analysts can override any factor. Overrides are kept across refreshes and shown as such.

These scores are preliminary research indicators, not investment recommendations.
"""
from __future__ import annotations

import math
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .models import (
    RAISED_STATUSES,
    AppSetting,
    ArticleMention,
    DiscoverySignal,
    FundingRound,
    InvestmentScore,
    NewsArticle,
    ScoreOverride,
    SecFiling,
    Startup,
    utcnow,
)

FACTORS = {
    "market_opportunity": "Market Opportunity",
    "business_traction": "Business Traction",
    "funding_validation": "Funding and Investor Validation",
    "product_differentiation": "Product Differentiation",
    "team_evidence": "Team and Founder Evidence",
    "growth_momentum": "Growth Momentum",
    "financial_evidence": "Financial Evidence",
}
METHODS = {
    "market_opportunity": "Proxy: number of distinct companies in the same industry with reported funding in the last 180 days, "
                          "relative to the busiest industry in the database. Measures investor activity, not market size. "
                          "Needs at least 20 funding events in the database.",
    "business_traction": "Rules on classified news: product launch 35, customer adoption +30, partnership +20, "
                         "disclosed revenue +15 (max 100). Unscorable when no traction evidence is public.",
    "funding_validation": "Best funding evidence: corroborated round 60, single-source report 45, Form D with securities sold 40, "
                          "rumour/target only 15; +10 if a lead investor is named; +5 per other named investor (max +25).",
    "product_differentiation": "Requires analyst judgement (IP, technical depth, switching costs). Unscorable until an analyst adds a score.",
    "team_evidence": "Founders publicly named 40 (or executives listed on Form D 30); accelerator acceptance +20 "
                     "(e.g. Y Combinator). Capped at 70 automatically; founder experience needs analyst review.",
    "growth_momentum": "Distinct activity events (one per type per week) in the last 90 days: 20 each, plus up to 30 for community "
                       "attention on Hacker News (log scale). 10 if activity exists but none in the last 90 days.",
    "financial_evidence": "Disclosed revenue 70 (+15 if corroborated); Form D with at least half of the offering sold 50, "
                          "otherwise 30. Unscorable when nothing is disclosed (does not penalise pre-revenue companies).",
}


def load_config(session: Session, file_config: dict) -> dict:
    config = {**file_config}
    stored = session.get(AppSetting, "scoring_weights")
    if stored:
        config["weights"] = stored.value
    return config


def validate_weights(weights: dict) -> dict:
    unknown = set(weights) - set(FACTORS)
    if unknown:
        raise ValueError(f"Unknown factor(s): {', '.join(sorted(unknown))}")
    clean = {k: float(weights.get(k, 0)) for k in FACTORS}
    if any(v < 0 for v in clean.values()):
        raise ValueError("Weights cannot be negative")
    if abs(sum(clean.values()) - 100) > 0.01:
        raise ValueError(f"Weights must add up to 100 (currently {sum(clean.values()):g})")
    return clean


def save_weights(session: Session, weights: dict) -> dict:
    clean = validate_weights(weights)
    row = session.get(AppSetting, "scoring_weights")
    if row:
        row.value = clean
    else:
        session.add(AppSetting(key="scoring_weights", value=clean))
    return clean


class Context:
    """Everything the factor rules need, loaded once per company."""

    def __init__(self, session: Session, startup: Startup, momentum_days: int):
        self.s = startup
        self.now = utcnow()
        self.rounds = list(startup.rounds)
        self.signals = list(session.scalars(select(DiscoverySignal).where(DiscoverySignal.startup_id == startup.id)))
        self.articles = list(session.scalars(
            select(NewsArticle).join(ArticleMention, ArticleMention.article_id == NewsArticle.id)
            .where(ArticleMention.startup_id == startup.id, NewsArticle.duplicate_of_id.is_(None))))
        self.filings = list(session.scalars(select(SecFiling).where(
            SecFiling.startup_id == startup.id, SecFiling.match_status.in_(["auto_matched", "created", "confirmed"]))))
        self.momentum_days = momentum_days
        self.session = session


def _ev(text: str, url: str | None = None) -> dict:
    return {"text": text, "url": url}


def factor_market(ctx: Context):
    s = ctx.s
    if not s.industry:
        return None, [], "Industry unknown"
    since = (ctx.now - timedelta(days=180)).date()
    rows = ctx.session.execute(
        select(Startup.industry, func.count(func.distinct(FundingRound.startup_id)))
        .join(FundingRound, FundingRound.startup_id == Startup.id)
        .where(FundingRound.evidence_status.in_(RAISED_STATUSES), FundingRound.announced_date >= since,
               Startup.industry.is_not(None), Startup.is_demo == s.is_demo)
        .group_by(Startup.industry)).all()
    total_events = sum(c for _, c in rows)
    if total_events < 20:
        return None, [], f"Only {total_events} recent funding events in the database (need 20 for a sector comparison)"
    counts = dict(rows)
    mine, top = counts.get(s.industry, 0), max(counts.values())
    score = 30 + 70 * mine / top
    return score, [_ev(f"{mine} companies in '{s.industry}' reported funding in the last 180 days (busiest sector: {top})")], None


def factor_traction(ctx: Context):
    points, evidence = 0.0, []
    for event, pts in (("product_launch", 35), ("customer_adoption", 30), ("partnership", 20)):
        hits = [a for a in ctx.articles if event in (a.event_types or [])]
        if hits:
            points += pts
            evidence.append(_ev(f"{event.replace('_', ' ').title()}: {hits[0].title}", hits[0].url))
    if ctx.s.revenue_amount:
        points += 15
        evidence.append(_ev(f"Revenue disclosed ({ctx.s.revenue_basis or 'see citation'})"))
    if not evidence:
        return None, [], "No public traction evidence (common for very early companies)"
    return min(points, 100), evidence, None


def factor_funding(ctx: Context):
    evidence, base = [], None
    raised = [r for r in ctx.rounds if r.evidence_status in RAISED_STATUSES]
    if any(r.evidence_status == "confirmed" for r in raised):
        base = 60
        r = next(r for r in raised if r.evidence_status == "confirmed")
        evidence.append(_ev(f"Corroborated {r.round_type or 'funding'} {r.amount_text or ''} ({', '.join(r.publishers or [])})".strip(), r.source_url))
    elif raised:
        base, r = 45, raised[-1]
        evidence.append(_ev(f"{r.evidence_status.replace('_', ' ')}: {r.round_type or 'funding'} {r.amount_text or ''}".strip(), r.source_url))
    sold = [f for f in ctx.filings if (f.total_amount_sold or 0) > 0]
    if sold:
        base = max(base or 0, 40)
        f = sold[0]
        evidence.append(_ev(f"Form D: ${f.total_amount_sold:,.0f} sold (offering notice, not a priced round)", f.filing_url))
    if base is None:
        unconfirmed = [r for r in ctx.rounds if r.evidence_status in ("rumor", "target")]
        if unconfirmed:
            r = unconfirmed[-1]
            return 15, [_ev(f"Only {r.evidence_status} funding information: {r.amount_text or ''}", r.source_url)], None
        return None, [], "No funding information"
    investors = {(ri.investor.name, ri.is_lead) for r in raised for ri in r.investors}
    leads = sorted({n for n, lead in investors if lead})
    others = sorted({n for n, lead in investors if not lead} - set(leads))
    bonus = (10 if leads else 0) + min(25, 5 * len(others))
    if leads:
        evidence.append(_ev(f"Lead investor(s) named: {', '.join(leads)}"))
    if others:
        evidence.append(_ev(f"Other named investors: {', '.join(others)}"))
    return min(100, base + bonus), evidence, None


def factor_product(ctx: Context):
    return None, [], "Requires analyst judgement; add a manual score with your reasoning"


def factor_team(ctx: Context):
    score, evidence = 0, []
    if ctx.s.founders:
        score, evidence = 40, [_ev(f"Founders named publicly: {ctx.s.founders}")]
    elif ctx.s.key_people:
        score, evidence = 30, [_ev(f"Executives listed on SEC filing: {ctx.s.key_people}")]
    accel = [sig for sig in ctx.signals if sig.signal_type == "accelerator"]
    if accel:
        score += 20
        evidence.append(_ev(accel[0].detail or "Accelerator participation", accel[0].source_url))
    if not evidence:
        return None, [], "No founder or team information"
    return min(score, 70), evidence, None


def factor_momentum(ctx: Context):
    if not ctx.signals:
        return None, [], "No activity signals recorded"
    recent_cut = ctx.now - timedelta(days=ctx.momentum_days)
    recent = {(sig.signal_type, (sig.observed_at or sig.detected_at).isocalendar()[:2])
              for sig in ctx.signals if (sig.observed_at or sig.detected_at) >= recent_cut}
    points = max((a.community_metrics or {}).get("points", 0) for a in ctx.articles) if ctx.articles else 0
    hn = min(30.0, 10 * math.log10(points + 1)) if points else 0.0
    if not recent:
        return 10, [_ev(f"No new activity in the last {ctx.momentum_days} days")], None
    types = sorted({t for t, _ in recent})
    evidence = [_ev(f"{len(recent)} distinct event-weeks in last {ctx.momentum_days} days ({', '.join(types)})")]
    if hn:
        evidence.append(_ev(f"Hacker News attention: {points} points"))
    return min(100.0, 20 * len(recent) + hn), evidence, None


def factor_financial(ctx: Context):
    s = ctx.s
    if s.revenue_amount:
        corroborated = s.revenue_basis and "corroborated" in s.revenue_basis.lower()
        return (85 if corroborated else 70), [_ev(f"Revenue disclosed: {s.revenue_amount:,.0f} ({s.revenue_basis or 'basis not stated'})")], None
    for f in ctx.filings:
        if f.total_offering_amount and f.total_amount_sold:
            ratio = f.total_amount_sold / f.total_offering_amount
            return (50 if ratio >= 0.5 else 30), [_ev(
                f"Form D: {ratio:.0%} of ${f.total_offering_amount:,.0f} offering sold", f.filing_url)], None
    return None, [], "No revenue or offering data disclosed (not penalised)"


RULES = {
    "market_opportunity": factor_market,
    "business_traction": factor_traction,
    "funding_validation": factor_funding,
    "product_differentiation": factor_product,
    "team_evidence": factor_team,
    "growth_momentum": factor_momentum,
    "financial_evidence": factor_financial,
}


def score_startup(session: Session, startup: Startup, config: dict) -> InvestmentScore:
    weights = validate_weights(config["weights"])
    thresholds = config["thresholds"]
    ctx = Context(session, startup, config.get("momentum_window_days", 90))
    overrides = {o.factor: o for o in session.scalars(select(ScoreOverride).where(ScoreOverride.startup_id == startup.id))}

    factors, missing = [], []
    weighted, weight_scored = 0.0, 0.0
    for key, label in FACTORS.items():
        auto, evidence, reason = RULES[key](ctx)
        entry = {"factor": key, "label": label, "weight": weights[key], "method": METHODS[key],
                 "auto_score": None if auto is None else round(auto, 1), "evidence": evidence,
                 "unscorable_reason": reason, "override": None}
        final = auto
        if key in overrides:
            o = overrides[key]
            final = o.score
            entry["override"] = {"score": o.score, "note": o.note, "analyst": o.analyst, "at": o.created_at.isoformat()}
        entry["score"] = None if final is None else round(final, 1)
        entry["status"] = "analyst_override" if key in overrides else ("scored" if final is not None else "unscorable")
        if final is None:
            missing.append({"factor": key, "label": label, "reason": reason})
        elif weights[key] > 0:
            weighted += final * weights[key]
            weight_scored += weights[key]
        factors.append(entry)

    coverage = weight_scored / 100.0
    total = round(weighted / weight_scored, 1) if weight_scored else None
    if total is None:
        rating = "Not scored"
    elif coverage < thresholds["min_coverage"]:
        rating = "Insufficient evidence"
    elif total >= thresholds["strong"]:
        rating = "Strong research candidate"
    elif total >= thresholds["promising"]:
        rating = "Promising"
    elif total >= thresholds["watchlist"]:
        rating = "Watchlist"
    else:
        rating = "Below threshold"

    session.execute(update(InvestmentScore).where(InvestmentScore.startup_id == startup.id).values(is_current=False))
    result = InvestmentScore(
        startup_id=startup.id, total_score=total, rating=rating, coverage=round(coverage, 3), weights=weights,
        factors=factors, missing=missing, thesis=build_thesis(ctx, factors), risks=build_risks(ctx, missing),
        model_version=str(config.get("model_version", "1.0")), is_current=True,
    )
    session.add(result)
    return result


def _money(amount, currency) -> str:
    if amount is None:
        return "an undisclosed amount"
    sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency or "", (currency or "") + " ")
    return f"{sym}{amount / 1e6:,.1f}M" if amount >= 1e6 else f"{sym}{amount:,.0f}"


def build_thesis(ctx: Context, factors: list[dict]) -> str:
    s = ctx.s
    where = ", ".join(p for p in (s.hq_city, s.hq_state, s.hq_country) if p)
    parts = [f"{s.name} is {('a ' + s.industry) if s.industry else 'an unclassified'} company" + (f" based in {where}" if where else "") + "."]
    if s.description:
        parts.append(s.description.rstrip(".") + ".")
    raised = [r for r in ctx.rounds if r.evidence_status in RAISED_STATUSES]
    if raised:
        r = max(raised, key=lambda x: x.announced_date or utcnow().date())
        parts.append(f"Most recent reported funding: {r.round_type or 'round'} of {_money(r.amount, r.currency)} "
                     f"({r.evidence_status.replace('_', ' ')}).")
    elif ctx.filings:
        f = ctx.filings[0]
        parts.append(f"An SEC Form D shows an exempt offering with {_money(f.total_amount_sold, 'USD')} sold; "
                     "this does not establish a priced venture round.")
    strong = [f["label"] for f in factors if f["score"] is not None and f["score"] >= 60]
    if strong:
        parts.append("Relative strengths in the available evidence: " + ", ".join(strong) + ".")
    parts.append("Preliminary, evidence-based summary; not an investment recommendation.")
    return " ".join(parts)


def build_risks(ctx: Context, missing: list[dict]) -> list[str]:
    s, risks = ctx.s, []
    if any(r.conflict for r in ctx.rounds):
        risks.append("Conflicting funding figures across sources")
    if ctx.rounds and all(r.evidence_status in ("rumor", "target") for r in ctx.rounds):
        risks.append("Funding is only rumoured or a target, not confirmed")
    if ctx.filings and not any(r.evidence_status in RAISED_STATUSES for r in ctx.rounds):
        risks.append("Funding evidence relies on a Form D notice, which does not confirm investors or valuation")
    neg = [a for a in ctx.articles if a.sentiment == "negative" or {"layoffs", "legal", "shutdown"} & set(a.event_types or [])]
    for a in neg[:3]:
        risks.append(f"Negative development reported: {a.title}")
    if not s.domain:
        risks.append("No verified company website")
    if "stale" in (s.flags or []):
        risks.append("Information is stale; re-verify before relying on it")
    if "possible_duplicate" in (s.flags or []) or "name_collision" in (s.flags or []):
        risks.append("Identity not fully resolved (possible duplicate or similarly named company)")
    if len(missing) >= 4:
        risks.append(f"{len(missing)} of {len(FACTORS)} factors could not be scored from public evidence")
    return risks


def refresh_scores(session: Session, config: dict, startup_ids: list[int] | None = None) -> int:
    query = select(Startup).where(Startup.review_status != "Archived")
    if startup_ids:
        query = select(Startup).where(Startup.id.in_(startup_ids))
    n = 0
    for s in session.scalars(query).all():
        score_startup(session, s, config)
        n += 1
    return n
