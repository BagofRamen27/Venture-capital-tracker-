"""Small, dependency-free text helpers: URL cleanup, company-name normalisation, money parsing."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "guccounter", "cmpid", "ncid", "sr_share"}

# Hosts shared by many unrelated projects; a link to them does not identify a company.
SHARED_HOSTS = {
    "github.com", "gitlab.com", "bitbucket.org", "github.io", "youtube.com", "youtu.be", "medium.com",
    "substack.com", "twitter.com", "x.com", "linkedin.com", "facebook.com", "instagram.com",
    "apps.apple.com", "play.google.com", "google.com", "docs.google.com", "producthunt.com",
    "news.ycombinator.com", "ycombinator.com", "reddit.com", "notion.site", "notion.so", "vercel.app",
    "netlify.app", "herokuapp.com", "pages.dev", "itch.io", "huggingface.co", "arxiv.org",
    "techcrunch.com", "wikipedia.org", "dropbox.com", "loom.com", "figma.com", "chrome.google.com",
    "npmjs.com", "pypi.org", "crates.io", "fly.dev", "replit.app", "web.app", "firebaseapp.com",
}
TWO_LEVEL_TLDS = {"co.uk", "org.uk", "ac.uk", "com.au", "co.in", "co.jp", "com.br", "co.nz", "com.sg", "co.za", "com.mx", "co.il", "com.cn", "com.tr"}

LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "l l c", "ltd", "limited", "corp", "corporation", "co", "company",
    "gmbh", "sa", "sas", "sarl", "bv", "nv", "ab", "as", "oy", "plc", "pbc", "lp", "llp", "srl", "spa",
    "ag", "pte", "pty", "kk", "sl", "sro", "ug",
}


def utc_date_str(dt) -> str | None:
    return dt.isoformat() if dt else None


def canonical_url(url: str | None) -> str | None:
    """Normalise a URL so the same article is recognised under different links."""
    if not url:
        return None
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def host_of(url: str | None) -> str | None:
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host or None


def registrable_domain(url: str | None) -> str | None:
    """`https://app.acme.co.uk/x` -> `acme.co.uk`."""
    host = host_of(url)
    if not host or re.fullmatch(r"[\d.]+", host):
        return None
    labels = host.split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in TWO_LEVEL_TLDS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def is_shared_host(url: str | None) -> bool:
    host = host_of(url)
    if not host:
        return True
    return any(host == h or host.endswith("." + h) for h in SHARED_HOSTS)


def company_domain(url: str | None) -> str | None:
    """Domain that can identify a company, or None for shared hosting / social sites."""
    if not url or is_shared_host(url):
        return None
    return registrable_domain(url)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_company_name(name: str | None) -> str:
    """Lower-case, strip punctuation and legal suffixes: 'Acme Robotics, Inc.' -> 'acme robotics'.
    Distinct brand words (AI, Labs, Health) are kept, so 'Acme AI' != 'Acme'."""
    if not name:
        return ""
    text = strip_accents(name).lower()
    text = re.split(r"\b(?:d/b/a|dba|f/k/a|fka)\b", text)[0]
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    tokens = text.split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    if len(tokens) > 1 and tokens[0] == "the":
        tokens = tokens[1:]
    return " ".join(tokens)


def display_name(name: str) -> str:
    """SEC names are often ALL CAPS; make them readable without changing the legal name."""
    name = " ".join(name.split())
    if not name.isupper():
        return name
    keep_upper = {"LLC", "LP", "LLP", "PBC", "PLC", "AI", "II", "III", "IV", "USA", "US", "UK", "AG", "SA", "AB", "BV", "NV"}
    return " ".join(w if w.strip(",.") in keep_upper else w.capitalize() for w in name.split(" "))


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_company_name(a), normalize_company_name(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


STOPWORDS = {"a", "an", "the", "to", "of", "for", "in", "on", "and", "with", "its", "as", "at", "by", "from", "new"}


def title_fingerprint(title: str) -> str:
    """Same headline syndicated across sites -> same fingerprint."""
    tokens = [t for t in re.sub(r"[^a-z0-9$€£ ]+", " ", strip_accents(title).lower()).split() if t not in STOPWORDS]
    return hashlib.sha1(" ".join(tokens).encode()).hexdigest()


CURRENCY_SYMBOLS = [
    ("US$", "USD"), ("USD", "USD"), ("C$", "CAD"), ("CA$", "CAD"), ("A$", "AUD"), ("S$", "SGD"),
    ("$", "USD"), ("€", "EUR"), ("EUR", "EUR"), ("£", "GBP"), ("GBP", "GBP"), ("CHF", "CHF"), ("₹", "INR"),
]
MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "mm": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
}
MONEY_RE = re.compile(
    r"(?P<cur>US\$|USD\s?|CA\$|C\$|A\$|S\$|\$|€|EUR\s?|£|GBP\s?|CHF\s?|₹)\s?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<mult>million|billion|thousand|mn|bn|mm|m|b|k)?\b",
    re.IGNORECASE,
)


def parse_money(text: str | None) -> tuple[float, str, str] | None:
    """Return (amount, currency, original_text) for the first money expression, else None."""
    if not text:
        return None
    m = MONEY_RE.search(text)
    if not m:
        return None
    raw_cur = m.group("cur").strip().upper()
    currency = next((code for sym, code in CURRENCY_SYMBOLS if raw_cur == sym.upper()), "USD")
    amount = float(m.group("num").replace(",", ""))
    mult = (m.group("mult") or "").lower()
    amount *= MULTIPLIERS.get(mult, 1.0)
    return amount, currency, m.group(0).strip()


def parse_amount(value) -> float | None:
    """Parse plain numbers like '1,235,000' or 1235000. Returns None for blanks/'Indefinite'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("$", "")
    try:
        return float(text) if text else None
    except ValueError:
        return None


def short(text: str | None, limit: int = 500) -> str | None:
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"
