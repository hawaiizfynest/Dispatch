"""
Seed data: feeds, categories, templates.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

from typing import List, Tuple

# (name, url) — everything here is editable in Feeds > Manage feeds.
DEFAULT_FEEDS: List[Tuple[str, str]] = [
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/"),
    ("The Hacker News", "https://feeds.feedburner.com/TheHackersNews"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/"),
    ("The Record", "https://therecord.media/feed/"),
    ("Ars Technica — Security", "https://arstechnica.com/security/feed"),
    ("SecurityWeek", "https://feeds.feedburner.com/securityweek"),
    ("Dark Reading", "https://www.darkreading.com/rss.xml"),
    ("CISA Advisories", "https://www.cisa.gov/cybersecurity-advisories/all.xml"),
    ("SANS Internet Storm Center", "https://isc.sans.edu/rssfeed_full.xml"),
    ("Schneier on Security", "https://www.schneier.com/feed/atom/"),
    ("Google Project Zero", "https://googleprojectzero.blogspot.com/feeds/posts/default"),
    ("Cisco Talos", "https://blog.talosintelligence.com/rss/"),
    ("Malwarebytes Labs", "https://www.malwarebytes.com/blog/feed/index.xml"),
    ("Sophos News", "https://www.sophos.com/en-us/blog/feed"),
    ("Microsoft Security Blog", "https://www.microsoft.com/en-us/security/blog/feed/"),
    ("Rapid7 Blog", "https://blog.rapid7.com/rss/"),
    ("Have I Been Pwned", "https://feeds.feedburner.com/HaveIBeenPwnedLatestBreaches"),
    ("Graham Cluley", "https://grahamcluley.com/feed/"),
]

CATEGORIES: List[str] = [
    "ransomware",
    "vulnerability",
    "breach",
    "malware",
    "apt",
    "policy",
    "research",
    "other",
]

# Keyword weights per category. First match with the highest score wins.
CATEGORY_KEYWORDS = {
    "ransomware": [
        "ransomware", "ransom", "lockbit", "alphv", "blackcat", "cl0p", "clop",
        "royal ransom", "akira", "rhysida", "play ransomware", "extortion",
        "double extortion", "encryptor", "leak site",
    ],
    "vulnerability": [
        "cve-", "vulnerability", "vulnerabilities", "zero-day", "zero day",
        "0-day", "patch tuesday", "rce", "remote code execution", "privilege escalation",
        "exploit", "poc", "proof-of-concept", "buffer overflow", "sql injection",
        "kev catalog", "actively exploited", "security update", "advisory", "flaw",
    ],
    "breach": [
        "data breach", "breach", "leaked", "leak", "exposed", "stolen data",
        "records exposed", "customer data", "hacked", "compromise", "exfiltrat",
        "database exposed", "unsecured",
    ],
    "malware": [
        "malware", "trojan", "backdoor", "botnet", "infostealer", "stealer",
        "loader", "rootkit", "spyware", "rat ", "cryptominer", "worm",
        "dropper", "supply chain attack", "malicious package", "npm package",
        "pypi package", "phishing", "smishing",
    ],
    "apt": [
        "apt", "nation-state", "nation state", "state-sponsored", "espionage",
        "lazarus", "sandworm", "fancy bear", "cozy bear", "volt typhoon",
        "salt typhoon", "kimsuky", "turla", "charming kitten", "mustang panda",
        "threat actor", "cyber espionage",
    ],
    "policy": [
        "sec ", "regulation", "regulatory", "lawsuit", "fine", "gdpr", "hipaa",
        "compliance", "legislation", "bill", "sanctions", "indict", "arrest",
        "sentenced", "guilty", "court", "doj", "ftc", "executive order",
        "cyber insurance", "disclosure rule",
    ],
    "research": [
        "research", "researchers", "study", "report finds", "whitepaper",
        "analysis", "technique", "framework", "benchmark", "survey",
    ],
}

BBCODE_TITLE = "{title}{cve_suffix}"
BBCODE_TEMPLATE = """[b]{title}[/b]

{summary}

{facts_bbcode}
[b]Source:[/b] [url={url}]{source}[/url]
{extra_sources_bbcode}"""

DIGEST_BBCODE_TITLE = "{title}"
DIGEST_BBCODE_TEMPLATE = """[b]{title}[/b]
{summary}
[url={url}]{source}[/url]{cve_line_bbcode}"""

MARKDOWN_TITLE = "{title}{cve_suffix}"
MARKDOWN_TEMPLATE = """## {title}

{summary}

{facts_md}
**Source:** [{source}]({url})
{extra_sources_md}"""

PLAIN_TITLE = "{title}"
PLAIN_TEMPLATE = """{title}

{summary}

