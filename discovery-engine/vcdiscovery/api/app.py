"""FastAPI application: REST endpoints for the dashboard.

Start it with:  python -m vcdiscovery.cli serve
Interactive documentation: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .. import __version__
from ..confidence import compute_confidence
from ..config import Settings, get_settings
from ..csv_io import export_filings_csv, export_rounds_csv, export_startups_csv, import_startups_csv
from ..db import configure, get_db, init_db
from ..models import (
    EVIDENCE_STATUSES,
    PIPELINE_STATUSES,
    ArticleMention,
    DuplicateCandidate,
    FundingRound,
    InvestmentScore,
    JobRun,
    NewsArticle,
    ReviewEvent,
    ScoreOverride,
    SecFiling,
    Startup,
    utcnow,
)
from ..funding import refresh_funding_summary
from ..pipeline import add_citation, latest_success, link_filing, run_discovery
from ..resolution import merge_startups
from ..scheduler import build_scheduler, describe, run_score_refresh
from ..scoring import FACTORS, METHODS, load_config, save_weights, score_startup
from ..sources import configuration_problem, load_source_configs
from ..text import company_domain, normalize_company_name
from . import serializers as ser


# ----------------------------------------------------------------- request bodies

class StatusChange(BaseModel):
    status: str = Field(description="One of: " + ", ".join(PIPELINE_STATUSES))
    note: str | None = None
    actor: str | None = "analyst"


class StartupPatch(BaseModel):
    """Manual edits by an analyst. Each change is recorded with the source you provide."""
    name: str | None = None
    website: str | None = None
    industry: str | None = None
    sub_industry: str | None = None
    description: str | None = None
    hq_city: str | None = None
    hq_state: str | None = None
    hq_country: str | None = None
    founded_year: int | None = None
    funding_stage: str | None = None
    business_model: str | None = None
    founders: str | None = None
    valuation_amount: float | None = None
    valuation_basis: str | None = None
    revenue_amount: float | None = None
    revenue_basis: str | None = None
    source_url: str | None = Field(None, description="Where this information comes from (recommended)")
    actor: str | None = "analyst"


class RunRequest(BaseModel):
    sources: list[str] | None = Field(None, description="Source keys; empty = all enabled sources")
    groups: list[str] | None = Field(None, description="news | funding | community | regulatory")


class WeightsBody(BaseModel):
    weights: dict[str, float]


class OverrideBody(BaseModel):
    factor: str
    score: float = Field(ge=0, le=100)
    note: str = Field(min_length=3, description="Why: the evidence behind your score")
    analyst: str | None = None


class DuplicateResolution(BaseModel):
    action: str = Field(description="merge | not_duplicate")
    keep_id: int | None = Field(None, description="For merge: the record to keep")


class FilingMatch(BaseModel):
    action: str = Field(description="link | reject")
    startup_id: int | None = None


# ----------------------------------------------------------------- app factory

def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure(settings.resolved_database_url)
    init_db()
    state: dict = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if settings.enable_scheduler:
            state["scheduler"] = build_scheduler(settings)
            state["scheduler"].start()
        yield
        if state.get("scheduler"):
            state["scheduler"].shutdown(wait=False)

    app = FastAPI(title="VC Discovery Engine", version=__version__, lifespan=lifespan,
                  description="Startup discovery, SEC Form D monitoring and evidence-based research scoring. "
                              "Scores are preliminary research indicators, not investment recommendations.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["*"], allow_headers=["*"])

    def require_token(x_api_key: str | None = Header(default=None)) -> None:
        if not settings.api_token:
            raise HTTPException(503, "Write API disabled: configure VCD_API_TOKEN")
        if x_api_key != settings.api_token:
            raise HTTPException(401, "Missing or wrong X-API-Key header")

    write = [Depends(require_token)]

    def get_startup(session: Session, startup_id: int) -> Startup:
        s = session.get(Startup, startup_id)
        if not s:
            raise HTTPException(404, f"Startup {startup_id} not found")
        return s

    def current_score(session: Session, sid: int) -> InvestmentScore | None:
        return session.scalar(select(InvestmentScore).where(InvestmentScore.startup_id == sid, InvestmentScore.is_current))

    # ------------------------------------------------------------- health & reference data

    @app.get("/api/health", tags=["system"])
    def health(session: Session = Depends(get_db)):
        return {"status": "ok", "version": __version__, "database": settings.resolved_database_url.split("///")[0],
                "startups": session.scalar(select(func.count(Startup.id))), "time": utcnow().isoformat()}

    @app.get("/api/reference", tags=["system"])
    def reference():
        return {"pipeline_statuses": PIPELINE_STATUSES, "evidence_statuses": EVIDENCE_STATUSES,
                "score_factors": [{"key": k, "label": v, "method": METHODS[k]} for k, v in FACTORS.items()]}

    # ------------------------------------------------------------- startups

    @app.get("/api/startups", tags=["startups"])
    def list_startups(
        session: Session = Depends(get_db),
        q: str | None = Query(None, description="Search in name or description"),
        industry: str | None = None,
        stage: str | None = None,
        status: str | None = Query(None, description="Comma-separated pipeline statuses"),
        min_confidence: float | None = None,
        min_score: float | None = None,
        discovered_after: date | None = None,
        flag: str | None = None,
        include_demo: bool = True,
        sort: str = Query("discovered", pattern="^(discovered|score|confidence|name|funding|updated)$"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        query = select(Startup, InvestmentScore).outerjoin(
            InvestmentScore, and_(InvestmentScore.startup_id == Startup.id, InvestmentScore.is_current.is_(True)))
        if q:
            like = f"%{q.lower()}%"
            query = query.where(or_(func.lower(Startup.name).like(like), func.lower(Startup.description).like(like)))
        if industry:
            query = query.where(Startup.industry == industry)
        if stage:
            query = query.where(Startup.funding_stage == stage)
        if status:
            query = query.where(Startup.review_status.in_([s.strip() for s in status.split(",")]))
        if min_confidence is not None:
            query = query.where(Startup.confidence_score >= min_confidence)
        if min_score is not None:
            query = query.where(InvestmentScore.total_score >= min_score)
        if discovered_after:
            query = query.where(Startup.first_discovered_at >= discovered_after)
        if not include_demo:
            query = query.where(Startup.is_demo.is_(False))
        order = {
            "discovered": Startup.first_discovered_at.desc(), "score": InvestmentScore.total_score.desc().nulls_last(),
            "confidence": Startup.confidence_score.desc().nulls_last(), "name": Startup.name.asc(),
            "funding": Startup.total_funding_amount.desc().nulls_last(), "updated": Startup.last_updated_at.desc(),
        }[sort]
        rows = session.execute(query.order_by(order, Startup.id)).all()
        if flag:
            rows = [r for r in rows if flag in (r[0].flags or [])]
        return {"total": len(rows), "limit": limit, "offset": offset,
                "items": [ser.startup_summary(s, sc) for s, sc in rows[offset: offset + limit]]}

    @app.get("/api/startups/{startup_id}", tags=["startups"])
    def startup_profile(startup_id: int, session: Session = Depends(get_db)):
        return ser.startup_detail(session, get_startup(session, startup_id))

    @app.patch("/api/startups/{startup_id}", tags=["startups"], dependencies=write)
    def edit_startup(startup_id: int, body: StartupPatch, session: Session = Depends(get_db)):
        s = get_startup(session, startup_id)
        changes = body.model_dump(exclude_unset=True, exclude={"source_url", "actor"})
        for field, value in changes.items():
            setattr(s, field, value)
            if field == "name":
                s.normalized_name = normalize_company_name(value)
            if field == "website":
                s.domain = company_domain(value)
            add_citation(session, s, field, None if value is None else str(value), "analyst_entered",
                          key=f"edit:{utcnow().isoformat()}", source_type="analyst", publisher=None,
                          url=body.source_url, note=f"Edited by {body.actor or 'analyst'}")
        compute_confidence(session, s, settings.stale_after_days)
        session.commit()
        return ser.startup_detail(session, s)

    @app.post("/api/startups/{startup_id}/status", tags=["pipeline"], dependencies=write)
    def change_status(startup_id: int, body: StatusChange, session: Session = Depends(get_db)):
        if body.status not in PIPELINE_STATUSES:
            raise HTTPException(422, f"status must be one of {PIPELINE_STATUSES}")
        s = get_startup(session, startup_id)
        session.add(ReviewEvent(startup_id=s.id, from_status=s.review_status, to_status=body.status, note=body.note,
                                actor=body.actor))
        s.review_status = body.status
        session.commit()
        return ser.startup_summary(s, current_score(session, s.id))

    @app.get("/api/pipeline", tags=["pipeline"])
    def pipeline(session: Session = Depends(get_db), include_demo: bool = True):
        out = []
        for status in PIPELINE_STATUSES:
            query = select(Startup).where(Startup.review_status == status)
            if not include_demo:
                query = query.where(Startup.is_demo.is_(False))
            items = session.scalars(query.order_by(Startup.last_updated_at.desc())).all()
            out.append({"status": status, "count": len(items),
                        "items": [ser.startup_summary(s, current_score(session, s.id)) for s in items[:200]]})
        return out

    @app.get("/api/filters", tags=["startups"])
    def filters(session: Session = Depends(get_db)):
        def counts(col):
            return [{"value": v, "count": c} for v, c in session.execute(
                select(col, func.count(Startup.id)).where(col.is_not(None)).group_by(col).order_by(func.count(Startup.id).desc()))]
        return {"industries": counts(Startup.industry), "stages": counts(Startup.funding_stage),
                "statuses": counts(Startup.review_status), "confidence_labels": counts(Startup.confidence_label)}

    # ------------------------------------------------------------- funding, filings, news

    @app.get("/api/funding-rounds", tags=["research"])
    def funding_rounds(session: Session = Depends(get_db), evidence_status: str | None = None,
                       conflict: bool | None = None, limit: int = Query(100, le=1000)):
        query = select(FundingRound)
        if evidence_status:
            query = query.where(FundingRound.evidence_status == evidence_status)
        if conflict is not None:
            query = query.where(FundingRound.conflict.is_(conflict))
        rows = session.scalars(query.order_by(FundingRound.announced_date.desc().nulls_last()).limit(limit))
        return [{**ser.round_dict(r), "startup_name": r.startup.name} for r in rows]

    @app.get("/api/sec/filings", tags=["sec"])
    def sec_filings(session: Session = Depends(get_db), match_status: str | None = None,
                    candidates_only: bool = False, limit: int = Query(100, le=1000)):
        query = select(SecFiling)
        if match_status:
            query = query.where(SecFiling.match_status == match_status)
        if candidates_only:
            query = query.where(SecFiling.is_startup_candidate.is_(True))
        return [ser.filing_dict(f) for f in session.scalars(query.order_by(SecFiling.filing_date.desc()).limit(limit))]

    @app.post("/api/sec/filings/{filing_id}/match", tags=["sec"], dependencies=write)
    def match_filing(filing_id: int, body: FilingMatch, session: Session = Depends(get_db)):
        filing = session.get(SecFiling, filing_id)
        if not filing:
            raise HTTPException(404, "Filing not found")
        if body.action == "reject":
            filing.match_status, filing.startup_id, filing.match_note = "rejected", None, "Rejected by analyst"
        elif body.action == "link":
            target = get_startup(session, body.startup_id or filing.suggested_startup_id or 0)
            link_filing(session, filing, target)
        else:
            raise HTTPException(422, "action must be 'link' or 'reject'")
        session.commit()
        return ser.filing_dict(filing)

    @app.get("/api/news", tags=["research"])
    def news(session: Session = Depends(get_db), startup_id: int | None = None, event_type: str | None = None,
             sentiment: str | None = None, include_duplicates: bool = False, limit: int = Query(100, le=1000)):
        query = select(NewsArticle)
        if startup_id:
            query = query.join(ArticleMention, ArticleMention.article_id == NewsArticle.id).where(ArticleMention.startup_id == startup_id)
        if sentiment:
            query = query.where(NewsArticle.sentiment == sentiment)
        if not include_duplicates:
            query = query.where(NewsArticle.duplicate_of_id.is_(None))
        rows = session.scalars(query.order_by(NewsArticle.published_at.desc().nulls_last()).limit(limit * 3)).all()
        if event_type:
            rows = [a for a in rows if event_type in (a.event_types or [])]
        return [ser.article_dict(a) for a in rows[:limit]]

    # ------------------------------------------------------------- duplicates

    @app.get("/api/duplicates", tags=["data quality"])
    def duplicates(session: Session = Depends(get_db), status: str = "open"):
        out = []
        for d in session.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status == status)):
            a, b = session.get(Startup, d.startup_a_id), session.get(Startup, d.startup_b_id)
            out.append({"id": d.id, "similarity": d.similarity, "reason": d.reason, "status": d.status,
                        "a": ser.startup_summary(a), "b": ser.startup_summary(b)})
        return out

    @app.post("/api/duplicates/{dup_id}/resolve", tags=["data quality"], dependencies=write)
    def resolve_duplicate(dup_id: int, body: DuplicateResolution, session: Session = Depends(get_db)):
        d = session.get(DuplicateCandidate, dup_id)
        if not d or d.status != "open":
            raise HTTPException(404, "Open duplicate candidate not found")
        if body.action == "not_duplicate":
            d.status, d.resolved_at = "not_duplicate", utcnow()
            for sid in (d.startup_a_id, d.startup_b_id):
                compute_confidence(session, session.get(Startup, sid))
            session.commit()
            return {"status": "not_duplicate"}
        if body.action != "merge":
            raise HTTPException(422, "action must be 'merge' or 'not_duplicate'")
        keep_id = body.keep_id or d.startup_a_id
        if keep_id not in (d.startup_a_id, d.startup_b_id):
            raise HTTPException(422, "keep_id must be one of the two records")
        remove_id = d.startup_b_id if keep_id == d.startup_a_id else d.startup_a_id
        keep = merge_startups(session, session.get(Startup, keep_id), session.get(Startup, remove_id))
        refresh_funding_summary(keep)
        compute_confidence(session, keep)
        session.commit()
        return ser.startup_detail(session, keep)

    # ------------------------------------------------------------- scoring

    @app.get("/api/scoring/weights", tags=["scoring"])
    def get_weights(session: Session = Depends(get_db)):
        config = load_config(session, settings.load_json(settings.scoring_file))
        return {"weights": config["weights"], "thresholds": config["thresholds"],
                "factors": [{"key": k, "label": v, "method": METHODS[k]} for k, v in FACTORS.items()]}

    @app.put("/api/scoring/weights", tags=["scoring"], dependencies=write)
    def put_weights(body: WeightsBody, session: Session = Depends(get_db)):
        try:
            weights = save_weights(session, body.weights)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        session.commit()
        return {"weights": weights, "note": "Run POST /api/scores/refresh to apply to all companies"}

    @app.get("/api/startups/{startup_id}/score", tags=["scoring"])
    def get_score(startup_id: int, session: Session = Depends(get_db)):
        get_startup(session, startup_id)
        return ser.full_score(current_score(session, startup_id))

    @app.post("/api/startups/{startup_id}/score", tags=["scoring"], dependencies=write)
    def rescore(startup_id: int, session: Session = Depends(get_db)):
        s = get_startup(session, startup_id)
        result = score_startup(session, s, load_config(session, settings.load_json(settings.scoring_file)))
        session.commit()
        return ser.full_score(result)

    @app.post("/api/startups/{startup_id}/score-override", tags=["scoring"], dependencies=write)
    def override(startup_id: int, body: OverrideBody, session: Session = Depends(get_db)):
        if body.factor not in FACTORS:
            raise HTTPException(422, f"factor must be one of {list(FACTORS)}")
        s = get_startup(session, startup_id)
        row = session.scalar(select(ScoreOverride).where(ScoreOverride.startup_id == s.id, ScoreOverride.factor == body.factor))
        if row:
            row.score, row.note, row.analyst, row.created_at = body.score, body.note, body.analyst, utcnow()
        else:
            session.add(ScoreOverride(startup_id=s.id, factor=body.factor, score=body.score, note=body.note, analyst=body.analyst))
        session.flush()
        result = score_startup(session, s, load_config(session, settings.load_json(settings.scoring_file)))
        session.commit()
        return ser.full_score(result)

    @app.delete("/api/startups/{startup_id}/score-override/{factor}", tags=["scoring"], dependencies=write)
    def remove_override(startup_id: int, factor: str, session: Session = Depends(get_db)):
        s = get_startup(session, startup_id)
        row = session.scalar(select(ScoreOverride).where(ScoreOverride.startup_id == s.id, ScoreOverride.factor == factor))
        if row:
            session.delete(row)
            session.flush()
        result = score_startup(session, s, load_config(session, settings.load_json(settings.scoring_file)))
        session.commit()
        return ser.full_score(result)

    @app.post("/api/scores/refresh", tags=["scoring"], dependencies=write)
    def refresh_all_scores():
        return run_score_refresh(settings, trigger="manual")

    # ------------------------------------------------------------- automation

    @app.post("/api/discovery/run", tags=["automation"], dependencies=write, status_code=202)
    def run_now(body: RunRequest, background: BackgroundTasks):
        background.add_task(run_discovery, settings, keys=body.sources, groups=body.groups, trigger="manual")
        return {"status": "started", "message": "Discovery is running in the background. Check GET /api/jobs for progress."}

    @app.get("/api/jobs", tags=["automation"])
    def jobs(session: Session = Depends(get_db), status: str | None = None, limit: int = Query(50, le=500)):
        query = select(JobRun)
        if status:
            query = query.where(JobRun.status == status)
        return [ser.job_dict(j) for j in session.scalars(query.order_by(JobRun.started_at.desc()).limit(limit))]

    @app.get("/api/sources/status", tags=["automation"])
    def sources_status(session: Session = Depends(get_db)):
        last_ok = latest_success(session)
        out = []
        for cfg in load_source_configs(settings):
            last = session.scalar(select(JobRun).where(JobRun.source_key == cfg["key"]).order_by(JobRun.started_at.desc()))
            health = "never_run" if not last else ("ok" if last.status in ("success", "partial") else last.status)
            if not cfg.get("enabled"):
                health = "disabled"
            elif configuration_problem(cfg, settings):
                health = "needs_configuration"
            out.append({"key": cfg["key"], "name": cfg["name"], "group": cfg["group"], "enabled": cfg.get("enabled", False),
                        "health": health, "last_success": ser.iso(last_ok.get(cfg["key"])),
                        "last_run": ser.job_dict(last) if last else None, "access_notes": cfg.get("access_notes"),
                        "disabled_reason": cfg.get("disabled_reason")})
        return out

    @app.get("/api/schedule", tags=["automation"])
    def schedule():
        return {"enabled": settings.enable_scheduler, "jobs": describe()}

    # ------------------------------------------------------------- import / export

    @app.get("/api/export/startups.csv", tags=["import/export"], response_class=PlainTextResponse)
    def export_startups(session: Session = Depends(get_db), include_demo: bool = True):
        return PlainTextResponse(export_startups_csv(session, include_demo), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=startups.csv"})

    @app.get("/api/export/funding_rounds.csv", tags=["import/export"], response_class=PlainTextResponse)
    def export_rounds(session: Session = Depends(get_db)):
        return PlainTextResponse(export_rounds_csv(session), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=funding_rounds.csv"})

    @app.get("/api/export/sec_filings.csv", tags=["import/export"], response_class=PlainTextResponse)
    def export_filings(session: Session = Depends(get_db)):
        return PlainTextResponse(export_filings_csv(session), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=sec_filings.csv"})

    @app.post("/api/import/startups", tags=["import/export"], dependencies=write)
    async def import_startups(file: UploadFile = File(...), session: Session = Depends(get_db)):
        max_upload_bytes = 2 * 1024 * 1024
        content_bytes = await file.read(max_upload_bytes + 1)
        if len(content_bytes) > max_upload_bytes:
            raise HTTPException(413, "CSV upload exceeds 2 MiB limit")
        try:
            content = content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(400, "CSV upload must be UTF-8 encoded") from exc
        result = import_startups_csv(session, content)
        session.commit()
        return result

    return app
