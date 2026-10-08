from datetime import timedelta

import pytest
from sqlalchemy import select

from tests.test_pipeline import ingest, news
from vcdiscovery import db
from vcdiscovery.models import ScoreOverride, Startup, utcnow
from vcdiscovery.scoring import load_config, save_weights, score_startup, validate_weights


def config(settings):
    with db.session_scope() as s:
        return load_config(s, settings.load_json(settings.scoring_file))


def score_of(settings, name):
    with db.session_scope() as s:
        st = s.scalar(select(Startup).where(Startup.name == name))
        result = score_startup(s, st, config(settings))
        return {f["factor"]: f for f in result.factors}, result


def test_unscorable_factors_are_listed_not_invented(settings):
    ingest(settings, [news("Acme Robotics raises $12M Series A led by Example Ventures", "https://a.example/1",
                           when=utcnow() - timedelta(days=5))])
    factors, result = score_of(settings, "Acme Robotics")
    assert factors["product_differentiation"]["score"] is None
    assert factors["product_differentiation"]["status"] == "unscorable"
    assert factors["financial_evidence"]["score"] is None  # pre-revenue is not scored as zero
    assert factors["market_opportunity"]["score"] is None  # not enough market data in the database
    assert factors["funding_validation"]["score"] == 55  # single-source report 45 + named lead 10
    assert {m["factor"] for m in result.missing} >= {"product_differentiation", "financial_evidence", "market_opportunity"}
    assert result.coverage < 0.5 and result.rating == "Insufficient evidence"
    assert "not an investment recommendation" in result.thesis


def test_media_volume_is_not_rewarded(settings):
    when = utcnow() - timedelta(days=3)
    ingest(settings, [news("Quiet Co raises $2M seed", "https://a.example/q", when=when)])
    ingest(settings, [news("Loud Co raises $2M seed", "https://a.example/l", when=when)])
    ingest(settings, [news("Quiet Co partners with Example Bank", "https://a.example/q2", when=when)])
    ingest(settings, [news(f"Loud Co partners with Example Bank, story {i}", f"https://outlet{i}.example/l",
                           publisher=f"Outlet {i}", when=when) for i in range(10)])
    quiet, _ = score_of(settings, "Quiet Co")
    loud, _ = score_of(settings, "Loud Co")
    for factor in ("business_traction", "growth_momentum", "funding_validation"):
        assert quiet[factor]["score"] == loud[factor]["score"], factor


def test_rumour_only_funding_scores_low_and_is_a_risk(settings):
    ingest(settings, [news("Orbital reportedly in talks to raise $50M", "https://a.example/r", when=utcnow())])
    factors, result = score_of(settings, "Orbital")
    assert factors["funding_validation"]["score"] == 15
    assert any("rumoured" in r for r in result.risks)


def test_overrides_persist_and_weights_are_customisable(settings):
    ingest(settings, [news("Acme Robotics raises $12M Series A", "https://a.example/1", when=utcnow())])
    with db.session_scope() as s:
        st = s.scalar(select(Startup))
        s.add(ScoreOverride(startup_id=st.id, factor="product_differentiation", score=80, note="Two granted patents", analyst="me"))
    factors, first = score_of(settings, "Acme Robotics")
    assert factors["product_differentiation"]["status"] == "analyst_override"
    assert factors["product_differentiation"]["score"] == 80
    with db.session_scope() as s:
        weights = {k: 0 for k in first.weights}
        weights.update(product_differentiation=50, funding_validation=50)
        save_weights(s, weights)
    _, second = score_of(settings, "Acme Robotics")
    assert second.weights["product_differentiation"] == 50
    assert second.total_score == round((80 * 50 + 45 * 50) / 100, 1)
    assert second.coverage == 1.0


def test_invalid_weights_rejected():
    with pytest.raises(ValueError, match="add up to 100"):
        validate_weights({"market_opportunity": 50})
    with pytest.raises(ValueError, match="Unknown"):
        validate_weights({"vibes": 100})
