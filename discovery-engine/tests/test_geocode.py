"""Map locations: stated company cities looked up on OpenStreetMap Nominatim, cached in the database."""
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import select

from tests.conftest import make_client
from vcdiscovery import db
from vcdiscovery.geocode import API, normalize_place, startup_place, write_places
from vcdiscovery.models import GeocodeCache, Startup, utcnow

PLACES = {
    "san francisco, ca, usa": {"lat": "37.7792588", "lon": "-122.4193286", "addresstype": "city", "name": "San Francisco",
                               "address": {"city": "San Francisco", "state": "California", "country": "United States"}},
    "paris": {"lat": "48.8534951", "lon": "2.3483915", "addresstype": "city", "name": "Paris",
              "address": {"city": "Paris", "country": "France"}},
    "california": {"lat": "36.7", "lon": "-118.7", "addresstype": "state", "name": "California", "address": {}},
}


def nominatim(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        q = {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}
        calls.append(q["q"])
        assert q["format"] == "jsonv2" and q["limit"] == "1"
        hit = PLACES.get(q["q"])
        return httpx.Response(200, json=[hit] if hit else [])
    return {API: handler}


def add(name, city=None, state=None, country=None):
    with db.session_scope() as s:
        st = Startup(name=name, normalized_name=name.lower(), hq_city=city, hq_state=state, hq_country=country)
        s.add(st)
        s.flush()
        return st.id


def market_file(tmp_path, companies):
    path = tmp_path / "market.json"
    path.write_text(json.dumps({"companies": companies}))
    return path


def test_place_text_is_cleaned():
    assert normalize_place("San Francisco, CA, USA; Remote") == "san francisco, ca, usa"
    assert normalize_place("  London  ") == "london"
    assert normalize_place("Remote") is None and normalize_place("") is None and normalize_place(None) is None
    assert startup_place(Startup(name="x", hq_city="San Francisco", hq_state="CA")) == "san francisco, ca, usa"
    assert startup_place(Startup(name="x", hq_state="CA", hq_country="United States")) is None  # a city is required


def test_cities_are_placed_and_states_or_unknown_places_are_not(settings, tmp_path):
    sf = add("Acme", "San Francisco", "CA")
    add("Statewide", "California")  # a "city" that is really a state is not a city-level location
    add("Nowhere Inc", "Atlantis")
    add("No Location")
    calls = []
    out = write_places(db.SessionLocal(), make_client(nominatim(calls)),
                       market_file(tmp_path, [{"slug": "nova", "location": "Paris"}, {"slug": "remote-co", "location": "Remote"}]),
                       tmp_path / "places.json")
    assert out["discovery"] == {str(sf): {"lat": 37.7793, "lon": -122.4193, "place": "San Francisco, United States",
                                          "country": "United States"}}
    assert out["market"] == {"nova": {"lat": 48.8535, "lon": 2.3484, "place": "Paris, France", "country": "France"}}
    assert sorted(calls) == ["atlantis", "california", "paris", "san francisco, ca, usa"]
    assert json.loads((tmp_path / "places.json").read_text())["attribution"].startswith("Locations © OpenStreetMap")


def test_lookups_are_cached_capped_and_retried_after_90_days(settings, tmp_path):
    add("Acme", "San Francisco", "CA")
    add("Nowhere Inc", "Atlantis")
    calls = []
    write_places(db.SessionLocal(), make_client(nominatim(calls)), None, tmp_path / "p.json")
    write_places(db.SessionLocal(), make_client(nominatim(calls)), None, tmp_path / "p.json")
    assert len(calls) == 2  # second run uses the cache
    with db.session_scope() as s:
        s.get(GeocodeCache, "atlantis").looked_up_at = utcnow() - timedelta(days=91)
    write_places(db.SessionLocal(), make_client(nominatim(calls)), None, tmp_path / "p.json", max_new=0)
    assert len(calls) == 2  # max_new=0: cache only
    write_places(db.SessionLocal(), make_client(nominatim(calls)), None, tmp_path / "p.json")
    assert calls[-1] == "atlantis"  # the not-found place is retried once it is 90 days old


def test_nominatim_failure_keeps_what_was_found(settings, tmp_path):
    add("Acme", "San Francisco", "CA")
    write_places(db.SessionLocal(), make_client(nominatim([])), None, tmp_path / "p.json")
    add("Nova", "Paris")
    out = write_places(db.SessionLocal(), make_client({API: 503}), None, tmp_path / "p.json")
    assert len(out["discovery"]) == 1  # Paris could not be looked up; San Francisco still comes from the cache
    with db.session_scope() as s:
        assert s.scalar(select(GeocodeCache).where(GeocodeCache.query == "paris")) is None


def test_street_addresses_are_reduced_to_the_city():
    assert normalize_place("200 Berkeley Street, 18th floor, Boston, MA 02116") == "boston, ma"
    assert normalize_place("1875 South Grant Street, Suite 550, San Mateo, CA 94402, USA") == "san mateo, ca, usa"
    assert normalize_place("114 Yigal Alon Street, Tel Aviv, Israel") == "tel aviv, israel"
    assert normalize_place("73 Spring St, Floor 3A, New York, NY 10012") == "new york, ny"
    assert normalize_place("Toronto, ON M5V 2T6") == "toronto, on"
    assert normalize_place("Stockholm") == "stockholm"  # plain places are unchanged
    assert normalize_place("St. Louis, MO") == "st. louis, mo"
