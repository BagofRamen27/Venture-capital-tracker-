"""Common data shapes returned by every source connector."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from ..http import PoliteClient


@dataclass
class NewsItem:
    """A headline from an RSS feed, press-release wire or community site."""

    source_key: str
    source_type: str  # news | press_release | video | community
    publisher: str
    url: str
    title: str
    summary: str | None = None
    published_at: datetime | None = None
    community_metrics: dict | None = None  # e.g. {"points": 120, "comments": 40, "discussion_url": ...}
    category: str = "news"  # news | funding | press_release | video | community


@dataclass
class RelatedPerson:
    name: str
    relationships: list[str] = field(default_factory=list)
    clarification: str | None = None


@dataclass
class FormDItem:
    accession_number: str
    cik: str
    form_type: str
    issuer_name: str
    filing_date: date | None
    filing_url: str
    document_url: str | None = None
    is_amendment: bool = False
    entity_type: str | None = None
    year_of_incorporation: int | None = None
    incorporated_within_five_years: bool | None = None
    industry_group: str | None = None
    investment_fund_type: str | None = None
    revenue_range: str | None = None
    federal_exemptions: list[str] = field(default_factory=list)
    date_of_first_sale: date | None = None
    total_offering_amount: float | None = None
    offering_amount_indefinite: bool = False
    total_amount_sold: float | None = None
    total_remaining: float | None = None
    investor_count: int | None = None
    has_non_accredited_investors: bool | None = None
    securities_types: list[str] = field(default_factory=list)
    related_persons: list[RelatedPerson] = field(default_factory=list)
    city: str | None = None
    state_or_country: str | None = None


class Source(Protocol):
    key: str
    name: str
    group: str  # news | funding | community | video | regulatory

    def fetch(self, client: PoliteClient) -> list[NewsItem] | list[FormDItem]: ...
