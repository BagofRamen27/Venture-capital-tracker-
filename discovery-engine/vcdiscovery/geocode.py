"""Coordinates for the website's map: each company's stated city, looked up on OpenStreetMap Nominatim.

Rules:
* only a location the company record already states is looked up; nothing is guessed or invented;
* a result counts only when it is a city, town or similar settlement, so a bare country or state, or a
  street-level match, never places a pin;
* every place is looked up once and cached in the database (`geocode_cache`); places not found are
  retried after 90 days;
* Nominatim's usage policy is followed: one request per second at most, an identifying User-Agent,
  cached results and a capped number of new lookups per run (https://operations.osmfoundation.org/policies/nominatim/).

Output: `places.json` for the website, mapping discovered company ids and StartupDB slugs to coordinates.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .http import PoliteClient
from .models import GeocodeCache, Startup, utcnow

API = "https://nominatim.openstreetmap.org/search"
ATTRIBUTION = "Locations © OpenStreetMap contributors (Nominatim, ODbL)"
RETRY_AFTER = timedelta(days=90)
SETTLEMENTS = {"city", "town", "village", "hamlet", "municipality", "suburb", "borough", "city_district", "quarter",
               "neighbourhood"}
# Street-address parts ("200 Berkeley Street", "Suite 550", "18th floor") are dropped so only the city is looked up.
# A street address always carries a number; "St. Louis" or "Fort Worth" do not.
STREET = re.compile(r"\d|\b(suite|floor|unit|building)\b", re.I)
POSTCODE = re.compile(r"\b(\d{5}(-\d{4})?|[a-z]\d[a-z] ?\d[a-z]\d)\b", re.I)  # US ZIP / Canadian postcode
US_STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
                "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR".split())


def normalize_place(text: str | None) -> str | None:
    """Clean a free-text location ("San Francisco, CA, USA; Remote") into a lookup query, or None."""
    first = re.split(r"[;|/]", text or "")[0]
    parts = [" ".join(POSTCODE.sub("", p).split()) for p in first.split(",")]  # "MA 02116" -> "MA"
    parts = [p for p in parts if p and not STREET.search(p) and p.lower() not in ("remote", "global", "worldwide")]
    query = ", ".join(parts)
    return query.lower()[:300] if parts else None


def startup_place(s: Startup) -> str | None:
    """The lookup query for a discovered company; a city is required."""
    if not s.hq_city:
        return None
    country = s.hq_country or ("USA" if (s.hq_state or "").upper() in US_STATES else None)
    return normalize_place(", ".join(p for p in (s.hq_city, s.hq_state, country) if p))


def lookup(client: PoliteClient, query: str) -> dict:
    """One Nominatim search; returns the cache fields for `query`."""
    results = client.get(API, params={"q": query, "format": "jsonv2", "limit": "1", "addressdetails": "1",
                                      "accept-language": "en"}).json()
    hit = results[0] if results else None
    if not hit or hit.get("addresstype") not in SETTLEMENTS:
        return {"status": "not_found", "lat": None, "lon": None, "place": None, "country": None}
    address = hit.get("address") or {}
    name = next((address[k] for k in ("city", "town", "village", "hamlet", "municipality", "suburb") if address.get(k)),
                hit.get("name") or query)
    country = address.get("country")
    return {"status": "found", "lat": round(float(hit["lat"]), 4), "lon": round(float(hit["lon"]), 4),
            "place": ", ".join(p for p in (name, country) if p), "country": country}


def geocode_queries(session: Session, client: PoliteClient, queries: set[str], max_new: int = 60) -> dict[str, GeocodeCache]:
    """Return cached rows for `queries`, looking up at most `max_new` that are missing or due for a retry."""
    rows = {r.query: r for r in session.scalars(select(GeocodeCache).where(GeocodeCache.query.in_(queries)))}
    due = sorted(q for q in queries if q not in rows or (
        rows[q].status == "not_found" and rows[q].looked_up_at < utcnow() - RETRY_AFTER))
    for query in due[:max_new]:
        try:
            fields = lookup(client, query)
        except Exception as exc:  # Nominatim unavailable: keep what is cached, try the rest next run
            print(f"::warning::Map geocoding stopped early: {exc}")
            break
        row = rows.get(query) or GeocodeCache(query=query)
        for key, value in {**fields, "looked_up_at": utcnow()}.items():
            setattr(row, key, value)
        session.add(row)
        session.commit()  # keep what was found even if a later lookup fails
        rows[query] = row
    return rows


def build_places(session: Session, client: PoliteClient, market_file: str | Path | None, max_new: int = 60) -> dict:
    """Look up the stated locations of discovered and StartupDB companies; return the places.json content."""
    wanted: dict[tuple[str, str], str] = {}
    for s in session.scalars(select(Startup).where(Startup.is_demo.is_(False), Startup.review_status != "Archived")):
        if query := startup_place(s):
            wanted[("discovery", str(s.id))] = query
    if market_file and Path(market_file).exists():
        for c in json.loads(Path(market_file).read_text(encoding="utf-8")).get("companies", []):
            if c.get("slug") and (query := normalize_place(c.get("location"))):
                wanted[("market", c["slug"])] = query
    rows = geocode_queries(session, client, set(wanted.values()), max_new)
    out: dict = {"generated_at": utcnow().isoformat(), "attribution": ATTRIBUTION, "precision": "city",
                 "discovery": {}, "market": {}}
    for (kind, key), query in sorted(wanted.items()):
        row = rows.get(query)
        if row and row.status == "found":
            out[kind][key] = {"lat": row.lat, "lon": row.lon, "place": row.place, "country": row.country}
    return out


def write_places(session: Session, client: PoliteClient, market_file: str | Path | None, out_file: str | Path,
                 max_new: int = 60) -> dict:
    data = build_places(session, client, market_file, max_new)
    path = Path(out_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return data
