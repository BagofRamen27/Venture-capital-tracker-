"""Wikidata enrichment: fill missing company facts from Wikidata (https://www.wikidata.org).

Wikidata's data is public domain (CC0) and is read through the official MediaWiki API
(`wbsearchentities` + `wbgetentities`), one request at a time, identified by our User-Agent
and with `maxlag` set, as Wikimedia's API etiquette asks.

Matching is deliberately conservative:
* If we know the company's website, a Wikidata item matches only when its official website
  (P856) has the same domain.
* Without a website, an item matches only when it is the ONLY company-like result whose label
  or alias equals the company's normalised name.
Anything else is left alone. Existing values are never overwritten; every filled field gets a
citation labelled "community_sourced" that links to the Wikidata item.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .confidence import compute_confidence
from .db import session_scope
from .http import PoliteClient, SourceUnavailable
from .models import JobRun, Startup, utcnow
from .pipeline import acquire_lock, add_citation, release_lock
from .text import company_domain, normalize_company_name

API = "https://www.wikidata.org/w/api.php"
ENTITY_URL = "https://www.wikidata.org/wiki/{}"
SOURCE_KEY = "wikidata"
RECHECK_AFTER = timedelta(days=30)

# Wikidata classes that describe businesses ("instance of", P31).
COMPANY_CLASSES = {"Q4830453", "Q783794", "Q6881511", "Q891723", "Q1589009", "Q167037", "Q21980538", "Q18388277"}
COMPANY_WORDS = re.compile(
    r"\b(company|startup|start-up|corporation|business|enterprise|firm|manufacturer|developer|provider|platform|"
    r"software|fintech|biotech|bank|brand|unicorn)\b", re.IGNORECASE)

PROPS = {"website": "P856", "inception": "P571", "founders": "P112", "headquarters": "P159",
         "country": "P17", "industry": "P452", "instance_of": "P31"}


@dataclass
class WikidataFacts:
    qid: str
    label: str
    description: str | None
    website: str | None = None
    founded_year: int | None = None
    founder_ids: list[str] = field(default_factory=list)
    hq_ids: list[str] = field(default_factory=list)
    country_ids: list[str] = field(default_factory=list)
    industry_ids: list[str] = field(default_factory=list)
    instance_of: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


def _api(client: PoliteClient, **params) -> dict:
    resp = client.get(API, params={**params, "format": "json", "maxlag": "5"})
    data = resp.json()
    if "error" in data:
        raise SourceUnavailable(f"Wikidata API error: {data['error'].get('code')} {data['error'].get('info', '')}".strip())
    return data


def _claims(entity: dict, prop: str) -> list[dict]:
    """Usable statement values, preferred-rank first, deprecated ones dropped."""
    statements = [s for s in entity.get("claims", {}).get(prop, []) if s.get("rank") != "deprecated"]
    statements.sort(key=lambda s: s.get("rank") != "preferred")
    return [s["mainsnak"]["datavalue"]["value"] for s in statements
            if s.get("mainsnak", {}).get("snaktype") == "value" and "datavalue" in s["mainsnak"]]


def parse_entity(entity: dict) -> WikidataFacts:
    ids = lambda prop: [v["id"] for v in _claims(entity, PROPS[prop]) if isinstance(v, dict) and "id" in v]
    websites = [v for v in _claims(entity, PROPS["website"]) if isinstance(v, str)]
    year = None
    for v in _claims(entity, PROPS["inception"]):
        m = re.match(r"[+]?(\d{4})-", v.get("time", "")) if isinstance(v, dict) else None
        if m and v.get("precision", 0) >= 9:  # 9 = year precision or finer
            year = int(m.group(1))
            break
    return WikidataFacts(
        qid=entity["id"], label=entity.get("labels", {}).get("en", {}).get("value", ""),
        description=entity.get("descriptions", {}).get("en", {}).get("value"),
        website=websites[0] if websites else None, founded_year=year,
        founder_ids=ids("founders"), hq_ids=ids("headquarters"), country_ids=ids("country"),
        industry_ids=ids("industry"), instance_of=ids("instance_of"),
        aliases=[a["value"] for a in entity.get("aliases", {}).get("en", [])],
    )


def is_company(facts: WikidataFacts) -> bool:
    return bool(set(facts.instance_of) & COMPANY_CLASSES) or bool(facts.description and COMPANY_WORDS.search(facts.description))


def choose_match(startup: Startup, candidates: list[WikidataFacts]) -> tuple[WikidataFacts | None, str]:
    """Return (match, reason). See the module docstring for the rules."""
    companies = [c for c in candidates if is_company(c)]
    if startup.domain:
        for c in companies:
            if company_domain(c.website) == startup.domain:
                return c, f"official website matches ({startup.domain})"
        return None, "no company item with the same website"
    target = startup.normalized_name
    same_name = [c for c in companies if target and target in {normalize_company_name(n) for n in [c.label, *c.aliases]}]
    if len(same_name) == 1:
        return same_name[0], "only company item with exactly this name"
    if len(same_name) > 1:
        return None, f"{len(same_name)} company items share this name; not matched to avoid confusion"
    return None, "no company item with exactly this name"


LEGAL_SUFFIX = re.compile(r",?\s+(inc|incorporated|llc|l\.l\.c|ltd|limited|corp|corporation|co|pbc|plc|gmbh)\.?$", re.IGNORECASE)


def search_term(name: str) -> str:
    """'Acme Robotics, Inc.' -> 'Acme Robotics' (Wikidata labels rarely include the legal suffix)."""
    return LEGAL_SUFFIX.sub("", name.strip()) or name


def lookup(client: PoliteClient, startup: Startup) -> tuple[WikidataFacts | None, str, dict[str, str]]:
    found = _api(client, action="wbsearchentities", search=search_term(startup.name), language="en", uselang="en", type="item", limit="7")
    qids = [r["id"] for r in found.get("search", [])]
    if not qids:
        return None, "not found on Wikidata", {}
    entities = _api(client, action="wbgetentities", ids="|".join(qids), props="labels|descriptions|aliases|claims",
                    languages="en")["entities"]
    candidates = [parse_entity(e) for e in entities.values() if "missing" not in e]
    match, reason = choose_match(startup, candidates)
    if not match:
        return None, reason, {}
    refs = list(dict.fromkeys(match.founder_ids + match.hq_ids + match.country_ids + match.industry_ids))[:50]
    labels: dict[str, str] = {}
    if refs:
        ref_entities = _api(client, action="wbgetentities", ids="|".join(refs), props="labels", languages="en")["entities"]
        labels = {q: e.get("labels", {}).get("en", {}).get("value") for q, e in ref_entities.items() if "missing" not in e}
        labels = {q: v for q, v in labels.items() if v}
    return match, reason, labels


def apply_facts(session: Session, startup: Startup, facts: WikidataFacts, labels: dict[str, str]) -> list[str]:
    """Fill only empty fields. Returns the list of fields filled."""
    url = ENTITY_URL.format(facts.qid)
    names = lambda ids: [labels[i] for i in ids if i in labels]
    filled: list[str] = []

    def fill(field_name: str, value, shown: str | None = None) -> None:
        if value in (None, "", []) or getattr(startup, field_name) not in (None, ""):
            return
        setattr(startup, field_name, value)
        add_citation(session, startup, field_name, shown or str(value), "community_sourced", key=f"wikidata:{facts.qid}",
                     source_type="open_data", publisher="Wikidata", url=url,
                     note=f"Wikidata item {facts.qid} ({facts.label}); community-edited, CC0")
        filled.append(field_name)

    if facts.website and company_domain(facts.website) and not startup.website:
        fill("website", facts.website)
        startup.domain = company_domain(facts.website)
    fill("founded_year", facts.founded_year)
    founders = ", ".join(names(facts.founder_ids))
    fill("founders", founders or None)
    hq = names(facts.hq_ids)
    fill("hq_city", hq[0] if hq else None)
    country = names(facts.country_ids)
    fill("hq_country", country[0] if country else None)
    industry = names(facts.industry_ids)
    fill("industry", industry[0].capitalize() if industry else None)
    fill("description", facts.description)
    return filled


def _due(startup: Startup, now) -> bool:
    info = (startup.extra or {}).get("wikidata")
    if not info:
        return True
    if info.get("qid"):
        return False  # already matched; Wikidata facts change slowly
    checked = info.get("checked_at")
    return not checked or now - _parse(checked) > RECHECK_AFTER


def _parse(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)


def run_enrichment(settings: Settings, client: PoliteClient, limit: int | None = None, trigger: str = "cli") -> dict:
    """Look up companies not yet checked (newest first) and fill missing fields."""
    limit = limit or settings.wikidata_max_lookups
    lock = f"source:{SOURCE_KEY}"
    with session_scope() as session:
        if not acquire_lock(session, lock, settings.job_lock_minutes):
            return {"source": SOURCE_KEY, "status": "skipped", "reason": "already running"}
        run = JobRun(job_name="enrichment", source_key=SOURCE_KEY, trigger=trigger)
        session.add(run)
        session.commit()
        run_id = run.id

    result = {"source": SOURCE_KEY, "status": "success", "checked": 0, "matched": 0, "fields_filled": 0}
    error = None
    try:
        now = utcnow()
        with session_scope() as session:
            ids = [s.id for s in session.scalars(
                select(Startup).where(Startup.is_demo.is_(False), Startup.review_status != "Archived")
                .order_by(Startup.first_discovered_at.desc())) if _due(s, now)][:limit]
        for sid in ids:
            with session_scope() as session:
                startup = session.get(Startup, sid)
                facts, reason, labels = lookup(client, startup)
                info = {"checked_at": now.isoformat(), "reason": reason}
                result["checked"] += 1
                if facts:
                    info.update(qid=facts.qid, url=ENTITY_URL.format(facts.qid), label=facts.label)
                    filled = apply_facts(session, startup, facts, labels)
                    info["fields_filled"] = filled
                    result["matched"] += 1
                    result["fields_filled"] += len(filled)
                    compute_confidence(session, startup, settings.stale_after_days)
                startup.extra = {**(startup.extra or {}), "wikidata": info}
    except Exception as exc:  # keep what was saved; report the failure
        result["status"] = "failed"
        error = f"{type(exc).__name__}: {exc}"
        result["error"] = error
    finally:
        with session_scope() as session:
            run = session.get(JobRun, run_id)
            run.status, run.finished_at, run.error_message = result["status"], utcnow(), error
            run.items_fetched, run.items_new = result["checked"], result["matched"]
            release_lock(session, lock)
    return result
