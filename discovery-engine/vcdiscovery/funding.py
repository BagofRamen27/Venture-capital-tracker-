"""Funding-round bookkeeping: deduplicate announcements, corroborate, and flag conflicts."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import RAISED_STATUSES, FundingRound, Investor, NewsArticle, RoundInvestor, Startup
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


def _publisher_key(value: str | None) -> str:
    """Normalize publisher labels so casing/spacing differences do not fake independence."""
    return " ".join((value or "").casefold().split())


def _append_note(rnd: FundingRound, note: str) -> None:
    if not note:
        return
    existing = [part.strip() for part in (rnd.notes or "").split(" | ") if part.strip()]
    if note not in existing:
        existing.append(note)
        rnd.notes = " | ".join(existing)


def _set_resolution(rnd: FundingRound, state: str, reason: str, candidate_ids: list[int] | None = None) -> None:
    extra = dict(rnd.extra or {})
    extra["funding_resolution"] = {
        "state": state, "reason": reason,
        "candidate_round_ids": sorted(set(candidate_ids or [])), "rule_version": 1,
    }
    rnd.extra = extra


def _record_observation(
    rnd: FundingRound, *, round_type: str | None, amount: float | None, currency: str | None,
    amount_text: str | None, announced: date | None, announced_date_basis: str | None,
    source_published_at: str | None, evidence_status: str, publisher: str | None,
    source_url: str | None, article_id: int | None, sec_filing_id: int | None,
    outcome: str, reason: str, independent_source: bool,
) -> None:
    """Keep every source observation on the round without introducing a new table."""
    extra = dict(rnd.extra or {})
    extra.setdefault("announced_date_basis", announced_date_basis or ("unknown" if announced is None else "unspecified"))
    observations = list(extra.get("funding_observations") or [])
    if article_id is not None:
        identity = ("article_id", article_id)
    elif source_url:
        identity = ("source_url", source_url)
    elif sec_filing_id is not None:
        identity = ("sec_filing_id", sec_filing_id)
    else:
        identity = None
    if identity is not None and any(o.get(identity[0]) == identity[1] for o in observations):
        return
    observations.append({
        "article_id": article_id, "sec_filing_id": sec_filing_id, "source_url": source_url,
        "publisher": publisher, "round_type": round_type, "amount": amount, "currency": currency,
        "amount_text": amount_text, "announced_date": announced.isoformat() if announced else None,
        "announced_date_basis": announced_date_basis or ("unknown" if announced is None else "unspecified"),
        "source_published_at": source_published_at, "evidence_status": evidence_status,
        "outcome": outcome, "match_reason": reason, "independent_source": bool(independent_source),
    })
    extra["funding_observations"] = observations
    rnd.extra = extra


def record_round(
    session: Session, startup: Startup, *, round_type: str | None, amount: float | None,
    currency: str | None, amount_text: str | None, announced: date | None, evidence_status: str,
    publisher: str | None, source_url: str | None, article_id: int | None = None,
    sec_filing_id: int | None = None, investors: list[str] | None = None, leads: list[str] | None = None,
    announced_date_basis: str | None = None, source_published_at: str | None = None,
) -> tuple[FundingRound, str]:
    """Record an observation conservatively and explain every match decision.

    Returns (round, outcome): 'new' | 'corroborated' | 'same_source' | 'conflict'.
    Underdetermined observations remain separate and are flagged for review.
    """
    incoming_article = session.get(NewsArticle, article_id) if article_id is not None else None
    syndicated_copy = bool(incoming_article and incoming_article.duplicate_of_id is not None)

    # Repeated observations must not create another round or increase corroboration.
    for existing in startup.rounds:
        observations = (existing.extra or {}).get("funding_observations") or []
        if article_id is not None and (
            existing.article_id == article_id
            or any(o.get("article_id") == article_id for o in observations)
        ):
            return existing, "same_source"
        if source_url and (
            existing.source_url == source_url
            or any(o.get("source_url") == source_url for o in observations)
        ):
            return existing, "same_source"

    compatible = [
        r for r in startup.rounds
        if r.evidence_status != "regulatory_filing" and evidence_status != "regulatory_filing"
        and (r.round_type is None or round_type is None or r.round_type == round_type)
        and (r.currency is None or currency is None or r.currency == currency)
    ]
    if announced is not None:
        window_lo = announced - timedelta(days=SAME_EVENT_WINDOW_DAYS)
        window_hi = announced + timedelta(days=SAME_EVENT_WINDOW_DAYS)
        dated_candidates = [
            r for r in compatible if r.announced_date is not None
            and window_lo <= r.announced_date <= window_hi
        ]
    else:
        # Unknown event dates are not replaced by retrieval/current dates.
        dated_candidates = []

    def fully_comparable(rnd: FundingRound) -> bool:
        # Unknown round labels may be tolerated as weaker evidence, but two known
        # labels must agree. Amount comparison requires a known shared currency.
        return (
            announced is not None and rnd.announced_date is not None
            and (rnd.round_type is None or round_type is None or rnd.round_type == round_type)
            and rnd.currency is not None and currency is not None and rnd.currency == currency
            and rnd.evidence_status != "regulatory_filing" and evidence_status != "regulatory_filing"
        )

    # A mismatch is a conflict only when date, round type and currency are comparable.
    conflicts = [
        r for r in dated_candidates
        if fully_comparable(r) and r.round_type is not None and round_type is not None
        and r.round_type == round_type and _amounts_agree(r.amount, amount) is False
        and r.evidence_status in RAISED_STATUSES and evidence_status in RAISED_STATUSES
    ]
    strong_matches = [
        r for r in dated_candidates
        if fully_comparable(r) and _amounts_agree(r.amount, amount) is True
    ]

    if conflicts:
        candidate_ids = [r.id for r in conflicts if r.id is not None]
        rnd = FundingRound(
            startup_id=startup.id, round_type=round_type, amount=amount, currency=currency, amount_text=amount_text,
            announced_date=announced, evidence_status=evidence_status, source_url=source_url, article_id=article_id,
            sec_filing_id=sec_filing_id, publishers=[publisher] if publisher and not syndicated_copy else [],
            conflict=True,
        )
        startup.rounds.append(rnd)
        session.flush()
        note = (
            f"Conflicting amounts for the same {round_type or 'round'} within {SAME_EVENT_WINDOW_DAYS} days: "
            f"{amount_text or amount} ({publisher or 'source'}) conflicts with round(s) "
            f"{', '.join(str(i) for i in candidate_ids)}"
        )
        rnd.conflict_note = note
        _set_resolution(rnd, "conflict", note, candidate_ids)
        for other in conflicts:
            other.conflict, other.conflict_note = True, note
            _set_resolution(other, "conflict", note, [rnd.id])
        startup.add_flag("conflicting_funding")
        _record_observation(
            rnd, round_type=round_type, amount=amount, currency=currency, amount_text=amount_text,
            announced=announced, announced_date_basis=announced_date_basis,
            source_published_at=source_published_at, evidence_status=evidence_status, publisher=publisher,
            source_url=source_url, article_id=article_id, sec_filing_id=sec_filing_id,
            outcome="conflict", reason=note, independent_source=bool(publisher and not syndicated_copy),
        )
        attach_investors(session, rnd, investors or [], leads or [], source_url)
        return rnd, "conflict"

    # Unknown dates or comparison fields indicate possible duplicates, never safe matches.
    uncertain_candidates = []
    for candidate in compatible:
        if announced is not None and candidate.announced_date is not None:
            if not window_lo <= candidate.announced_date <= window_hi:
                continue
            date_unknown = False
        else:
            date_unknown = True
        fields_missing = (
            candidate.currency is None or currency is None
            or candidate.amount is None or amount is None
        )
        if not date_unknown and not fields_missing:
            continue
        amount_consistent = True
        if (candidate.amount is not None and amount is not None
                and candidate.currency is not None and currency is not None
                and candidate.currency == currency):
            amount_consistent = _amounts_agree(candidate.amount, amount) is not False
        if amount_consistent:
            uncertain_candidates.append(candidate)

    plausible = list(strong_matches)
    seen_ids = {r.id for r in plausible}
    for candidate in uncertain_candidates:
        if candidate.id not in seen_ids:
            plausible.append(candidate)
            seen_ids.add(candidate.id)
    ambiguous = len(strong_matches) > 1 or bool(uncertain_candidates) or (
        announced is None and bool(plausible)
    )

    if len(strong_matches) == 1 and not ambiguous:
        rnd = strong_matches[0]
        publishers = list(rnd.publishers or [])
        existing_keys = {_publisher_key(p) for p in publishers if _publisher_key(p)}
        incoming_key = _publisher_key(publisher)
        independent_source = bool(incoming_key and incoming_key not in existing_keys and not syndicated_copy)

        unconfirmed = {"rumor", "target"}
        if rnd.evidence_status in unconfirmed and evidence_status in RAISED_STATUSES:
            earlier = ", ".join(publishers) or "unknown"
            _append_note(rnd, f"Earlier {rnd.evidence_status} from {earlier}")
            publishers = []
            existing_keys = set()
        elif evidence_status in unconfirmed and rnd.evidence_status in RAISED_STATUSES:
            reason = "Rumour/target retained as source evidence but not used to confirm an already reported round"
            _set_resolution(rnd, "matched", reason, [rnd.id])
            _record_observation(
                rnd, round_type=round_type, amount=amount, currency=currency, amount_text=amount_text,
                announced=announced, announced_date_basis=announced_date_basis,
                source_published_at=source_published_at, evidence_status=evidence_status, publisher=publisher,
                source_url=source_url, article_id=article_id, sec_filing_id=sec_filing_id,
                outcome="same_source", reason=reason, independent_source=False,
            )
            return rnd, "same_source"

        if incoming_key and incoming_key not in existing_keys and not syndicated_copy:
            publishers.append(publisher)
        rnd.publishers = publishers
        outcome = "corroborated" if independent_source else "same_source"
        reason = (
            f"Unique candidate with no known round-type contradiction and matching currency; event dates are within "
            f"{SAME_EVENT_WINDOW_DAYS} days and amounts agree within {AMOUNT_TOLERANCE:.0%}"
        )
        if syndicated_copy:
            reason += "; syndicated copy excluded from independent corroboration"
        independent_count = len({_publisher_key(p) for p in publishers if _publisher_key(p)})
        rnd.evidence_status = _combine_status(rnd.evidence_status, evidence_status, independent_count)
        attach_investors(session, rnd, investors or [], leads or [], source_url)
        _set_resolution(rnd, "matched", reason, [rnd.id])
        _record_observation(
            rnd, round_type=round_type, amount=amount, currency=currency, amount_text=amount_text,
            announced=announced, announced_date_basis=announced_date_basis,
            source_published_at=source_published_at, evidence_status=evidence_status, publisher=publisher,
            source_url=source_url, article_id=article_id, sec_filing_id=sec_filing_id,
            outcome=outcome, reason=reason, independent_source=independent_source,
        )
        return rnd, outcome

    rnd = FundingRound(
        startup_id=startup.id, round_type=round_type, amount=amount, currency=currency, amount_text=amount_text,
        announced_date=announced, evidence_status=evidence_status, source_url=source_url, article_id=article_id,
        sec_filing_id=sec_filing_id, publishers=[publisher] if publisher and not syndicated_copy else [],
    )
    startup.rounds.append(rnd)
    session.flush()
    attach_investors(session, rnd, investors or [], leads or [], source_url)

    if ambiguous:
        candidate_ids = [r.id for r in plausible if r.id is not None]
        reason = (
            "Potential duplicate not auto-merged because the event date or comparison fields are missing, "
            "or more than one candidate fits; compare the linked source observations before resolving"
        )
        _append_note(rnd, reason)
        for other in plausible:
            _append_note(other, f"Possible related funding observation in round {rnd.id}; review before merging")
            _set_resolution(other, "needs_review", reason, [rnd.id])
        startup.add_flag("possible_duplicate")
        _set_resolution(rnd, "needs_review", reason, candidate_ids)
    else:
        reason = "No unique candidate met the required date, round-type, currency and amount match rules"
        _set_resolution(rnd, "distinct", reason)

    _record_observation(
        rnd, round_type=round_type, amount=amount, currency=currency, amount_text=amount_text,
        announced=announced, announced_date_basis=announced_date_basis,
        source_published_at=source_published_at, evidence_status=evidence_status, publisher=publisher,
        source_url=source_url, article_id=article_id, sec_filing_id=sec_filing_id,
        outcome="new", reason=reason, independent_source=bool(publisher and not syndicated_copy),
    )
    return rnd, "new"

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
