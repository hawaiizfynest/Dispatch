"""
Feed fetching and ingest.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

import hashlib
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError

import feedparser

from . import cluster as clu
from .db import Database

MAX_SUMMARY_CHARS = 4000


@dataclass
class FetchResult:
    feed_id: int
    feed_name: str
    status: str = "ok"
    error: str = ""
    entries: List[Dict[str, Any]] = field(default_factory=list)
    etag: Optional[str] = None
    modified: Optional[str] = None
    not_modified: bool = False
    moved_to: str = ""


def _http_error_text(code: int) -> str:
    """Say what a status code means for this feed and what to do about it."""
    if code in (401, 403):
        return (
            f"HTTP {code}: the host refused the request. Its firewall does not like "
            "the User-Agent. Change it in File > Settings."
        )
    if code == 404:
        return "HTTP 404: the feed is gone. Check the URL in Feeds > Manage feeds."
    if code == 429:
        return "HTTP 429: too many requests. Lower Parallel fetches in Settings."
    if 500 <= code < 600:
        return f"HTTP {code}: the outlet's server is having problems. Try later."
    return f"HTTP {code}"


def _parse_error_text(exc: Any, code: Optional[int]) -> str:
    """
    Turn an XML complaint into something worth reading.

    feedparser reports where the parse broke, which is useless when the thing it
    parsed was never a feed. Say that instead.
    """
    detail = str(exc)[:120]
    if code and 200 <= code < 300:
        return (
            f"The host returned something that is not a feed ({detail}). "
            "The URL may point at a web page rather than its RSS."
        )
    return f"Could not parse the feed: {detail}"


def _entry_guid(entry: Any, url: str, title: str) -> str:
    """Stable per-entry key. Some feeds omit id, some recycle it."""
    for key in ("id", "guid"):
        value = entry.get(key) if hasattr(entry, "get") else getattr(entry, key, None)
        if value:
            return str(value)[:400]
    basis = url or title
    return hashlib.sha256(basis.encode("utf-8", "replace")).hexdigest()


def _entry_published(entry: Any) -> Optional[str]:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = getattr(entry, key, None)
        if parsed:
            try:
                return datetime.fromtimestamp(
                    time.mktime(parsed), tz=timezone.utc
                ).isoformat(timespec="seconds")
            except (OverflowError, ValueError):
                continue
    return None


def _entry_summary(entry: Any) -> str:
    raw = ""
    content = getattr(entry, "content", None)
    if content:
        try:
            raw = content[0].get("value", "")
        except (AttributeError, IndexError, KeyError):
            raw = ""
    if not raw:
        raw = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    text = clu.strip_continuation(clu.strip_html(raw))
    if len(text) > MAX_SUMMARY_CHARS:
        text = text[:MAX_SUMMARY_CHARS].rsplit(" ", 1)[0] + "..."
    return text


def _entry_author(entry: Any) -> str:
    author = getattr(entry, "author", "") or ""
    if not author:
        detail = getattr(entry, "author_detail", None)
        if detail:
            author = detail.get("name", "") or ""
    return clu.strip_html(author)[:200]


def fetch_feed(
    feed_id: int,
    feed_name: str,
    url: str,
    etag: Optional[str],
    modified: Optional[str],
    user_agent: str,
    timeout: int,
) -> FetchResult:
    """Pull one feed. Conditional GET when the host gave us a validator."""
    result = FetchResult(feed_id=feed_id, feed_name=feed_name)
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        parsed = feedparser.parse(
            url,
            etag=etag or None,
            modified=modified or None,
            agent=user_agent,
        )
    except (HTTPError, URLError, socket.timeout, OSError, ValueError) as exc:
        result.status = "error"
        result.error = str(exc)[:300]
        return result
    finally:
        socket.setdefaulttimeout(old_timeout)

    status_code = getattr(parsed, "status", None)
    if status_code == 304:
        result.not_modified = True
        result.status = "not modified"
        result.etag = etag
        result.modified = modified
        return result

    # HTTP status comes first, before any XML complaint. A blocked feed hands
    # back an HTML error page, feedparser tries to parse that as a feed, and the
    # resulting "mismatched tag" describes the error page rather than the feed.
    # Reporting that instead of the 403 sends you hunting for a problem that is
    # not there.
    if status_code and status_code >= 400:
        result.status = "error"
        result.error = _http_error_text(status_code)
        return result

    # A permanent redirect means the outlet moved the feed. Pass the new address
    # back so the caller can save it instead of taking the detour forever.
    if status_code in (301, 308) and parsed.entries:
        # Only chase a redirect that landed on a real feed. Sophos points its
        # old address at a path that parses to nothing, and saving that would
        # trade a working detour for a dead end.
        moved_to = getattr(parsed, "href", "") or ""
        if moved_to and moved_to != url:
            result.moved_to = moved_to

    bozo_exc = getattr(parsed, "bozo_exception", None)
    if not parsed.entries and bozo_exc is not None:
        result.status = "error"
        result.error = _parse_error_text(bozo_exc, status_code)
        return result

    result.etag = getattr(parsed, "etag", None)
    result.modified = getattr(parsed, "modified", None)

    for entry in parsed.entries:
        link = getattr(entry, "link", "") or ""
        title = clu.clean_title(getattr(entry, "title", "") or "")
        if not title:
            continue
        canonical = clu.canonical_url(link)
        result.entries.append(
            {
                "feed_id": feed_id,
                "guid": _entry_guid(entry, link, title),
                "url": link,
                "canonical_url": canonical or link,
                "title": title,
                "summary": _entry_summary(entry),
                "author": _entry_author(entry),
                "published": _entry_published(entry),
            }
        )

    if not result.entries:
        result.status = "empty"
    return result


def fetch_all(
    feeds: List[Dict[str, Any]],
    user_agent: str,
    timeout: int,
    workers: int = 6,
    progress=None,
    cancelled=None,
) -> List[FetchResult]:
    """Fetch feeds in parallel. progress(done, total, name) is called per feed."""
    results: List[FetchResult] = []
    total = len(feeds)
    done = 0

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(
                fetch_feed,
                f["id"],
                f["name"],
                f["url"],
                f.get("etag"),
                f.get("modified"),
                user_agent,
                timeout,
            ): f
            for f in feeds
        }
        for future in as_completed(futures):
            feed = futures[future]
            if cancelled is not None and cancelled():
                for pending in futures:
                    pending.cancel()
                break
            try:
                result = future.result()
            except Exception as exc:  # a single bad feed must not sink the run
                result = FetchResult(
                    feed_id=feed["id"],
                    feed_name=feed["name"],
                    status="error",
                    error=str(exc)[:300],
                )
            results.append(result)
            done += 1
            if progress is not None:
                progress(done, total, result.feed_name)
    return results


def ingest(
    db: Database,
    results: List[FetchResult],
    threshold: int = 82,
    window_days: int = 5,
    auto_categorize: bool = True,
) -> Tuple[int, int]:
    """
    Write fetched entries into the database, folding duplicates into clusters.

    Returns (new_articles, new_clusters).
    """
    new_articles = 0
    new_clusters = 0

    # One snapshot of recent clusters, extended in memory as we go, so a batch
    # containing the same story from six outlets still collapses to one cluster.
    candidates: List[Tuple[int, str]] = [
        (row["id"], row["norm_title"]) for row in db.recent_clusters(window_days)
    ]

    for result in results:
        if result.moved_to:
            db.move_feed(result.feed_id, result.moved_to)
        if result.status == "error" or result.not_modified:
            db.record_fetch(result.feed_id, result.status or "error", result.etag, result.modified)
            continue

        for entry in result.entries:
            if db.article_exists(entry["feed_id"], entry["guid"]):
                continue

            cluster_id = db.cluster_for_canonical(entry["canonical_url"])
            norm = clu.normalize_title(entry["title"])

            if cluster_id is None:
                cluster_id = clu.match_cluster(norm, candidates, threshold=threshold)

            if cluster_id is None:
                category = (
                    clu.guess_category(entry["title"], entry["summary"])
                    if auto_categorize
                    else None
                )
                cluster_id = db.create_cluster(entry["title"], norm, category)
                candidates.append((cluster_id, norm))
                new_clusters += 1
            else:
                db.touch_cluster(cluster_id)

            if db.insert_article(entry, cluster_id) is not None:
                new_articles += 1

        db.record_fetch(result.feed_id, result.status, result.etag, result.modified)

    db.commit()
    return new_articles, new_clusters
