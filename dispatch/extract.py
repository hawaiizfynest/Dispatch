"""
Fact extraction.

Pulls the checkable details out of a story: CVE IDs, severity scores, whether
anyone is exploiting it, affected products, how many records went out the door.
Facts carry no copyright, which is why this module reads for them instead of
lifting sentences.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)

# "CVSS 9.8", "CVSS v3.1 score of 9.8", "CVSS score: 9.8", "rated 9.8 out of 10"
CVSS_RES = [
    re.compile(
        r"CVSS(?:\s*v?[234](?:\.\d)?)?\s*(?:base\s*)?(?:score)?\s*(?:of|:|is)?\s*"
        r"(\d{1,2}(?:\.\d)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:severity|base)\s+(?:score|rating)\s+(?:of|:)?\s*(\d{1,2}(?:\.\d)?)",
        re.IGNORECASE,
    ),
    re.compile(r"\b(\d{1,2}\.\d)\s*(?:out of 10|/\s*10)\b", re.IGNORECASE),
]

EXPLOITED_RE = re.compile(
    r"actively exploited|exploited in the wild|under active (?:attack|exploitation)"
    r"|being (?:actively )?exploited|exploitation (?:is )?(?:ongoing|observed|detected)"
    r"|attacks? (?:are )?(?:ongoing|observed)|zero[- ]day",
    re.IGNORECASE,
)
NOT_EXPLOITED_RE = re.compile(
    r"no (?:evidence|reports?|indication) of (?:active )?exploitation"
    r"|not (?:been )?(?:actively )?exploited"
    r"|no known exploitation",
    re.IGNORECASE,
)
KEV_RE = re.compile(
    r"known exploited vulnerabilit|\bKEV\b|CISA(?:'s)? (?:KEV|catalog)"
    r"|added to (?:the )?(?:CISA )?catalog",
    re.IGNORECASE,
)
PATCH_RE = re.compile(
    r"patch(?:es|ed)? (?:is |are |now )?available|released (?:a |an )?(?:patch|fix|update|advisory)"
    r"|has (?:since )?(?:patched|fixed|addressed)|fix(?:es|ed)? (?:is |are )?available"
    r"|update(?:s)? (?:is |are )?(?:now )?available|shipped (?:a )?fix",
    re.IGNORECASE,
)
NO_PATCH_RE = re.compile(
    r"no patch|unpatched|no fix (?:is )?available|awaiting a (?:patch|fix)"
    r"|patch (?:is )?not (?:yet )?available|no official fix|remains unpatched",
    re.IGNORECASE,
)
POC_RE = re.compile(
    r"proof[- ]of[- ]concept|\bPoC\b|exploit code (?:is )?(?:public|available|released)",
    re.IGNORECASE,
)

# Words that flip the meaning of a phrase that follows them. "Fortinet has not
# released a patch" contains "released a patch" and means the opposite of it,
# so every positive match gets checked against the run-up text.
NEGATION_RE = re.compile(
    r"\b(?:not|no|never|nor|without|hasn't|haven't|hadn't|isn't|aren't|wasn't"
    r"|weren't|doesn't|don't|didn't|cannot|can't|won't|yet to|awaiting|pending"
    r"|unable to|declined to|failed to|stopped short of)\b",
    re.IGNORECASE,
)
NEGATION_WINDOW = 45


def _negated(text: str, start: int, window: int = NEGATION_WINDOW) -> bool:
    """True when a negation sits close enough in front of a match to flip it."""
    prefix = text[max(0, start - window) : start]
    # A sentence boundary ends the negation's reach: "No patch exists. Microsoft
    # released a fix for the other bug" must not read as negated.
    for boundary in (". ", "! ", "? ", "; "):
        index = prefix.rfind(boundary)
        if index != -1:
            prefix = prefix[index + len(boundary) :]
    return bool(NEGATION_RE.search(prefix))


def _positive_match(pattern: "re.Pattern[str]", text: str) -> bool:
    """True when the pattern matches somewhere it is not negated."""
    return any(not _negated(text, m.start()) for m in pattern.finditer(text))

# "6.9 million records", "40 organizations", "2,300 servers"
COUNT_RE = re.compile(
    r"\b(\d[\d,]*(?:\.\d+)?)\s*(million|billion|thousand)?\s+"
    r"(records?|customers?|users?|organi[sz]ations?|orgs?|victims?|devices?|servers?"
    r"|systems?|accounts?|companies|instances?|endpoints?|hosts?|machines?|people)\b",
    re.IGNORECASE,
)

# Products worth naming in a forum post. Matched whole-word, case-insensitive.
PRODUCTS = [
    "Windows Server", "Windows 11", "Windows 10", "Windows", "Microsoft Exchange",
    "Exchange Server", "Active Directory", "SharePoint", "Microsoft 365", "Azure",
    "Outlook", "Office", "Chrome", "Chromium", "Firefox", "Safari", "Edge",
    "Android", "iOS", "iPadOS", "macOS", "Linux kernel", "Linux", "Ubuntu",
    "Red Hat", "VMware ESXi", "VMware vCenter", "VMware", "Citrix NetScaler",
    "Citrix", "Fortinet FortiOS", "FortiGate", "FortiOS", "Fortinet", "Ivanti",
    "Pulse Secure", "SonicWall", "Palo Alto", "PAN-OS", "Cisco IOS", "Cisco ASA",
    "Cisco", "Juniper", "F5 BIG-IP", "BIG-IP", "Zyxel", "QNAP", "Synology",
    "Confluence", "Jira", "Bitbucket", "Jenkins", "GitLab", "GitHub",
    "WordPress", "Drupal", "Joomla", "Magento", "Apache Struts", "Apache Tomcat",
    "Apache", "nginx", "OpenSSL", "OpenSSH", "Log4j", "Spring Framework",
    "Kubernetes", "Docker", "Oracle", "SAP", "MOVEit", "GoAnywhere", "Accellion",
    "ScreenConnect", "ConnectWise", "TeamViewer", "AnyDesk", "Zoom", "Slack",
    "Salesforce", "ServiceNow", "Veeam", "Zimbra", "Roundcube", "PostgreSQL",
    "MySQL", "MongoDB", "Redis", "Elasticsearch", "Jetty", "WebLogic",
]
# When a specific product matches, naming its vendor too is noise. Listing
# "FortiOS, Fortinet" in a post reads like the extractor is padding.
VENDOR_ROLLUP = {
    "Fortinet": {"Fortinet FortiOS", "FortiOS", "FortiGate"},
    "Cisco": {"Cisco IOS", "Cisco ASA"},
    "Citrix": {"Citrix NetScaler"},
    "VMware": {"VMware ESXi", "VMware vCenter"},
    "Palo Alto": {"PAN-OS"},
    "Apache": {"Apache Struts", "Apache Tomcat"},
    "F5 BIG-IP": {"BIG-IP"},
    "Windows": {"Windows Server", "Windows 11", "Windows 10"},
    "Linux": {"Linux kernel"},
    "Exchange Server": {"Microsoft Exchange"},
}

PRODUCT_RES = [
    (p, re.compile(r"(?<![\w-])" + re.escape(p) + r"(?![\w-])", re.IGNORECASE))
    for p in PRODUCTS
]


def _negated_patch(text: str) -> bool:
    """True when the text says a patch has not landed."""
    return any(_negated(text, m.start()) for m in PATCH_RE.finditer(text))


@dataclass
class Facts:
    cves: List[str] = field(default_factory=list)
    cvss_max: Optional[float] = None
    exploited: bool = False
    exploitation_ruled_out: bool = False
    kev: bool = False
    poc_public: bool = False
    patch_available: Optional[bool] = None
    products: List[str] = field(default_factory=list)
    counts: List[str] = field(default_factory=list)

    def any(self) -> bool:
        return bool(
            self.cves
            or self.cvss_max is not None
            or self.exploited
            or self.kev
            or self.poc_public
            or self.patch_available is not None
            or self.products
            or self.counts
        )


def _clean_number(raw: str, scale: Optional[str], noun: str) -> str:
    number = raw.strip().rstrip(".")
    scale_part = f" {scale.lower()}" if scale else ""
    return f"{number}{scale_part} {noun.lower()}"


def extract_facts(*texts: str) -> Facts:
    """Read facts out of any number of article texts, merged and deduped."""
    facts = Facts()
    raw = "\n".join(t for t in texts if t)
    if not raw.strip():
        return facts

    # Collapse every run of whitespace to one space. Article text wraps wherever
    # the outlet felt like it, and a pattern written with literal spaces misses
    # "no\nevidence of exploitation" while matching the same words on one line.
    blob = " ".join(raw.split())

    seen_cves: List[str] = []
    for match in CVE_RE.findall(blob):
        cve = match.upper()
        if cve not in seen_cves:
            seen_cves.append(cve)
    facts.cves = seen_cves

    scores: List[float] = []
    for pattern in CVSS_RES:
        for raw in pattern.findall(blob):
            try:
                value = float(raw)
            except ValueError:
                continue
            # A CVSS score lives in 0.0-10.0. Anything else matched a year,
            # a version number, or a price.
            if 0.0 <= value <= 10.0:
                scores.append(value)
    if scores:
        facts.cvss_max = max(scores)

    facts.exploitation_ruled_out = bool(NOT_EXPLOITED_RE.search(blob))
    facts.exploited = (
        _positive_match(EXPLOITED_RE, blob) and not facts.exploitation_ruled_out
    )
    facts.kev = _positive_match(KEV_RE, blob)
    facts.poc_public = _positive_match(POC_RE, blob)

    # Denial wins over availability. Getting this backwards would put "Patch
    # available" on a story about a bug with no patch, which is worse than
    # saying nothing at all.
    if NO_PATCH_RE.search(blob) or _negated_patch(blob):
        facts.patch_available = False
    elif _positive_match(PATCH_RE, blob):
        facts.patch_available = True

    found: List[str] = []
    for name, pattern in PRODUCT_RES:
        if pattern.search(blob):
            found.append(name)

    # Drop a vendor once one of its own products is already on the list.
    for vendor, specifics in VENDOR_ROLLUP.items():
        if vendor in found and any(s in found for s in specifics):
            found.remove(vendor)
    # Drop a name wholly contained in another match: "Windows" under
    # "Windows Server", "Apache" under "Apache Tomcat".
    redundant = {
        a
        for a in found
        for b in found
        if a != b and re.search(r"(?<![\w-])" + re.escape(a) + r"(?![\w-])", b, re.I)
    }
    found = [f for f in found if f not in redundant]
    facts.products = found[:6]

    counts: List[str] = []
    for raw, scale, noun in COUNT_RE.findall(blob):
        # Small bare numbers are noise: "3 flaws", "2 weeks".
        digits = raw.replace(",", "")
        try:
            value = float(digits)
        except ValueError:
            continue
        if not scale and value < 100:
            continue
        text = _clean_number(raw, scale or None, noun)
        if text not in counts:
            counts.append(text)
    facts.counts = counts[:4]

    return facts


def _lines(facts: Facts) -> List[str]:
    """The facts as plain sentences, ready for any markup."""
    out: List[str] = []

    if facts.cves:
        cve_text = ", ".join(facts.cves[:6])
        if len(facts.cves) > 6:
            cve_text += f" and {len(facts.cves) - 6} more"
        if facts.cvss_max is not None:
            cve_text += f" (CVSS {facts.cvss_max:g})"
        out.append(f"CVEs: {cve_text}")
    elif facts.cvss_max is not None:
        out.append(f"CVSS: {facts.cvss_max:g}")

    if facts.exploited:
        out.append("Exploited in the wild")
    elif facts.exploitation_ruled_out:
        out.append("No reported exploitation")

    if facts.kev:
        out.append("Listed in the CISA KEV catalog")
    if facts.poc_public:
        out.append("Exploit code is public")

    if facts.patch_available is True:
        out.append("Patch available")
    elif facts.patch_available is False:
        out.append("No patch yet")

    if facts.products:
        out.append("Affects: " + ", ".join(facts.products))
    if facts.counts:
        out.append("Scale: " + ", ".join(facts.counts))

    return out


def render_facts(facts: Facts, fmt: str = "bbcode", heading: str = "Key facts") -> str:
    """
    A facts block, or an empty string when there is nothing worth printing.

    Returning empty matters: a template carrying {facts_bbcode} on a story with
    no CVEs and no numbers should render nothing at all, not a bare heading over
    an empty list.
    """
    lines = _lines(facts)
    if not lines:
        return ""

    if fmt == "bbcode":
        body = "\n".join(f"[*]{line}" for line in lines)
        return f"[b]{heading}[/b]\n[list]\n{body}\n[/list]\n"
    if fmt == "markdown":
        body = "\n".join(f"- {line}" for line in lines)
        return f"**{heading}**\n{body}\n"
    body = "\n".join(f"- {line}" for line in lines)
    return f"{heading}:\n{body}\n"
