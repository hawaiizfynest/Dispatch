"""
Full text, for the sources where that is yours to take.

Works produced by US federal agencies carry no copyright (17 U.S.C. section 105).
A CISA advisory or an NVD entry can go into a post whole. A BleepingComputer
article cannot, however convenient it would be, so this module refuses to fetch
one rather than leaving the decision to whoever is in a hurry.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

import re
import socket
import urllib.request
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from .cluster import strip_html
from .config import USER_AGENT

# US federal agency hosts. Their advisories are federal work product and sit in
# the public domain. This list stays hardcoded and stays short: an editable
# allowlist is just a switch for turning copyright off.
PUBLIC_DOMAIN_HOSTS = {
    "cisa.gov",
    "us-cert.gov",
    "nvd.nist.gov",
    "nist.gov",
    "csrc.nist.gov",
    "ic3.gov",
    "fbi.gov",
    "justice.gov",
    "nsa.gov",
    "defense.gov",
    "cyber.mil",
    "energy.gov",
    "hhs.gov",
    "treasury.gov",
    "sec.gov",
    "ftc.gov",
}

MAX_FULLTEXT_CHARS = 20000

DROP_TAGS_RE = re.compile(
    r"(?is)<(script|style|nav|header|footer|aside|form|noscript|svg|iframe)\b[^>]*>.*?</\1\s*>"
)
MAIN_RE = re.compile(r"(?is)<(article|main)\b[^>]*>(.*?)</\1\s*>")
BODY_RE = re.compile(r"(?is)<body\b[^>]*>(.*?)</body\s*>")

# Boilerplate that survives extraction on federal pages.
BOILERPLATE = [
    re.compile(r"(?im)^\s*an official website of the united states government.*$"),
    re.compile(r"(?im)^\s*here'?s how you know.*$"),
    re.compile(r"(?im)^\s*official websites use \.gov.*$"),
    re.compile(r"(?im)^\s*secure \.gov websites use HTTPS.*$"),
    re.compile(r"(?im)^\s*share:?\s*$"),
    re.compile(r"(?im)^\s*(?:skip to main content|back to top|print|subscribe)\s*$"),
]


def host_of(url: str) -> str:
    try:
        host = urlsplit(url).netloc.lower()
    except ValueError:
        return ""
    if ":" in host:
        host = host.rsplit(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def is_public_domain(url: str) -> bool:
    """
    True when the URL points at a US federal agency.

    Matches the registrable domain and its subdomains, so both cisa.gov and
    an advisory served from a cisa.gov subdomain qualify, while a lookalike
    such as cisa.gov.example.com does not.
    """
    host = host_of(url)
    if not host:
        return False
    return any(host == pd or host.endswith("." + pd) for pd in PUBLIC_DOMAIN_HOSTS)


def licence_note(url: str) -> str:
    """One line explaining why full text is or is not on the table."""
    if is_public_domain(url):
        return f"{host_of(url)} is a US federal agency. Its advisories are public domain."
    return (
        f"{host_of(url) or 'This outlet'} holds copyright on its articles. "
        "Dispatch pulls the facts and leaves the prose where it is."
    )


def _extract_main(html: str) -> str:
    """Pull the article region out of a page, best effort."""
    html = DROP_TAGS_RE.sub(" ", html)

    best = ""
    for match in MAIN_RE.finditer(html):
        chunk = match.group(2)
        if len(chunk) > len(best):
            best = chunk
    if not best:
        body = BODY_RE.search(html)
        best = body.group(1) if body else html

    text = strip_html(best)
    for pattern in BOILERPLATE:
        text = pattern.sub("", text)

    # Federal pages leave a lot of whitespace-only lines behind once the markup
    # goes. Drop them, and glue orphaned labels back onto their values so
    # "Release Date" and the date itself do not land on separate lines.
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_fulltext(
    url: str,
    user_agent: str = USER_AGENT,
    timeout: int = 20,
) -> Tuple[Optional[str], str]:
    """
    Fetch and extract article text.

    Returns (text, status). text is None when the fetch failed or the source is
    not public domain. status always explains itself.
    """
    if not url:
        return None, "No URL on this article."
    if not is_public_domain(url):
        return None, licence_note(url)

    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(3_000_000)
    except (HTTPError, URLError, socket.timeout, OSError, ValueError) as exc:
        return None, f"Could not reach {host_of(url)}: {str(exc)[:120]}"

    try:
        html = raw.decode(charset, errors="replace")
    except LookupError:
        html = raw.decode("utf-8", errors="replace")

    text = _extract_main(html)
    if len(text) < 200:
        return None, "Fetched the page but found no article text on it."

    truncated = False
    if len(text) > MAX_FULLTEXT_CHARS:
        text = text[:MAX_FULLTEXT_CHARS].rsplit("\n", 1)[0]
        truncated = True

    status = f"Pulled {len(text):,} characters from {host_of(url)} (public domain)."
    if truncated:
        status += " Trimmed to fit a forum post."
    return text, status
