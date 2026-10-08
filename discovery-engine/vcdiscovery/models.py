"""Database tables.

Design rules:
* Every fact about a company should be traceable to a `Citation` (source URL + retrieval time).
* Missing information is stored as NULL, never as a guessed value.
* Funding amounts carry an `evidence_status` so confirmed, reported, target, rumoured and
  regulatory (Form D) figures are never mixed up.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

PIPELINE_STATUSES = [
    "Discovered",
    "Needs Verification",
    "Under Review",
    "Watchlist",
    "Due Diligence",
    "Rejected",
    "Archived",
]

# Ordered from strongest to weakest evidence.
EVIDENCE_STATUSES = {
    "regulatory_filing": "Regulatory filing (e.g. SEC Form D). Shows an offering, not a priced VC round.",
    "confirmed": "Company announcement corroborated by an independent outlet, or 2+ independent outlets agree.",
    "company_announced": "Press release or statement from the company itself, not yet corroborated.",
    "reported": "Reported by one news outlet, not yet corroborated.",
    "analyst_entered": "Entered or imported by an analyst; check the cited source.",
    "target": "Amount the company is seeking or aims to raise. Not money raised.",
    "rumor": "Unconfirmed report (e.g. 'in talks', 'reportedly'). Never treated as raised.",
}
# Statuses that may be counted as capital actually raised.
RAISED_STATUSES = {"confirmed", "company_announced", "reported", "analyst_entered"}


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite does not store time zones)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Startup(Base):
    __tablename__ = "startups"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True)  # e.g. DS-001 from the dashboard
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(500))
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    industry: Mapped[str | None] = mapped_column(String(120), index=True)
    sub_industry: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    hq_city: Mapped[str | None] = mapped_column(String(120))
    hq_state: Mapped[str | None] = mapped_column(String(120))
    hq_country: Mapped[str | None] = mapped_column(String(120))
    founded_year: Mapped[int | None] = mapped_column(Integer)
    funding_stage: Mapped[str | None] = mapped_column(String(60), index=True)
    business_model: Mapped[str | None] = mapped_column(String(255))
    founders: Mapped[str | None] = mapped_column(Text)  # only people publicly described as founders
    key_people: Mapped[str | None] = mapped_column(Text)  # e.g. executive officers listed on Form D

    total_funding_amount: Mapped[float | None] = mapped_column(Float)
    total_funding_currency: Mapped[str | None] = mapped_column(String(8))
    total_funding_basis: Mapped[str | None] = mapped_column(Text)
    latest_funding_amount: Mapped[float | None] = mapped_column(Float)
    latest_funding_currency: Mapped[str | None] = mapped_column(String(8))
    latest_funding_date: Mapped[date | None] = mapped_column(Date)
    latest_funding_status: Mapped[str | None] = mapped_column(String(40))
    valuation_amount: Mapped[float | None] = mapped_column(Float)
    valuation_currency: Mapped[str | None] = mapped_column(String(8))
    valuation_basis: Mapped[str | None] = mapped_column(Text)
    revenue_amount: Mapped[float | None] = mapped_column(Float)
    revenue_basis: Mapped[str | None] = mapped_column(Text)

    growth_signals: Mapped[str | None] = mapped_column(Text)
    latest_news_title: Mapped[str | None] = mapped_column(Text)
    latest_news_url: Mapped[str | None] = mapped_column(String(1000))
    latest_news_date: Mapped[datetime | None] = mapped_column(DateTime)
    primary_source_url: Mapped[str | None] = mapped_column(String(1000))
    sec_cik: Mapped[str | None] = mapped_column(String(20), index=True)

    review_status: Mapped[str] = mapped_column(String(40), default="Discovered", index=True)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    confidence_label: Mapped[str | None] = mapped_column(String(20))
    confidence_breakdown: Mapped[dict | None] = mapped_column(JSON)
    flags: Mapped[list | None] = mapped_column(JSON, default=list)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[dict | None] = mapped_column(JSON)  # untouched rows from an imported tracker

    discovered_via: Mapped[str | None] = mapped_column(String(80))
    first_discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime)

    rounds: Mapped[list["FundingRound"]] = relationship(back_populates="startup", cascade="all, delete-orphan")
    signals: Mapped[list["DiscoverySignal"]] = relationship(back_populates="startup", cascade="all, delete-orphan")
    citations: Mapped[list["Citation"]] = relationship(back_populates="startup", cascade="all, delete-orphan")
    mentions: Mapped[list["ArticleMention"]] = relationship(back_populates="startup", cascade="all, delete-orphan")
    filings: Mapped[list["SecFiling"]] = relationship(back_populates="startup", foreign_keys="SecFiling.startup_id")

    def add_flag(self, flag: str) -> None:
        current = list(self.flags or [])
        if flag not in current:
            current.append(flag)
            self.flags = current

    def remove_flag(self, flag: str) -> None:
        if self.flags and flag in self.flags:
            self.flags = [f for f in self.flags if f != flag]


class NewsArticle(Base):
    """A news story, press release or community post. Only headline, link and a short
    summary are stored; full article text is never copied."""

    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(80), index=True)
    source_type: Mapped[str] = mapped_column(String(40))  # news | press_release | community
    publisher: Mapped[str | None] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    title_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("news_articles.id"))
    event_types: Mapped[list | None] = mapped_column(JSON)
    sentiment: Mapped[str | None] = mapped_column(String(20))
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    classification_evidence: Mapped[dict | None] = mapped_column(JSON)
    community_metrics: Mapped[dict | None] = mapped_column(JSON)  # e.g. HN points/comments

    mentions: Mapped[list["ArticleMention"]] = relationship(back_populates="article", cascade="all, delete-orphan")


class ArticleMention(Base):
    __tablename__ = "article_mentions"
    __table_args__ = (UniqueConstraint("article_id", "startup_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("news_articles.id", ondelete="CASCADE"))
    startup_id: Mapped[int] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"), index=True)
    match_method: Mapped[str] = mapped_column(String(40))  # extracted_subject | name_mention | hn_title

    article: Mapped[NewsArticle] = relationship(back_populates="mentions")
    startup: Mapped[Startup] = relationship(back_populates="mentions")


class Investor(Base):
    __tablename__ = "investors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RoundInvestor(Base):
    __tablename__ = "round_investors"
    __table_args__ = (UniqueConstraint("round_id", "investor_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("funding_rounds.id", ondelete="CASCADE"))
    investor_id: Mapped[int] = mapped_column(ForeignKey("investors.id", ondelete="CASCADE"))
    is_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))

    investor: Mapped[Investor] = relationship()


class FundingRound(Base):
    __tablename__ = "funding_rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    startup_id: Mapped[int] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"), index=True)
    round_type: Mapped[str | None] = mapped_column(String(60))
    amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    amount_text: Mapped[str | None] = mapped_column(String(120))  # as written by the source
    announced_date: Mapped[date | None] = mapped_column(Date)
    evidence_status: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("news_articles.id", ondelete="SET NULL"))
    sec_filing_id: Mapped[int | None] = mapped_column(ForeignKey("sec_filings.id", ondelete="SET NULL"))
    publishers: Mapped[list | None] = mapped_column(JSON, default=list)  # independent outlets citing it
    conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_note: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    startup: Mapped[Startup] = relationship(back_populates="rounds")
    investors: Mapped[list[RoundInvestor]] = relationship(cascade="all, delete-orphan")


class SecFiling(Base):
    """SEC Form D (or D/A). A Form D is a notice of an exempt offering: it does NOT prove a
    completed VC round, a valuation, or institutional investor participation."""

    __tablename__ = "sec_filings"

    id: Mapped[int] = mapped_column(primary_key=True)
    accession_number: Mapped[str] = mapped_column(String(30), unique=True)
    cik: Mapped[str] = mapped_column(String(20), index=True)
    form_type: Mapped[str] = mapped_column(String(10))
    is_amendment: Mapped[bool] = mapped_column(Boolean, default=False)
    issuer_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    filing_date: Mapped[date | None] = mapped_column(Date, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    year_of_incorporation: Mapped[int | None] = mapped_column(Integer)
    incorporated_within_five_years: Mapped[bool | None] = mapped_column(Boolean)
    industry_group: Mapped[str | None] = mapped_column(String(120))
    investment_fund_type: Mapped[str | None] = mapped_column(String(120))
    revenue_range: Mapped[str | None] = mapped_column(String(80))
    federal_exemptions: Mapped[list | None] = mapped_column(JSON)
    date_of_first_sale: Mapped[date | None] = mapped_column(Date)
    total_offering_amount: Mapped[float | None] = mapped_column(Float)
    offering_amount_indefinite: Mapped[bool] = mapped_column(Boolean, default=False)
    total_amount_sold: Mapped[float | None] = mapped_column(Float)
    total_remaining: Mapped[float | None] = mapped_column(Float)
    investor_count: Mapped[int | None] = mapped_column(Integer)
    has_non_accredited_investors: Mapped[bool | None] = mapped_column(Boolean)
    securities_types: Mapped[list | None] = mapped_column(JSON)
    related_persons: Mapped[list | None] = mapped_column(JSON)
    city: Mapped[str | None] = mapped_column(String(120))
    state_or_country: Mapped[str | None] = mapped_column(String(80))
    filing_url: Mapped[str] = mapped_column(String(1000))
    document_url: Mapped[str | None] = mapped_column(String(1000))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    is_startup_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    candidate_reason: Mapped[str | None] = mapped_column(Text)
    startup_id: Mapped[int | None] = mapped_column(ForeignKey("startups.id", ondelete="SET NULL"), index=True)
    suggested_startup_id: Mapped[int | None] = mapped_column(ForeignKey("startups.id", ondelete="SET NULL"))
    match_status: Mapped[str] = mapped_column(String(30), default="unmatched")
    # unmatched | auto_matched | created | needs_review | confirmed | rejected
    match_score: Mapped[float | None] = mapped_column(Float)
    match_note: Mapped[str | None] = mapped_column(Text)
    review_flags: Mapped[list | None] = mapped_column(JSON)

    startup: Mapped[Startup | None] = relationship(back_populates="filings", foreign_keys=[startup_id])


class DiscoverySignal(Base):
    __tablename__ = "discovery_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    startup_id: Mapped[int] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"), index=True)
    signal_type: Mapped[str] = mapped_column(String(60), index=True)
    source_key: Mapped[str] = mapped_column(String(80))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("news_articles.id", ondelete="SET NULL"))
    sec_filing_id: Mapped[int | None] = mapped_column(ForeignKey("sec_filings.id", ondelete="SET NULL"))
    detail: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)

    startup: Mapped[Startup] = relationship(back_populates="signals")


class Citation(Base):
    """One claim about one field of a company, with where and when it came from."""

    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(primary_key=True)
    startup_id: Mapped[int] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"), index=True)
    field_name: Mapped[str] = mapped_column(String(80))
    value_text: Mapped[str | None] = mapped_column(Text)
    evidence_status: Mapped[str] = mapped_column(String(40))
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=False)  # algorithmic, not source-reported
    source_type: Mapped[str | None] = mapped_column(String(40))
    publisher: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("news_articles.id", ondelete="SET NULL"))
    sec_filing_id: Mapped[int | None] = mapped_column(ForeignKey("sec_filings.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)

    startup: Mapped[Startup] = relationship(back_populates="citations")


class InvestmentScore(Base):
    __tablename__ = "investment_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    startup_id: Mapped[int] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    total_score: Mapped[float | None] = mapped_column(Float)
    rating: Mapped[str] = mapped_column(String(40))
    coverage: Mapped[float] = mapped_column(Float)
    weights: Mapped[dict] = mapped_column(JSON)
    factors: Mapped[list] = mapped_column(JSON)
    missing: Mapped[list] = mapped_column(JSON)
    thesis: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[list | None] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(20))


class ScoreOverride(Base):
    __tablename__ = "score_overrides"
    __table_args__ = (UniqueConstraint("startup_id", "factor"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    startup_id: Mapped[int] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"))
    factor: Mapped[str] = mapped_column(String(40))
    score: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(Text)
    analyst: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReviewEvent(Base):
    __tablename__ = "review_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    startup_id: Mapped[int] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DuplicateCandidate(Base):
    __tablename__ = "duplicate_candidates"
    __table_args__ = (UniqueConstraint("startup_a_id", "startup_b_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    startup_a_id: Mapped[int] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"))
    startup_b_id: Mapped[int] = mapped_column(ForeignKey("startups.id", ondelete="CASCADE"))
    similarity: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | merged | not_duplicate
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)


class JobRun(Base):
    """Data collection log: one row per source per run."""

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(80), index=True)
    source_key: Mapped[str | None] = mapped_column(String(80), index=True)
    trigger: Mapped[str] = mapped_column(String(20))  # manual | scheduled | cli
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|success|failed|skipped
    items_fetched: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    startups_created: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)


class JobLock(Base):
    __tablename__ = "job_locks"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
