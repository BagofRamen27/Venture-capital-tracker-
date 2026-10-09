"""Write the static data files the VentureScout website reads (no server needed).

Files written to the output folder:
* discovery.json - discovered companies with evidence, funding rounds, SEC filings, scores
* news.json      - recent classified headlines
* status.json    - source health, last runs and record counts
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .api import serializers as ser
from .config import Settings
from .models import (
    EVIDENCE_STATUSES,
    PIPELINE_STATUSES,
    JobRun,
    NewsArticle,
    SecFiling,
    Startup,
    utcnow,
)
from .pipeline import latest_success
from .scheduler import describe
from .scoring import FACTORS, METHODS
from .sources import configuration_problem, load_source_configs

MAX_COMPANIES = 1000
MAX_NEWS = 150
DISCLAIMER = ("Scores are preliminary research indicators built from public evidence only. "
              "They are not investment recommendations.")


def _company(session: Session, s: Startup) -> dict:
    d = ser.startup_detail(session, s)
    return {
        **{k: d[k] for k in (
            "id", "name", "website", "industry", "description", "headquarters", "founded_year", "funding_stage",
            "total_funding", "latest_funding", "review_status", "confidence", "investment_score", "flags",
            "discovered_via", "first_discovered_at", "last_updated_at", "latest_news", "founders", "key_people",
            "investors", "valuation", "revenue", "primary_source_url", "confidence_breakdown")},
        "funding_rounds": d["funding_rounds"],
        "sec_filings": [{k: f[k] for k in (
            "form_type", "issuer_name", "filing_date", "industry_group", "total_offering_amount",
            "offering_amount_indefinite", "total_amount_sold", "investor_count", "filing_url", "match_status",
            "review_flags", "disclaimer")} for f in d["sec_filings"]],
        "news": [{k: a[k] for k in ("title", "url", "publisher", "published_at", "event_types", "sentiment",
                                    "classification_evidence")} for a in d["news"][:10]],
        "signals": d["signals"][:10],
        "citations": d["citations"][:15],
        "score": d["score"],
    }


def build_site_data(session: Session, settings: Settings) -> dict[str, dict]:
    now = utcnow().isoformat()
    companies = session.scalars(
        select(Startup).where(Startup.review_status != "Archived", Startup.is_demo.is_(False))
        .order_by(Startup.last_updated_at.desc()).limit(MAX_COMPANIES)).all()
    discovery = {
        "generated_at": now, "disclaimer": DISCLAIMER, "evidence_statuses": EVIDENCE_STATUSES,
        "pipeline_statuses": PIPELINE_STATUSES,
        "factors": [{"key": k, "label": v, "method": METHODS[k]} for k, v in FACTORS.items()],
        "companies": [_company(session, s) for s in companies],
    }
    articles = session.scalars(select(NewsArticle).where(NewsArticle.duplicate_of_id.is_(None))
                               .order_by(NewsArticle.published_at.desc().nulls_last()).limit(MAX_NEWS)).all()
    news = {"generated_at": now, "note": "Tone describes a headline's wording, not investment quality.",
            "articles": [{**{k: v for k, v in ser.article_dict(a).items() if k not in ("id", "duplicate_of_id", "note")},
                          "companies": [m.startup.name for m in a.mentions]} for a in articles]}
    last_ok = latest_success(session)
    sources = []
    for cfg in load_source_configs(settings):
        last = session.scalar(select(JobRun).where(JobRun.source_key == cfg["key"]).order_by(JobRun.started_at.desc()))
        problem = configuration_problem(cfg, settings) if cfg.get("enabled") else None
        health = "disabled" if not cfg.get("enabled") else "needs_configuration" if problem else (
            "never_run" if not last else ("ok" if last.status in ("success", "partial") else last.status))
        sources.append({"key": cfg["key"], "name": cfg["name"], "group": cfg["group"], "health": health,
                        "last_success": ser.iso(last_ok.get(cfg["key"])),
                        "last_error": problem or (last.error_message if last and last.status == "failed" else None),
                        "access_notes": cfg.get("access_notes"), "disabled_reason": cfg.get("disabled_reason")})
    status = {
        "generated_at": now, "sources": sources, "schedule": describe(),
        "counts": {"companies": session.scalar(select(func.count(Startup.id)).where(Startup.is_demo.is_(False))),
                   "articles": session.scalar(select(func.count(NewsArticle.id))),
                   "sec_filings": session.scalar(select(func.count(SecFiling.id)))},
        "recent_jobs": [ser.job_dict(j) for j in session.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(30))],
    }
    return {"discovery.json": discovery, "news.json": news, "status.json": status}


def write_site_data(session: Session, settings: Settings, out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, payload in build_site_data(session, settings).items():
        path = out / name
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        written.append(path)
    return written
