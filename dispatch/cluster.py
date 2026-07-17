"""
Deduplication: canonical URLs, normalized titles, fuzzy cluster matching.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz

from .defaults import CATEGORY_KEYWORDS

# Query params that identify a campaign, not a document.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_reader", "utm_brand", "utm_social",
    "fbclid", "gclid", "dclid", "msclkid", "twclid", "igshid", "mc_cid",
    "mc_eid", "ref", "referrer", "source", "src", "cmp", "campaign",
    "spm", "scid", "yclid", "_hsenc", "_hsmi", "hsCtaTracking", "at_medium",
    "at_campaign", "guccounter", "amp", "sh",
}

# Outlet noise that shows up glued onto headlines.
TITLE_PREFIXES = re.compile(
    r"^\s*(?:breaking|exclusive|update|updated|report|news|alert|psa|advisory)\s*[:\-–—]\s*",
    re.IGNORECASE,
)
TITLE_SUFFIXES = re.compile(
    r"\s*[\|\-–—]\s*(?:bleepingcomputer|the hacker news|krebs on security|the record|"
    r"ars technica|securityweek|dark reading|help net security|threatpost|infosecurity"
    r"(?: magazine)?|cyberscoop|the register|zdnet|scmagazine|sc media)\s*$",
    re.IGNORECASE,
)

STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "to", "and", "or", "is", "are",
    "was", "were", "be", "been", "as", "at", "by", "with", "from", "that",
    "this", "it", "its", "into", "after", "over", "amid", "says", "said",
    "new", "now", "how", "why", "what", "more", "than", "but", "has", "have",
    "can", "will", "may", "could", "would", "about", "up", "out", "via",
}

CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)

# WordPress truncates excerpts with "[...]" and most security outlets run
# WordPress. Twelve of fifteen BleepingComputer summaries carry one. Pasted
# into a post it reads like the poster forgot to finish the sentence.
CONTINUATION_RE = re.compile(
    r"\s*\[\s*(?:\.\.\.|\u2026|&hellip;|read\s+more|continue\s+reading|more)\s*\]\s*$",
    re.IGNORECASE,
)
TRAILING_READMORE_RE = re.compile(
    r"\s*(?:\u2026|\.\.\.)?\s*(?:\[?\s*(?:read\s+more|continue\s+reading|read\s+the\s+rest)"
    r"(?:\s*(?:\u2192|->|&raquo;|\u00bb))?\s*\]?)\s*$",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^\w\s]")

HTML_ENTITIES = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'",
    "&apos;": "'", "&nbsp;": " ", "&hellip;": "...", "&mdash;": "-",
    "&ndash;": "-", "&rsquo;": "'", "&lsquo;": "'", "&ldquo;": '"',
    "&rdquo;": '"', "&#8217;": "'", "&#8216;": "'", "&#8220;": '"',
    "&#8221;": '"', "&#8211;": "-", "&#8212;": "-", "&#160;": " ",
}


def strip_html(text: str) -> str:
    """Turn feed HTML into readable plain text."""
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = TAG_RE.sub("", text)
    for entity, char in HTML_ENTITIES.items():
        text = text.replace(entity, char)
    text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_tracking(parts) -> Tuple[str, str, str]:
    """Shared cleanup: returns (host, path, query) with campaign junk removed."""
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host.endswith(":80") or host.endswith(":443"):
        host = host.rsplit(":", 1)[0]

    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS
    ]
    query.sort()

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    if path.endswith("/amp"):
        path = path[:-4] or "/"

    return host, path, urlencode(query)


def strip_continuation(text: str) -> str:
    """
    Drop the "[...]" an outlet's CMS bolts onto a truncated excerpt.

    Only tidies punctuation when a marker actually came off. Stripping trailing
    dots unconditionally would quietly eat the full stop from every summary that
    was already fine.
    """
    if not text:
        return ""

    out = text.rstrip()
    changed = False
    for _ in range(2):
        for pattern in (CONTINUATION_RE, TRAILING_READMORE_RE):
            trimmed = pattern.sub("", out).rstrip()
            if trimmed != out:
                changed = True
                out = trimmed
    if not changed:
        return out

    while out and out[-1] in " \u2026,;:-":
        out = out[:-1]
    if out.endswith("..."):
        out = out[:-3].rstrip()
    if out and out[-1] not in ".!?":
        out += "."
    return out or text.strip()


def canonical_url(url: str) -> str:
    """
    Dedup key. Aggressive on purpose: forces https so an http and an https
    copy of the same article collapse together. Do not paste this one, use
    display_url instead.
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()

    scheme = "https" if parts.scheme in ("http", "https", "") else parts.scheme
    host, path, query = _strip_tracking(parts)
    return urlunsplit((scheme, host, path, query, ""))