{facts_plain}
Source: {source} — {url}
{extra_sources_plain}"""

# Public domain sources only. {fulltext} renders nothing anywhere else and the
# Compose tab says why.
ADVISORY_TITLE = "{title}{cve_suffix}"
ADVISORY_TEMPLATE = """[b]{title}[/b]

{facts_bbcode}
[b]Advisory in full[/b]
[quote]{fulltext}[/quote]

[b]Source:[/b] [url={url}]{source}[/url]
{licence_note}"""

# --- roundups: one thread, many stories

ROUNDUP_TITLE = "Security roundup — {date} ({count} stories)"
ROUNDUP_ITEM = """[b]{index}. {title}[/b]
{summary_short}
{cve_line_bbcode}[url={url}]{source}[/url]{extra_source_count}
"""
ROUNDUP_TEMPLATE = """{notes}

[hr]
{items}
[hr]
{count} stories · {date} · {outlets} outlets"""

CVE_ROUNDUP_TITLE = "Patch roundup — {date} ({count} advisories)"
CVE_ROUNDUP_ITEM = """[b]{index}. {title}[/b]
{facts_bbcode}[url={url}]{source}[/url]
"""
CVE_ROUNDUP_TEMPLATE = """{notes}

{items}
{count} advisories · compiled {date}"""

# (name, format, kind, title, item, body)
DEFAULT_TEMPLATES: List[Tuple[str, str, str, str, str, str]] = [
    ("Forum post (BBCode)", "bbcode", "single", BBCODE_TITLE, "", BBCODE_TEMPLATE),
    ("Forum digest line (BBCode)", "bbcode", "single", DIGEST_BBCODE_TITLE, "", DIGEST_BBCODE_TEMPLATE),
    ("Markdown post", "markdown", "single", MARKDOWN_TITLE, "", MARKDOWN_TEMPLATE),
    ("Plain text", "plain", "single", PLAIN_TITLE, "", PLAIN_TEMPLATE),
    ("Advisory in full (public domain only)", "bbcode", "single", ADVISORY_TITLE, "", ADVISORY_TEMPLATE),
    ("Weekly roundup (BBCode)", "bbcode", "digest", ROUNDUP_TITLE, ROUNDUP_ITEM, ROUNDUP_TEMPLATE),
    ("Patch roundup (BBCode)", "bbcode", "digest", CVE_ROUNDUP_TITLE, CVE_ROUNDUP_ITEM, CVE_ROUNDUP_TEMPLATE),
]

TEMPLATE_TOKENS = [
    ("{title}", "Headline of the lead article"),
    ("{title_short}", "Headline trimmed to the thread title limit"),
    ("{category_tag}", "[Ransomware] style tag with trailing space, blank when untagged"),
    ("{category_upper}", "Category in caps, blank when untagged"),
    ("{cve_first}", "First CVE ID only, blank when none"),
    ("{cve_suffix}", "' (CVE-2026-1337)', blank when none or already in the headline"),
    ("{summary}", "Cleaned summary text, HTML stripped"),
    ("{url}", "Lead article URL"),
    ("{source}", "Feed name of the lead article"),
    ("{author}", "Byline, when the feed provides one"),
    ("{published}", "Publish timestamp of the lead article"),
    ("{date}", "Today's date"),
    ("{category}", "Cluster category"),
    ("{notes}", "Your notes on the cluster"),
    ("{cve_list}", "Comma-separated CVE IDs found in the story"),
    ("{cve_line_bbcode}", "CVE line, blank when no CVEs found"),
    ("{cve_line_md}", "Markdown CVE line, blank when none"),
    ("{cve_line_plain}", "Plain CVE line, blank when none"),
    ("{sources_bbcode}", "All sources as BBCode links"),
    ("{sources_md}", "All sources as Markdown links"),
    ("{sources_plain}", "All sources as plain lines"),
    ("{extra_sources_bbcode}", "Other coverage block, blank when single source"),
    ("{extra_sources_md}", "Other coverage block, Markdown"),
    ("{extra_sources_plain}", "Other coverage block, plain"),
    ("{source_count}", "Number of outlets carrying the story"),
    ("{summary_short}", "One sentence, for roundup items"),
    ("{facts_bbcode}", "Key facts list: CVEs, CVSS, exploitation, products, scale"),
    ("{facts_md}", "Key facts, Markdown"),
    ("{facts_plain}", "Key facts, plain"),
    ("{fulltext}", "Whole article. Public domain sources only, empty elsewhere"),
    ("{licence_note}", "Why full text is or is not available for this source"),
    ("{items}", "DIGEST ONLY: every selected story, rendered through the item format"),
    ("{count}", "DIGEST ONLY: how many stories are in the roundup"),
    ("{outlets}", "DIGEST ONLY: how many distinct outlets the roundup draws on"),
    ("{index}", "DIGEST ITEM ONLY: position of this story in the roundup"),
    ("{extra_source_count}", "' +3 more' when other outlets ran it, else empty"),
]
