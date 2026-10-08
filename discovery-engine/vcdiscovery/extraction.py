"""Turn headlines into structured company / funding facts with transparent rules.

The extractor is deliberately conservative: when a headline does not clearly name one company
and one amount, it returns None rather than guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import parse_money

RUMOR_MARKERS = [
    r"reportedly", r"in talks", r"is said to", r"said to be", r"sources say", r"rumou?red", r"according to (?:people|sources)",
    r"people familiar", r"\beyes\b", r"\bmulls\b", r"considering", r"in discussions",
]
TARGET_MARKERS = [
    r"aims to raise", r"seeks?\b", r"seeking", r"looking to raise", r"looks to raise", r"plans to raise", r"set to raise",
    r"targets?\b", r"wants to raise", r"hopes to raise", r"launches .{0,30}(?:crowdfunding|campaign)", r"opens .{0,20}round",
]

VERB = (
    r"(?:reportedly\s+)?(?:raises|raised|secures|secured|lands|landed|closes|closed|bags|nabs|snags|grabs|picks up|scores|nets|"
    r"gets|announces|completes|receives|collects|pulls in|hauls in|is raising|in talks to raise|seeks|aims to raise|"
    r"looks to raise|plans to raise|eyes|mulls)"
)
HEADLINE_RE = re.compile(
    rf"^(?P<subject>.{{2,90}}?)\s+{VERB}\b(?P<rest>.*)$", re.IGNORECASE
)
LABEL_PREFIX_RE = re.compile(r"^\s*(?:exclusive|breaking|funding|report|scoop|update|deal|news)\s*[:\-–—|]\s*", re.IGNORECASE)
BASED_RE = re.compile(r"^(?P<loc>[A-Z][\w.' ]{1,40}?)-based\s+", re.UNICODE)
DESCRIPTOR_RE = re.compile(
    r"^(?P<desc>(?:[\w\-/&']+\s){0,4}?(?:startup|start-up|company|platform|maker|developer|provider|firm|unicorn|scaleup|"
    r"scale-up|spinout|spin-off|fintech|insurtech|healthtech|medtech|biotech|edtech|proptech|legaltech|cleantech|"
    r"climate tech|deeptech|agtech|foodtech|regtech|govtech|defense tech|defence tech|SaaS))\s+(?P<name>.+)$",
    re.IGNORECASE,
)
ROUND_RE = re.compile(
    r"\b(pre-?seed|seed|series\s+[a-h](?:\+|\s?extension|\s?-?\s?[12])?|growth equity|growth|bridge|venture debt|debt|angel|"
    r"strategic|convertible note|safe|grant|crowdfunding|reg cf|reg a\+?)\b",
    re.IGNORECASE,
)
INVESTOR_RE = re.compile(
    r"(?P<kind>co-led by|led by|backed by|from|with participation from|participation from|investors including)\s+"
    r"(?P<names>[A-Z0-9][^.;:()]{2,200}?)(?=\s+(?:to|for|as|at|in order|with|alongside|amid|after)\b|[.;:(]|$)",
)
BAD_NAME_STARTS = {
    "how", "why", "what", "when", "where", "who", "these", "this", "here", "here's", "startups", "investors", "vcs",
    "report", "weekly", "top", "the week", "funding", "a", "an", "our", "my", "we", "i", "it", "they", "every",
    "all", "some", "many", "most", "another", "one", "two", "three", "former", "ex",
}
INDUSTRY_HINTS = {
    "ai": "Artificial Intelligence", "artificial intelligence": "Artificial Intelligence", "genai": "Artificial Intelligence",
    "fintech": "Fintech", "payments": "Fintech", "insurtech": "Fintech", "regtech": "Fintech", "banking": "Fintech",
    "cybersecurity": "Cybersecurity", "security": "Cybersecurity", "biotech": "Biotechnology", "drug": "Biotechnology",
    "healthtech": "Healthcare Technology", "medtech": "Healthcare Technology", "health": "Healthcare Technology",
    "climate": "Climate Technology", "cleantech": "Climate Technology", "energy": "Climate Technology", "battery": "Climate Technology",
    "defense": "Defense Technology", "defence": "Defense Technology", "drone": "Defense Technology",
    "saas": "Enterprise Software", "software": "Enterprise Software", "devtools": "Enterprise Software", "developer": "Enterprise Software",
    "infrastructure": "Infrastructure", "data": "Enterprise Software", "robotics": "Robotics", "chip": "Semiconductors",
    "semiconductor": "Semiconductors", "edtech": "Education Technology", "proptech": "Real Estate Technology",
    "legaltech": "Legal Technology", "agtech": "Agriculture Technology", "foodtech": "Food Technology",
    "consumer": "Consumer Technology", "ecommerce": "Consumer Technology", "e-commerce": "Consumer Technology",
    "space": "Space Technology", "quantum": "Quantum Computing", "crypto": "Crypto / Web3", "web3": "Crypto / Web3",
}


@dataclass
class FundingExtraction:
    company_name: str
    amount: float | None
    currency: str | None
    amount_text: str | None
    round_type: str | None
    evidence_status: str
    investors: list[str] = field(default_factory=list)
    lead_investors: list[str] = field(default_factory=list)
    location_hint: str | None = None
    industry_hint: str | None = None
    descriptor: str | None = None
    rule: str = ""


def normalize_round(raw: str | None) -> str | None:
    if not raw:
        return None
    r = " ".join(raw.lower().replace("-", " ").split())
    if r.startswith("pre seed") or r == "preseed":
        return "Pre-seed"
    if r.startswith("series"):
        letter = r.split()[1][0].upper()
        return f"Series {letter}"
    mapping = {
        "seed": "Seed", "growth": "Growth", "growth equity": "Growth", "bridge": "Bridge", "venture debt": "Debt",
        "debt": "Debt", "angel": "Angel", "strategic": "Strategic", "convertible note": "Convertible note",
        "safe": "SAFE", "grant": "Grant", "crowdfunding": "Crowdfunding", "reg cf": "Reg CF", "reg a": "Reg A+", "reg a+": "Reg A+",
    }
    return mapping.get(r, raw.title())


def industry_from_text(*texts: str | None) -> str | None:
    joined = " ".join(t for t in texts if t).lower()
    for word, industry in INDUSTRY_HINTS.items():
        if re.search(rf"\b{re.escape(word)}\b", joined):
            return industry
    return None


def evidence_status_for(text: str, source_type: str) -> str:
    lowered = text.lower()
    if any(re.search(p, lowered) for p in RUMOR_MARKERS):
        return "rumor"
    if any(re.search(p, lowered) for p in TARGET_MARKERS):
        return "target"
    return "company_announced" if source_type == "press_release" else "reported"


def _clean_subject(subject: str) -> tuple[str | None, str | None, str | None]:
    """Return (company_name, location_hint, descriptor)."""
    subject = LABEL_PREFIX_RE.sub("", subject).strip(" \"'“”‘’")
    location = None
    m = BASED_RE.match(subject)
    if m:
        location = m.group("loc").strip()
        subject = subject[m.end():]
    descriptor = None
    for _ in range(3):  # "climate tech startup Acme" needs two passes
        m = DESCRIPTOR_RE.match(subject)
        if not m or len(m.group("name").split()) > 6 or not _plausible_descriptor(m.group("desc")):
            break
        descriptor = f"{descriptor} {m.group('desc')}" if descriptor else m.group("desc")
        subject = m.group("name")
    # "Acme, the AI startup," / "Acme (YC S24)"
    subject = re.split(r",|\s\(|\s[-–—]\s", subject)[0].strip(" \"'“”‘’")
    # Drop a leading lower-case industry word left over: "fintech Qonto" -> "Qonto"
    words = subject.split()
    while len(words) > 1 and words[0].lower() in INDUSTRY_HINTS and words[0][0].islower():
        descriptor = (descriptor + " " if descriptor else "") + words.pop(0)
    subject = " ".join(words)
    if not _valid_company_name(subject):
        return None, location, descriptor
    return subject, location, descriptor


GENERIC_NOUNS = {"startup", "start-up", "company", "platform", "maker", "developer", "provider", "firm", "unicorn",
                 "scaleup", "scale-up", "spinout", "spin-off"}


def _plausible_descriptor(desc: str) -> bool:
    """'Platform Science' is a company name, 'AI platform' / 'startup' are descriptors."""
    words = desc.split()
    keyword = words[-1]
    if keyword.lower() not in GENERIC_NOUNS:
        return True  # industry words such as 'fintech' are descriptors
    return len(words) > 1 or keyword.islower()


def _valid_company_name(name: str) -> bool:
    if not name or len(name) > 60:
        return False
    words = name.split()
    if not 1 <= len(words) <= 5:
        return False
    if words[0].lower().strip("'’") in BAD_NAME_STARTS or " ".join(words[:2]).lower() in BAD_NAME_STARTS:
        return False
    if not re.match(r"[A-Za-z0-9]", name):
        return False
    # Needs at least one capital letter or digit (brand-like), e.g. "dbt Labs" passes, "startup" fails.
    return any(c.isupper() or c.isdigit() for c in name)


def _split_names(chunk: str) -> list[str]:
    chunk = re.sub(r"\b(?:existing investors|others|other investors|and others|among others)\b", "", chunk, flags=re.IGNORECASE)
    parts = re.split(r",\s*|\s+and\s+|\s*&\s+(?=[A-Z])", chunk)
    names = []
    for p in parts:
        p = p.strip(" .'\"")
        p = re.sub(r"^(?:investors? (?:including|such as)|including)\s+", "", p, flags=re.IGNORECASE)
        if p and len(p.split()) <= 6 and p[0].isupper():
            names.append(p)
    return names


def extract_investors(text: str) -> tuple[list[str], list[str]]:
    """Return (all_investors, lead_investors) mentioned with explicit phrases like 'led by'."""
    investors: list[str] = []
    leads: list[str] = []
    for m in INVESTOR_RE.finditer(text or ""):
        names = _split_names(m.group("names"))
        kind = m.group("kind").lower()
        if kind == "from" and not re.search(r"\b(?:capital|ventures|partners|vc|fund|investments|labs|holdings|group)\b", m.group("names"), re.IGNORECASE):
            continue  # "from" is too generic unless the names look like investment firms
        for n in names:
            if n not in investors:
                investors.append(n)
            if "led by" in kind and n not in leads:
                leads.append(n)
    return investors, leads


def extract_funding(title: str, summary: str | None = None, source_type: str = "news") -> FundingExtraction | None:
    """Extract a funding event from a headline like 'Paris-based Acme raises €10M Series A led by Index'."""
    if not title:
        return None
    m = HEADLINE_RE.match(title.strip())
    if not m:
        return None
    name, location, descriptor = _clean_subject(m.group("subject"))
    if not name:
        return None
    rest = m.group("rest")
    money = parse_money(rest[:80])
    round_match = ROUND_RE.search(rest) or ROUND_RE.search(summary or "")
    if money is None and round_match is None:
        return None  # 'Acme lands new CEO' is not a funding event
    investors, leads = extract_investors(f"{title}. {(summary or '')[:500]}")
    full = f"{title} {summary or ''}"
    return FundingExtraction(
        company_name=name,
        amount=money[0] if money else None,
        currency=money[1] if money else None,
        amount_text=money[2] if money else None,
        round_type=normalize_round(round_match.group(1)) if round_match else None,
        evidence_status=evidence_status_for(title, source_type),
        investors=investors,
        lead_investors=leads,
        location_hint=location,
        industry_hint=industry_from_text(descriptor, title, summary),
        descriptor=descriptor,
        rule="headline: <company> <raise-verb> <amount/round>" + ("; summary used for round/investors" if summary else ""),
    ) if not _looks_like_roundup(full) else None


def _looks_like_roundup(text: str) -> bool:
    return bool(re.search(r"\b(?:roundup|round-up|this week in|weekly recap|biggest rounds|top \d+ )", text, re.IGNORECASE))


HN_TITLE_RE = re.compile(r"^(?P<kind>Show HN|Launch HN)\s*:\s*(?P<body>.+)$", re.IGNORECASE)
YC_BATCH_RE = re.compile(r"\(\s*YC\s+(?P<batch>[WSFX]\d{2}|(?:Winter|Summer|Fall|Spring)\s+\d{4})\s*\)", re.IGNORECASE)
SENTENCE_STARTS = {"i", "we", "my", "our", "a", "an", "the", "how", "what", "why", "built", "made", "open", "free", "simple", "tiny", "yet", "using"}


@dataclass
class HNExtraction:
    kind: str  # show_hn | launch_hn
    company_name: str | None
    tagline: str | None
    yc_batch: str | None


def extract_hn(title: str) -> HNExtraction | None:
    m = HN_TITLE_RE.match((title or "").strip())
    if not m:
        return None
    kind = "launch_hn" if m.group("kind").lower().startswith("launch") else "show_hn"
    body = m.group("body").strip()
    batch_m = YC_BATCH_RE.search(body)
    batch = batch_m.group("batch").upper() if batch_m else None
    body_wo_batch = YC_BATCH_RE.sub("", body).strip()
    parts = re.split(r"\s+[-–—]\s+|:\s+|\s+–|\s+—", body_wo_batch, maxsplit=1)
    candidate = parts[0].strip(" .")
    tagline = parts[1].strip() if len(parts) > 1 else None
    words = candidate.split()
    name = candidate
    if (
        not tagline
        or not 1 <= len(words) <= 4
        or words[0].lower() in SENTENCE_STARTS
        or not any(c.isupper() or c.isdigit() for c in candidate)
    ):
        name = None
    return HNExtraction(kind=kind, company_name=name, tagline=tagline, yc_batch=batch)