def display_url(url: str) -> str:
    """
    The link you actually paste. Drops utm/fbclid noise but keeps the scheme
    the outlet published, so an http-only host still resolves.
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()

    if parts.scheme not in ("http", "https", ""):
        return url.strip()

    scheme = parts.scheme or "https"
    host, path, query = _strip_tracking(parts)
    if not host:
        return url.strip()
    return urlunsplit((scheme, host, path, query, ""))


def clean_title(title: str) -> str:
    """Human-readable title with outlet decoration removed."""
    title = strip_html(title or "")
    title = TITLE_SUFFIXES.sub("", title)
    title = TITLE_PREFIXES.sub("", title)
    return WS_RE.sub(" ", title).strip()


def normalize_title(title: str) -> str:
    """Comparison key: lowercase, no punctuation, no stopwords."""
    title = clean_title(title).lower()
    title = PUNCT_RE.sub(" ", title)
    words = [w for w in title.split() if w and w not in STOPWORDS]
    return " ".join(words)


def extract_cves(*texts: str) -> List[str]:
    """CVE IDs in first-seen order, uppercased and deduped."""
    seen: List[str] = []
    for text in texts:
        if not text:
            continue
        for match in CVE_RE.findall(text):
            cve = match.upper()
            if cve not in seen:
                seen.append(cve)
    return seen


def guess_category(title: str, summary: str = "") -> str:
    """Keyword scoring. Title hits count double."""
    title_l = (title or "").lower()
    summary_l = (summary or "")[:1200].lower()

    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in title_l:
                score += 2
            if keyword in summary_l:
                score += 1
        if score:
            scores[category] = score

    if not scores:
        return "other"
    best = max(scores.items(), key=lambda kv: (kv[1], -list(CATEGORY_KEYWORDS).index(kv[0])))
    return best[0]


def title_similarity(a: str, b: str) -> float:
    """
    Blended score for two normalized titles, 0-100.

    token_set_ratio alone returns 100 whenever one headline's words are a
    subset of the other's, which merges "Apple patches WebKit bug" into
    "Apple patches WebKit bug exploited against journalists in Europe" but
    also merges plenty of unrelated short headlines. Mixing in token_sort_ratio
    pulls the score back down when one title carries a lot of extra content.
    """
    tset = fuzz.token_set_ratio(a, b)
    tsort = fuzz.token_sort_ratio(a, b)
    return 0.55 * tset + 0.45 * tsort


def shared_tokens(a: str, b: str) -> int:
    return len(set(a.split()) & set(b.split()))


def match_cluster(
    norm_title: str,
    candidates: Sequence[Tuple[int, str]],
    threshold: int = 82,
    min_shared: int = 2,
) -> Optional[int]:
    """
    Best fuzzy match above threshold, or None.

    candidates is a sequence of (cluster_id, norm_title). Two headlines need
    both a high blended score and at least min_shared words in common, so a
    pair of three-word headlines cannot merge on one word alone.
    """
    if not norm_title or not candidates:
        return None

    best_id: Optional[int] = None
    best_score = float(threshold) - 0.001

    for cluster_id, other in candidates:
        if not other:
            continue
        if shared_tokens(norm_title, other) < min_shared:
            continue
        score = title_similarity(norm_title, other)
        if score > best_score:
            best_score = score
            best_id = cluster_id

    return best_id
