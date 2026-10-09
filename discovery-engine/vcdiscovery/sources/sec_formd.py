"""SEC EDGAR Form D monitoring.

How it works (all free, no API key):
1. Read EDGAR's daily form index: https://www.sec.gov/Archives/edgar/daily-index/YYYY/QTRn/form.YYYYMMDD.idx
2. Keep rows whose form type is `D` (new notice) or `D/A` (amendment).
3. Download each filing's structured XML (`primary_doc.xml`) and read the offering details.

SEC fair-access rules: identify yourself with a User-Agent containing your name and email
(set VCD_SEC_USER_AGENT), and stay under 10 requests per second. See
https://www.sec.gov/os/accessing-edgar-data

A Form D is a notice that a company is selling securities under an exemption. It does NOT prove
a completed venture round, a valuation, or that professional investors took part.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Callable

from ..http import PoliteClient, SourceUnavailable
from ..text import parse_amount
from .base import FormDItem, RelatedPerson

ARCHIVES = "https://www.sec.gov/Archives/"
INDEX_ROW_RE = re.compile(
    r"^(?P<form>\S+)\s+(?P<name>.+?)\s+(?P<cik>\d{1,10})\s+(?P<date>\d{8})\s+(?P<file>edgar/data/\S+)\s*$"
)
FORM_TYPES = {"D", "D/A"}

# Form D industry groups that usually describe operating companies (not funds or property deals).
STARTUP_INDUSTRY_GROUPS = {
    "Other Technology", "Computers", "Telecommunications", "Biotechnology", "Pharmaceuticals", "Other Health Care",
    "Energy Conservation", "Environmental Services", "Other Energy", "Business Services", "Manufacturing",
    "Other Banking and Financial Services", "Insurance", "Agriculture", "Other",
}
INDUSTRY_LABELS = {
    "Biotechnology": "Biotechnology", "Pharmaceuticals": "Biotechnology", "Other Health Care": "Healthcare Technology",
    "Computers": "Technology", "Other Technology": "Technology", "Telecommunications": "Telecommunications",
    "Energy Conservation": "Climate Technology", "Environmental Services": "Climate Technology", "Other Energy": "Energy",
    "Other Banking and Financial Services": "Financial Services", "Insurance": "Financial Services",
    "Business Services": "Business Services", "Manufacturing": "Manufacturing", "Agriculture": "Agriculture",
}
NON_OPERATING_NAME_RE = re.compile(
    r"\b(?:fund|funds|l\.?p\.?|spv|series \d+|a series of|reit|trust|capital partners|co-?invest|feeder|master|"
    r"opportunit(?:y|ies) (?:fund|zone)|investors? llc|holdings? (?:i|ii|iii|iv|v)\b)",
    re.IGNORECASE,
)


def daily_index_url(day: date) -> str:
    quarter = (day.month - 1) // 3 + 1
    return f"{ARCHIVES}edgar/daily-index/{day.year}/QTR{quarter}/form.{day:%Y%m%d}.idx"


def parse_daily_index(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = INDEX_ROW_RE.match(line)
        if not m or m.group("form") not in FORM_TYPES:
            continue
        file_name = m.group("file")
        accession = file_name.rsplit("/", 1)[-1].removesuffix(".txt")
        cik = m.group("cik").lstrip("0") or "0"
        folder = f"{ARCHIVES}edgar/data/{cik}/{accession.replace('-', '')}/"
        rows.append({
            "form_type": m.group("form"),
            "issuer_name": " ".join(m.group("name").split()),
            "cik": cik,
            "filing_date": datetime.strptime(m.group("date"), "%Y%m%d").date(),
            "accession_number": accession,
            "filing_url": f"{folder}{accession}-index.htm",
            "document_url": f"{folder}primary_doc.xml",
        })
    return rows


def _strip_ns(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in ("true", "y", "yes", "1")


def _date(value: str | None) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else None
    except ValueError:
        return None


def parse_form_d_xml(xml: bytes | str, meta: dict) -> FormDItem:
    """Parse a Form D `primary_doc.xml`. `meta` comes from the daily index row."""
    root = _strip_ns(ET.fromstring(xml))
    issuer = root.find("primaryIssuer")
    offering = root.find("offeringData")
    address = issuer.find("issuerAddress") if issuer is not None else None

    year_value = _text(issuer, "yearOfInc/value")
    within_five = _bool(_text(issuer, "yearOfInc/withinFiveYears"))
    if within_five is None and _bool(_text(issuer, "yearOfInc/overFiveYears")):
        within_five = False

    amounts = offering.find("offeringSalesAmounts") if offering is not None else None
    offering_raw = _text(amounts, "totalOfferingAmount")
    indefinite = bool(offering_raw and offering_raw.lower().startswith("indefinite"))

    persons = []
    for info in root.findall("relatedPersonsList/relatedPersonInfo"):
        first = _text(info, "relatedPersonName/firstName") or ""
        middle = _text(info, "relatedPersonName/middleName") or ""
        last = _text(info, "relatedPersonName/lastName") or ""
        name = " ".join(p for p in (first, middle, last) if p and p.upper() != "N/A")
        rels = [r.text.strip() for r in info.findall("relatedPersonRelationshipList/relationship") if r.text]
        if name:
            persons.append(RelatedPerson(name=name, relationships=rels, clarification=_text(info, "relationshipClarification")))

    securities = []
    types_el = offering.find("typesOfSecuritiesOffered") if offering is not None else None
    if types_el is not None:
        for child in types_el:
            if _bool(child.text):
                securities.append(re.sub(r"^is|Type$", "", child.tag))
            elif child.tag == "descriptionOfOtherType" and child.text:
                securities.append(child.text.strip())

    count_raw = _text(offering, "investors/totalNumberAlreadyInvested")
    form_type = _text(root, "submissionType") or meta.get("form_type", "D")
    is_amendment = _bool(_text(offering, "typeOfFiling/newOrAmendment/isAmendment"))

    return FormDItem(
        accession_number=meta["accession_number"],
        cik=meta["cik"],
        form_type=form_type,
        issuer_name=_text(issuer, "entityName") or meta["issuer_name"],
        filing_date=meta.get("filing_date"),
        filing_url=meta["filing_url"],
        document_url=meta.get("document_url"),
        is_amendment=bool(is_amendment) or form_type.endswith("/A"),
        entity_type=_text(issuer, "entityType"),
        year_of_incorporation=int(year_value) if year_value and year_value.isdigit() else None,
        incorporated_within_five_years=within_five,
        industry_group=_text(offering, "industryGroup/industryGroupType"),
        investment_fund_type=_text(offering, "industryGroup/investmentFundInfo/investmentFundType"),
        revenue_range=_text(offering, "issuerSize/revenueRange") or _text(offering, "issuerSize/aggregateNetAssetValueRange"),
        federal_exemptions=[i.text.strip() for i in root.findall("offeringData/federalExemptionsExclusions/item") if i.text],
        date_of_first_sale=_date(_text(offering, "typeOfFiling/dateOfFirstSale/value")),
        total_offering_amount=None if indefinite else parse_amount(offering_raw),
        offering_amount_indefinite=indefinite,
        total_amount_sold=parse_amount(_text(amounts, "totalAmountSold")),
        total_remaining=None if (_text(amounts, "totalRemaining") or "").lower().startswith("indefinite") else parse_amount(_text(amounts, "totalRemaining")),
        investor_count=int(count_raw) if count_raw and count_raw.isdigit() else None,
        has_non_accredited_investors=_bool(_text(offering, "investors/hasNonAccreditedInvestors")),
        securities_types=securities,
        related_persons=persons,
        city=_text(address, "city"),
        state_or_country=_text(address, "stateOrCountryDescription") or _text(address, "stateOrCountry"),
    )


def assess_candidate(item: FormDItem) -> tuple[bool, str]:
    """Is this filing likely to come from an early-stage operating company? Returns (bool, reason)."""
    if item.industry_group == "Pooled Investment Fund" or item.investment_fund_type:
        return False, "Pooled investment fund (investor vehicle, not a startup)"
    if NON_OPERATING_NAME_RE.search(item.issuer_name):
        return False, "Name suggests a fund, SPV or trust"
    if item.entity_type and "partnership" in item.entity_type.lower():
        return False, "Limited partnership (usually a fund or SPV)"
    if item.industry_group not in STARTUP_INDUSTRY_GROUPS:
        return False, f"Industry group '{item.industry_group}' is outside the startup filter"
    if item.incorporated_within_five_years is False:
        return False, "Incorporated more than five years ago"
    if item.incorporated_within_five_years is None:
        return False, "Year of incorporation not stated"
    return True, f"Operating company in '{item.industry_group}', incorporated within five years"


def review_flags(item: FormDItem) -> list[str]:
    flags = []
    if item.is_amendment:
        flags.append("Amendment (D/A): may restate or update an earlier notice")
    if item.offering_amount_indefinite:
        flags.append("Offering amount stated as 'Indefinite'")
    if item.total_amount_sold in (None, 0):
        flags.append("No securities reported sold yet; this is not evidence of a completed raise")
    if item.has_non_accredited_investors:
        flags.append("Includes non-accredited investors")
    if "06c" in item.federal_exemptions:
        flags.append("Rule 506(c): general solicitation allowed (public fundraising)")
    if item.total_offering_amount and item.total_amount_sold and item.total_amount_sold > item.total_offering_amount:
        flags.append("Amount sold exceeds offering amount; check the filing")
    return flags


class SecFormDSource:
    group = "regulatory"

    def __init__(self, key: str = "sec_form_d", name: str = "SEC EDGAR Form D", lookback_days: int = 3,
                 max_filings: int = 150, today: Callable[[], date] = date.today):
        self.key = key
        self.name = name
        self.lookback_days = lookback_days
        self.max_filings = max_filings
        self.today = today
        self.skip_accession: Callable[[str], bool] = lambda _acc: False

    def fetch(self, client: PoliteClient) -> list[FormDItem]:
        rows: list[dict] = []
        unpublished: str | None = None
        loaded = False
        for offset in range(1, self.lookback_days + 1):
            day = self.today() - timedelta(days=offset)
            if day.weekday() >= 5:
                continue  # EDGAR does not publish daily indexes on weekends
            url = daily_index_url(day)
            resp = client.get(url, ok_statuses=(403, 404))
            if resp.status_code == 404:
                continue  # holiday
            if resp.status_code == 403:
                # EDGAR also answers 403 for an index that does not exist (yet): yesterday's is published
                # around 10 pm US Eastern. If another day's index loads, access itself is fine.
                unpublished = unpublished or url
                continue
            loaded = True
            rows.extend(parse_daily_index(resp.text))
        if unpublished and not loaded:
            # No index loaded at all, so this is not just a missing day: access is refused.
            raise SourceUnavailable(f"{unpublished} refused access (HTTP 403). Check VCD_SEC_USER_AGENT and "
                                    "SEC's access rules (https://www.sec.gov/os/accessing-edgar-data).")
        items: list[FormDItem] = []
        for row in rows:
            if len(items) >= self.max_filings:
                break
            if self.skip_accession(row["accession_number"]):
                continue
            resp = client.get(row["document_url"])
            items.append(parse_form_d_xml(resp.content, row))
        return items
