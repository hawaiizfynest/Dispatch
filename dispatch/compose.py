"""
Draft rendering.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from . import cluster as clu
from .extract import extract_facts, render_facts
from .fulltext import is_public_domain, licence_note

TOKEN_RE = re.compile(r"\{(\w+)\}")

SUMMARY_SENTENCE_LIMIT = 3
SUMMARY_CHAR_LIMIT = 700
TITLE_CHAR_LIMIT = 100


def trim_title(text: str, limit: int = TITLE_CHAR_LIMIT) -> str:
    """Cut a thread title to fit, on a word boundary, with an ellipsis."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    cut = text[: limit - 3].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") + "..."


def trim_summary(text: str, sentences: int = SUMMARY_SENTENCE_LIMIT) -> str:
    """
    First few sentences of a feed summary, since most feeds dump the lede.

    Strips HTML again even though ingest already did. Feeds are unpredictable
    and a stray <p> pasted into a forum post is exactly the kind of thing that
    slips through, so this belt-and-braces pass stays.
    """
    text = clu.strip_html(text or "").strip()
    text = clu.strip_continuation(text)
    if not text:
        return ""
    first_para = text.split("\n\n", 1)[0].strip()
    parts = re.split(r"(?<=[.!?])\s+", first_para)
    out = clu.strip_continuation(" ".join(parts[:sentences]).strip())
    if len(out) > SUMMARY_CHAR_LIMIT:
        out = out[:SUMMARY_CHAR_LIMIT].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    return out


def _fmt_date(iso: Optional[str], fallback: str = "") -> str:
    if not iso:
        return fallback
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %Y")
    except ValueError:
        return fallback or iso


def build_context(
    cluster_row: sqlite3.Row,
    articles: Sequence[sqlite3.Row],
    summary_sentences: int = SUMMARY_SENTENCE_LIMIT,
    title_limit: int = TITLE_CHAR_LIMIT,
    fulltext: str = "",
) -> Dict[str, str]:
    """
    Every token a template can reference, resolved for one cluster.

    fulltext arrives already fetched, and only ever for a public domain source.
    This function does not go and get it: rendering a draft should not fire off
    a network request every time you click a row.
    """
    if not articles:
        return {}

    lead = articles[0]
    others = list(articles[1:])

    title = clu.clean_title(lead["title"])
    summary = trim_summary(lead["summary"] or "", summary_sentences)
    if not summary:
        for alt in others:
            summary = trim_summary(alt["summary"] or "", summary_sentences)
            if summary:
                break

    cves = clu.extract_cves(
        " ".join(a["title"] or "" for a in articles),
        " ".join((a["summary"] or "")[:1500] for a in articles),
    )
    cve_list = ", ".join(cves)

    # Links get the tracking-free form. Pasting utm_source=rss onto a forum
    # is sloppy and some boards flag it as referral spam.
    links = {a["id"]: clu.display_url(a["url"] or "") for a in articles}
    lead_link = links[lead["id"]]

    sources_bbcode = "\n".join(
        f"[*][url={links[a['id']]}]{a['feed_name']}[/url]" for a in articles
    )
    sources_md = "\n".join(f"- [{a['feed_name']}]({links[a['id']]})" for a in articles)
    sources_plain = "\n".join(f"- {a['feed_name']}: {links[a['id']]}" for a in articles)

    if others:
        extra_bbcode = (
            "[b]Other coverage:[/b]\n[list]\n"
            + "\n".join(f"[*][url={links[a['id']]}]{a['feed_name']}[/url]" for a in others)
            + "\n[/list]\n"
        )
        extra_md = (
            "**Other coverage:**\n"
            + "\n".join(f"- [{a['feed_name']}]({links[a['id']]})" for a in others)
            + "\n"
        )
        extra_plain = (
            "Other coverage:\n"
            + "\n".join(f"- {a['feed_name']}: {links[a['id']]}" for a in others)
            + "\n"
        )
    else:
        extra_bbcode = extra_md = extra_plain = ""

    if cve_list:
        cve_bbcode = f"[b]CVEs:[/b] {cve_list}\n"
        cve_md = f"**CVEs:** {cve_list}\n"
        cve_plain = f"CVEs: {cve_list}\n"
    else:
        cve_bbcode = cve_md = cve_plain = ""

    # Title-only tokens.
    category = cluster_row["category"] or ""
    category_tag = f"[{category.capitalize()}] " if category else ""
    cve_first = cves[0] if cves else ""
    # Most outlets already put the CVE in the headline. Appending it again
    # gives you "...zero-day CVE-2026-1337 (CVE-2026-1337)", so only add the
    # suffix when the headline does not already carry that ID.
    if cve_first and cve_first.upper() not in title.upper():
        cve_suffix = f" ({cve_first})"
    else:
        cve_suffix = ""

    facts = extract_facts(
        " ".join(a["title"] or "" for a in articles),
        " ".join((a["summary"] or "") for a in articles),
        fulltext or "",
    )

    others_count = len(others)
    extra_source_count = f" +{others_count} more" if others_count else ""

    return {
        "title": title,
        "summary": summary,
        "summary_short": trim_summary(lead["summary"] or "", 1),
        "facts_bbcode": render_facts(facts, "bbcode"),
        "facts_md": render_facts(facts, "markdown"),
        "facts_plain": render_facts(facts, "plain"),
        "fulltext": fulltext or "",
        "licence_note": licence_note(lead["url"] or ""),
        "extra_source_count": extra_source_count,
        "url": lead_link,
        "raw_url": lead["url"] or "",
        "source": lead["feed_name"] or "",
        "author": lead["author"] or "",
        "published": _fmt_date(lead["published"]),
        "date": datetime.now().strftime("%b %d, %Y"),
        "title_short": trim_title(title, title_limit),
        "category_tag": category_tag,
        "category_upper": category.upper(),
        "cve_first": cve_first,
        "cve_suffix": cve_suffix,
        "category": category,
        "notes": cluster_row["notes"] or "",
        "cve_list": cve_list,
        "cve_line_bbcode": cve_bbcode,
        "cve_line_md": cve_md,
        "cve_line_plain": cve_plain,
        "sources_bbcode": sources_bbcode,
        "sources_md": sources_md,
        "sources_plain": sources_plain,
        "extra_sources_bbcode": extra_bbcode,
        "extra_sources_md": extra_md,
        "extra_sources_plain": extra_plain,
        "source_count": str(len(articles)),
    }


