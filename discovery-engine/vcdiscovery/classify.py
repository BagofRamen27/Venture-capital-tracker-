"""Explainable news classification: keyword rules for event type and tone.

Every label lists the exact words that triggered it, so a reviewer can check it.
Tone (sentiment) describes the wording of a story. It is NOT a measure of investment quality.
"""
from __future__ import annotations

import re

EVENT_RULES: dict[str, list[str]] = {
    "funding": [r"rais(?:es|ed|ing)", r"funding", r"seed round", r"series [a-h]\b", r"pre-?seed", r"secures? \$", r"investment from", r"backed by", r"closes? .{0,20}round"],
    "product_launch": [r"launch(?:es|ed)?", r"unveil(?:s|ed)?", r"introduc(?:es|ed)", r"debut(?:s|ed)?", r"show hn", r"launch hn", r"now available", r"general availability", r"releases?"],
    "partnership": [r"partner(?:s|ship|ed)? with", r"partnership", r"teams up", r"collaborat(?:es|ion)", r"alliance", r"integrat(?:es|ion) with"],
    "customer_adoption": [r"customers?", r"signs? (?:a )?(?:deal|contract)", r"selected by", r"deploy(?:s|ed|ment)", r"adopt(?:s|ed|ion)", r"pilot", r"wins? contract", r"users"],
    "leadership_change": [r"appoints?", r"names? .{0,30}(?:ceo|cfo|cto|coo|chief)", r"hires?", r"steps? down", r"resign(?:s|ed)", r"new (?:ceo|cfo|cto)", r"joins as"],
    "layoffs": [r"layoffs?", r"lays? off", r"job cuts", r"cuts? .{0,15}(?:staff|jobs|workforce)", r"downsiz", r"restructur"],
    "regulatory": [r"\bsec\b", r"\bfda\b", r"regulat(?:or|ory|ion)", r"approval", r"clearance", r"complian", r"license", r"fine[ds]?\b", r"probe", r"investigation"],
    "acquisition": [r"acquir(?:es|ed|ing)", r"acquisition", r"merg(?:es|er)", r"bought by", r"buys"],
    "legal": [r"lawsuit", r"sues?\b", r"sued", r"litigation", r"settle(?:s|ment)"],
    "grant": [r"\bgrant\b", r"\bsbir\b", r"\bsttr\b", r"\bdarpa\b", r"innovation award", r"government contract"],
    "accelerator": [r"\(yc [wsfx]\d{2}\)", r"y combinator", r"accelerator", r"techstars", r"joins .{0,20}cohort", r"demo day"],
    "shutdown": [r"shuts? down", r"shutting down", r"ceases? operations", r"bankrupt", r"insolven", r"wind(?:s|ing)? down"],
}

POSITIVE = [
    "raises", "secures", "launches", "partners", "growth", "grows", "record", "expands", "expansion", "wins", "award",
    "milestone", "profitable", "approval", "approved", "surge", "oversubscribed", "doubles", "triples", "selected", "breakthrough",
]
NEGATIVE = [
    "layoff", "layoffs", "lays off", "lawsuit", "sued", "fraud", "breach", "shuts down", "bankrupt", "decline", "declines",
    "losses", "probe", "investigation", "fined", "resigns", "steps down", "delay", "delayed", "recall", "outage", "cuts",
    "downsizing", "insolvency", "warning", "controversy", "struggles",
]

_EVENT_PATTERNS = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in EVENT_RULES.items()}


def classify_text(title: str, summary: str | None = None) -> dict:
    """Return {'event_types': [...], 'sentiment': str, 'sentiment_score': float, 'evidence': {...}}."""
    title = title or ""
    text = f"{title} {summary or ''}"
    evidence: dict[str, list[str]] = {}
    for event, patterns in _EVENT_PATTERNS.items():
        # Title matches are strong; summary-only matches need two distinct hits to avoid noise.
        title_hits = sorted({m.group(0).lower() for p in patterns for m in p.finditer(title)})
        all_hits = sorted({m.group(0).lower() for p in patterns for m in p.finditer(text)})
        if title_hits or len(all_hits) >= 2:
            evidence[event] = all_hits
    lowered = f" {text.lower()} "
    pos = [w for w in POSITIVE if re.search(rf"\b{re.escape(w)}\b", lowered)]
    neg = [w for w in NEGATIVE if re.search(rf"\b{re.escape(w)}\b", lowered)]
    total = len(pos) + len(neg)
    score = 0.0 if total == 0 else round((len(pos) - len(neg)) / total, 2)
    sentiment = "neutral" if total == 0 or abs(score) < 0.2 else ("positive" if score > 0 else "negative")
    if pos and neg and abs(score) < 0.5:
        sentiment = "mixed"
    return {
        "event_types": sorted(evidence),
        "sentiment": sentiment,
        "sentiment_score": score,
        "evidence": {"events": evidence, "positive_terms": pos, "negative_terms": neg,
                     "method": "keyword rules v1 (title matches, or 2+ summary matches)"},
    }
