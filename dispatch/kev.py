"""
CISA's Known Exploited Vulnerabilities catalog.

CISA retired its RSS feeds in May 2025. The advisories endpoint still answers
from some networks and refuses others, because nobody maintains a rule for a
channel that was switched off. The KEV catalog survived as a plain JSON file
under a different path, and that path is still served to everyone.

It is better material anyway. Every entry is a vulnerability someone is already
exploiting, with the vendor, the product, the fix, and whether ransomware crews
have picked it up. Federal work product, so the text is public domain.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from . import cluster as clu

KEV_MARKER = "known_exploited_vulnerabilities.json"

# The catalog carries every KEV ever listed, over 1,600 of them. Pulling the lot
# would bury the inbox on first refresh, so only recent additions come through.
# CISA adds a handful a week, which puts this window at roughly 15-30 stories.
KEV_WINDOW_DAYS = 45
KEV_MAX_ENTRIES = 60


def is_kev_url(url: str) -> bool:
    return KEV_MARKER in (url or "").lower()


def _iso(date_text: str) -> str:
    """KEV dates are plain YYYY-MM-DD. Give them a timezone so sorting works."""
    try:
        parsed = datetime.strptime(date_text.strip(), "%Y-%m-%d")
    except (ValueError, AttributeError):
        return ""
    return parsed.replace(tzinfo=timezone.utc).isoformat(timespec="seconds")


def _title(item: Dict[str, Any]) -> str:
    vendor = (item.get("vendorProject") or "").strip()
    product = (item.get("product") or "").strip()
    name = (item.get("vulnerabilityName") or "").strip()
    cve = (item.get("cveID") or "").strip()

    subject = " ".join(p for p in (vendor, product) if p)
    if subject and name:
        # "Microsoft Windows: Use-After-Free Vulnerability (CVE-2026-58644)"
        headline = f"{subject}: {name}"
    else:
        headline = name or subject or cve
    if cve and cve.upper() not in headline.upper():
        headline = f"{headline} ({cve})"
    return clu.clean_title(headline)


def _summary(item: Dict[str, Any]) -> str:
    """
    Readable prose that also feeds the fact extractor.

    The exploited and KEV wording is deliberate: everything in this catalog is
    under active exploitation by definition, and the Key facts block reads that
    from the text rather than being told separately.
    """
    parts: List[str] = []

    description = (item.get("shortDescription") or "").strip()
    if description:
        parts.append(description)

    parts.append(
        "Listed in CISA's Known Exploited Vulnerabilities catalog, which means "
        "it is being actively exploited in the wild."
    )

    action = (item.get("requiredAction") or "").strip()
    if action:
        parts.append(f"Required action: {action}")

    due = (item.get("dueDate") or "").strip()
    if due:
        parts.append(f"Federal agencies have until {due} to comply.")

    ransomware = (item.get("knownRansomwareCampaignUse") or "").strip()
    if ransomware.lower() == "known":
        parts.append("Ransomware crews are known to use this one.")
    elif ransomware.lower() == "unknown":
        parts.append("No confirmed ransomware campaign use so far.")

    notes = (item.get("notes") or "").strip()
    if notes:
        parts.append(notes)

    return "\n\n".join(parts)


def parse_kev(
    payload: bytes,
    feed_id: int,
    window_days: int = KEV_WINDOW_DAYS,
    max_entries: int = KEV_MAX_ENTRIES,
) -> List[Dict[str, Any]]:
    """
    Turn the catalog into article entries, newest first.

    Raises ValueError when the payload is not the catalog, so the caller can
    report that rather than quietly ingesting nothing.
    """
    try:
        data = json.loads(payload.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc

    if not isinstance(data, dict) or "vulnerabilities" not in data:
        raise ValueError("JSON is not the KEV catalog: no vulnerabilities list")

    rows = data.get("vulnerabilities") or []
    if not isinstance(rows, list):
        raise ValueError("KEV vulnerabilities is not a list")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).date()
    entries: List[Dict[str, Any]] = []

    for item in rows:
        if not isinstance(item, dict):
            continue
        cve = (item.get("cveID") or "").strip().upper()
        if not cve:
            continue

        added = (item.get("dateAdded") or "").strip()
        try:
            added_date = datetime.strptime(added, "%Y-%m-%d").date()
        except ValueError:
            continue
        if added_date < cutoff:
            continue

        # NVD carries the detail CISA's one-liner leaves out, and it is a
        # federal source too, so the full text is fair game there.
        url = f"https://nvd.nist.gov/vuln/detail/{cve}"

        entries.append(
            {
                "feed_id": feed_id,
                "guid": f"kev:{cve}",
                "url": url,
                "canonical_url": clu.canonical_url(url),
                "title": _title(item),
                "summary": _summary(item),
                "author": "CISA",
                "published": _iso(added),
            }
        )

    entries.sort(key=lambda e: e["published"], reverse=True)
    return entries[:max_entries]