def render(template_body: str, context: Dict[str, str]) -> str:
    """
    Substitute {tokens}. Unknown tokens are left alone so a stray brace in
    BBCode or a spoiler tag does not blow up the render.
    """
    if not context:
        return ""

    def replace(match: "re.Match[str]") -> str:
        key = match.group(1)
        return context.get(key, match.group(0))

    out = TOKEN_RE.sub(replace, template_body)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip() + "\n"


def render_cluster(
    template_body: str,
    cluster_row: sqlite3.Row,
    articles: Sequence[sqlite3.Row],
    summary_sentences: int = SUMMARY_SENTENCE_LIMIT,
    title_limit: int = TITLE_CHAR_LIMIT,
) -> str:
    context = build_context(cluster_row, articles, summary_sentences, title_limit)
    return render(template_body, context)


def render_title(template_title: str, context: Dict[str, str]) -> str:
    """
    One line, no trailing newline, whitespace collapsed.

    A thread title field takes a single line. Anything a template renders with
    a newline in it would paste as a broken title, so flatten it here rather
    than leaving the user to notice.
    """
    if not context:
        return ""
    text = render(template_title, context)
    return " ".join(text.split())


def build_digest_context(
    entries: Sequence[Dict[str, str]],
    item_template: str,
    notes: str = "",
    date_text: str = "",
) -> Dict[str, str]:
    """
    Context for a roundup post.

    entries is a list of per-cluster contexts, already built. Each one gets an
    {index} and runs through the item template, then the results are joined into
    {items} for the body.
    """
    rendered: List[str] = []
    outlets: set = set()

    for position, context in enumerate(entries, start=1):
        local = dict(context)
        local["index"] = str(position)
        rendered.append(render(item_template, local).strip())
        if context.get("source"):
            outlets.add(context["source"])

    return {
        "items": "\n\n".join(rendered),
        "count": str(len(entries)),
        "outlets": str(len(outlets)),
        "notes": notes.strip(),
        "date": date_text or datetime.now().strftime("%b %d, %Y"),
        "category_tag": "",
        "cve_suffix": "",
        "title": f"{len(entries)} stories",
    }


def render_digest(
    template_body: str,
    item_template: str,
    entries: Sequence[Dict[str, str]],
    notes: str = "",
) -> str:
    return render(template_body, build_digest_context(entries, item_template, notes))
