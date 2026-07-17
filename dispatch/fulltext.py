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


# Standard feed-reader identities, used only to work out whether a refusal is
# about the User-Agent at all. Nothing rotates through these behind your back:
# the refresh sends whatever is in Settings and nothing else.
PROBE_AGENTS = [
    ("feedparser default", "feedparser/6.0.12 +https://github.com/kurtmckee/feedparser/"),
    ("bare name and version", "Dispatch/1.0"),
]


def _try_once(url: str, user_agent: str, timeout: int):
    """Returns (status, note, body_head)."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers.get("Content-Type", "?"), response.read(300)
    except HTTPError as exc:
        body = b""
        try:
            body = exc.read(300)
        except Exception:
            pass
        marks = []
        if exc.headers:
            if exc.headers.get("cf-ray"):
                marks.append("Cloudflare")
            if exc.headers.get("x-reference-error") or b"Reference #" in body:
                marks.append("Akamai")
            if exc.headers.get("Server"):
                marks.append(f"Server: {exc.headers.get('Server')}")
        return exc.code, ", ".join(marks) or "(no clue in the headers)", body
    except (URLError, socket.timeout, OSError, ValueError) as exc:
        return None, str(exc)[:120], b""


def probe_feed(url: str, user_agent: str, timeout: int = 20) -> str:
    """
    Fetch a feed URL raw and report exactly what came back.

    A 403 says a host refused the request and nothing more. Guessing at the
    reason sends people to change settings that were never wrong, so this shows
    the reply. When the configured agent is refused it retries with a couple of
    ordinary reader identities, which answers the only question that matters
    next: is this about the User-Agent, or about you?
    """
    lines = [f"URL:        {url}", f"User-Agent: {user_agent}", ""]

    status, note, body = _try_once(url, user_agent, timeout)
    lines.append(f"Status:     {status if status else 'no reply'}")
    lines.append(f"Detail:     {note}")
    lines.append("")
    lines.append("First bytes of the reply:")
    lines.append(repr(body[:280]) if body else "(empty)")

    if status == 200:
        lines.append("")
        lines.append("This feed is fine.")
        return "\n".join(lines)

    if status in (401, 403):
        lines.append("")
        lines.append("Refused. Trying other identities to see whether the agent matters:")
        any_ok = False
        for label, agent in PROBE_AGENTS:
            other, other_note, _ = _try_once(url, agent, timeout)
            mark = "WORKS" if other == 200 else f"{other or 'no reply'}"
            lines.append(f"  {mark:9} {label}: {agent[:52]}")
            if other == 200:
                any_ok = True
        lines.append("")
        if any_ok:
            lines.append(
                "Another identity got through, so this host objects to the agent "
                "rather than to you. Put a working one in File > Settings."
            )
        else:
            lines.append(
                "Every identity was refused while the same URL loads in your "
                "browser. That points at the host's bot detection reading the "
                "connection itself, not the agent string. No setting in here "
                "changes that. Disable the feed, or reach it another way."
            )
    return "\n".join(lines)
