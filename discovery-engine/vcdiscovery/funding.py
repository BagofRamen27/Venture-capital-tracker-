"""Funding-round bookkeeping: deduplicate announcements, corroborate, and flag conflicts."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import RAISED_STATUSES, FundingRound, Investor, RoundInvestor, Startup, utcnow
from .text import normalize_company_name

SAME_EVENT_WINDOW_DAYS = 60
AMOUNT_TOLERANCE = 0.10  # amounts within 10% are treated as the same figure (rounding in headlines)

STATUS_RANK = {"regulatory_filing": 0, "confirmed": 1, "company_announced": 2, "reported": 3, "analyst_entered": 4,
               "target": 5, "rumor": 6}


def _amounts_agree(a: float | None, b: float | None) -> bool | None:
    if a is None or b is None:
        return None
    hi = max(a, b)
    return hi == 0 or abs(a - b) / hi <= AMOUNT_TOLERANCE


def get_or_create_investor(session: Session, name: str) -> Investor:
    norm = normalize_company_name(name)
    inv = session.scalar(select(Investor).where(Investor.normalized_name == norm))
    if not inv:
        inv = Investor(name=name, normalized_name=norm)
        session.add(inv)
        session.flush()
    return inv


def attach_investors(session: Session, rnd: FundingRound, investors: list[str], leads: list[str], source_url: str | None) -> None:
    existing = {ri.investor_id for ri in rnd.investors}
    for name in investors:
        inv = get_or_create_investor(session, name)
        if inv.id in existing:
            continue
        rnd.investors.append(RoundInvestor(investor_id=inv.id, is_lead=name in leads, source_url=source_url))
        existing.add(inv.id)


def record_round(
    session: Session,
    startup: Startup,
    *,
    round_type: str | None,
    amount: float | None,
    currency: str | None,
    amount_text: str | None,
    announced: date | None,
    evidence_status: str,
    publisher: str | None,
    source_url: str | None,
    article_id: int | None = None,
    sec_filing_id: int | None = None,
    investors: list[str] | None = None,
    leads: list[str] | None = None,
) -> tuple[FundingRound, str]:
    """Add a funding observation. Returns (round, outcome) where outcome is
    'new' | 'corroborated' | 'same_source' | 'conflict'."""
    announced = announced or utcnow().date()
    window_lo, window_hi = announced - timedelta(days=SAME_EVENT_WINDOW_DAYS), announced + timedelta(days=SAME_EVENT_WINDOW_DAYS)
    candidates = [
        r for r in startup.rounds
        if r.evidence_status != "regulatory_filing" and evidence_status != "regulatory_filing"
        and (r.announced_date is None or window_lo <= r.announced_date <= window_hi)
        and (r.round_type is None or round_type is None or r.round_type == round_type)
        and (r.currency is None or currency is None or r.currency == currency)
    ]
    for rnd in candidates:
        agree = _amounts_agree(rnd.amount, amount)
        if agree is False:
            continue
        publishers = list(rnd.publishers or [])
        unconfirmed = {"rumor", "target"}
        if rnd.evidence_status in unconfirmed and evidence_status in RAISED_STATUSES:
            # A rumour followed by a real report: earlier rumour outlets do not count as corroboration.
            rnd.notes = ((rnd.notes + "; ") if rnd.notes else "") + f"Earlier {rnd.evidence_status} from {', '.join(publishers) or 'unknown'}"
            publishers = []
        elif evidence_status in unconfirmed and rnd.evidence_status in RAISED_STATUSES:
            return rnd, "same_source"  # a rumour adds nothing to a reported round
        if publisher and publisher in publishers:
            outcome = "same_source"
            rnd.publishers = publishers
        else:
            if publisher:
                publishers.append(publisher)
            rnd.publishers = publishers
            outcome = "corroborated"
        rnd.round_type = rnd.round_type or round_type
        if rnd.amount is None and amount is not None:
            rnd.amount, rnd.currency, rnd.amount_text = amount, currency, amount_text
        rnd.evidence_status = _combine_status(rnd.evidence_status, evidence_status, len(publishers))
        attach_investors(session, rnd, investors or [], leads or [], source_url)
        return rnd, outcome

    rnd = FundingRound(
        startup_id=startup.id, round_type=round_type, amount=amount, currency=currency, amount_text=amount_text,
        announced_date=announced, evidence_status=evidence_status, source_url=source_url, article_id=article_id,
        sec_filing_id=sec_filing_id, publishers=[publisher] if publisher else [],
    )
    startup.rounds.append(rnd)
    session.flush()
    attach_investors(session, rnd, investors or [], leads or [], source_url)

    outcome = "new"
    if evidence_status in RAISED_STATUSES:
        for other in candidates:
            if other.evidence_status in RAISED_STATUSES and _amounts_agree(other.amount, amount) is False:
                note = (f"Conflicting amounts for the same {round_type or 'round'}: "
                        f"{other.amount_text or other.amount} ({', '.join(other.publishers or []) or 'source'}) vs "
                        f"{amount_text or amount} ({publisher or 'source'})")
                for r in (rnd, other):
                    r.conflict, r.conflict_note = True, note
                startup.add_flag("conflicting_funding")
                outcome = "conflict"
    return rnd, outcome


def _combine_status(current: str, new: str, independent_publishers: int) -> str:
    """Rumours and targets never become 'confirmed' by repetition alone."""
    raised = {current, new} & {"company_announced", "reported", "confirmed"}
    if raised:
        if "confirmed" in raised or independent_publishers >= 2:
            return "confirmed"
        return min(raised, key=lambda s: STATUS_RANK[s])
    return min((current, new), key=lambda s: STATUS_RANK.get(s, 99))


def refresh_funding_summary(startup: Startup) -> None:
    """Recompute total / latest funding from rounds. Rumours, targets and Form D offers are excluded
    from the total; Form D is shown separately on the filing itself."""
    raised = [r for r in startup.rounds if r.evidence_status in RAISED_STATUSES and r.amount is not None]
    currencies = {r.currency for r in raised}
    if raised and len(currencies) == 1:
        startup.total_funding_amount = sum(r.amount for r in raised)
        startup.total_funding_currency = currencies.pop()
        n_conf = sum(1 for r in raised if r.evidence_status == "confirmed")
        startup.total_funding_basis = (
            f"Sum of {len(raised)} publicly reported round(s) ({n_conf} corroborated). Excludes rumours, targets and "
            "Form D offering amounts. Not audited."
        )
    elif raised:
        startup.total_funding_amount, startup.total_funding_currency = None, None
        startup.total_funding_basis = "Rounds reported in different currencies; see individual rounds (no conversion applied)."
    else:
        startup.total_funding_amount = startup.total_funding_currency = None
        startup.total_funding_basis = "Not disclosed"

    dated = sorted(
        (r for r in startup.rounds if r.evidence_status in RAISED_STATUSES | {"regulatory_filing"}),
        key=lambda r: (r.announced_date or date.min, -STATUS_RANK.get(r.evidence_status, 9)),
    )
    if dated:
        latest = dated[-1]
        startup.latest_funding_amount = latest.amount
        startup.latest_funding_currency = latest.currency
        startup.latest_funding_date = latest.announced_date
        startup.latest_funding_status = latest.evidence_status
        if latest.round_type and latest.evidence_status != "regulatory_filing":
            startup.funding_stage = latest.round_type
    if not any(r.conflict for r in startup.rounds):
        startup.remove_flag("conflicting_funding")
