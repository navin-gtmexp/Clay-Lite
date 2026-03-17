"""
Free HTML scraper for detecting analytics/BI tool usage.

Scans company homepages for JavaScript CDN signatures, script src attributes,
and embedded iframe patterns to detect which tools a company uses.

No API key required. Coverage is best for tools with client-side embeds.
"""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import Company, TechDetectionConfig
from .base import CompanyEnricher

# ─── Tool signature definitions ───────────────────────────────────────────────
# Each entry: tool_name -> list of strings to search for in HTML/scripts.
# Matched case-insensitively against:
#   - <script src="..."> attributes
#   - <iframe src="..."> attributes
#   - <link href="..."> attributes
#   - Inline JavaScript text (limited, only obvious patterns)

TOOL_SIGNATURES: dict[str, list[str]] = {
    # Primary targets
    "Sisense": [
        "cdn.sisense.com",
        "sisense.com/js/",
        "sisense/embed",
        "sisense.js",
        "SisensePrism",
        "/sisense/",
        "app.sisense.com/embed",
    ],
    "Looker": [
        "looker.com/embed",
        "lookercdn.com",
        "looker_embed",
        "looker.js",
        "/embed/explore",
        "/embed/dashboards",
        "me.looker.com",
        "looker-custom-viz",
    ],
    "GoodData": [
        "secure.gooddata.com",
        "sdk.gooddata.com",
        "gooddata.com/lib/",
        "gooddata.com/js/",
        "gooddata-ui",
        "gd-sdk",
    ],
    # Common analytics/BI tools (detected if detect_common_analytics=True)
    "Tableau": [
        "tableau.com/javascriptapi",
        "tableau.com/embed",
        "tableauPublic.js",
        "tableau.js",
        "public.tableau.com",
        "online.tableau.com",
        "tableau-analytics",
    ],
    "Power BI": [
        "powerbi.com/reportEmbed",
        "app.powerbi.com/embed",
        "powerbi.js",
        "powerbi-client",
        "microsoft.com/embed/reportEmbed",
    ],
    "Metabase": [
        "metabase.io/embed",
        "metabase.com/embed",
        "/metabase/embed",
        "metabase-embed",
    ],
    "Domo": [
        "domo.com/embed",
        "embed.domo.com",
        "domostats.com",
    ],
    "Qlik": [
        "qlik.com/embed",
        "qlikcloud.com",
        "qliksense",
        "qlikview",
        "qlik.js",
    ],
    "ThoughtSpot": [
        "thoughtspot.com/embed",
        "thoughtspot-everywhere",
        "ts-embed",
    ],
    "MicroStrategy": [
        "microstrategy.com",
        "microstrategy-embed",
        "mstrweb",
    ],
    "Chartio": [
        "chartio.com/embed",
        "chartio-embed",
    ],
    "Redash": [
        "redash.io/embed",
        "/embed/query",
    ],
    "Superset": [
        "superset.apache.org",
        "superset-embed",
        "apache-superset",
    ],
}

# Tools always detected regardless of target_tools (common category signals)
_ALWAYS_DETECT = set(TOOL_SIGNATURES.keys())

_REQUEST_TIMEOUT = 10  # seconds
_USER_AGENT = (
    "Mozilla/5.0 (compatible; ClayLiteBot/1.0; +https://github.com/clay-lite)"
)


class ScraperEnricher(CompanyEnricher):
    """
    Detects analytics/BI tools by scraping a company's public homepage.

    Strategy:
      1. Fetch the homepage HTML (HTTPS first, then HTTP fallback)
      2. Scan all <script src>, <iframe src>, <link href> attributes
      3. Scan inline script content for known patterns
      4. Match against TOOL_SIGNATURES using case-insensitive substring search
    """

    def __init__(self, config: TechDetectionConfig):
        self._config = config
        self._target_tools = set(config.target_tools)

    @property
    def name(self) -> str:
        return "scraper"

    def enrich(self, company: Company) -> Company:
        if not company.domain:
            company.enrichment_errors.append("scraper: no domain available")
            company.tech_detection_source = "none"
            return company

        html = self._fetch_homepage(company.domain)
        if html is None:
            company.tech_detection_source = "none"
            return company

        detected = self._scan(html)

        # Decide which tools to scan
        if self._config.detect_common_analytics:
            scan_tools = _ALWAYS_DETECT
        else:
            scan_tools = self._target_tools

        matched = {tool for tool in scan_tools if tool in detected}

        company.detected_tools = sorted(matched)
        company.tech_detection_source = "scraper"
        company.enrichment_timestamp = datetime.utcnow()

        # Set specific flags for the primary target tools
        company.uses_sisense = "Sisense" in matched if "Sisense" in scan_tools else None
        company.uses_looker = "Looker" in matched if "Looker" in scan_tools else None
        company.uses_gooddata = "GoodData" in matched if "GoodData" in scan_tools else None

        return company

    def _fetch_homepage(self, domain: str) -> Optional[str]:
        """Try HTTPS then HTTP. Return HTML string or None on failure."""
        urls = [f"https://{domain}", f"http://{domain}"]
        for url in urls:
            try:
                resp = requests.get(
                    url,
                    headers={"User-Agent": _USER_AGENT},
                    timeout=_REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                if resp.status_code < 400:
                    return resp.text
            except requests.exceptions.SSLError:
                continue  # Try HTTP fallback
            except requests.exceptions.ConnectionError:
                continue
            except requests.exceptions.Timeout:
                continue
            except Exception:
                continue
        return None

    def _scan(self, html: str) -> set:
        """Scan HTML for all known tool signatures. Returns set of matched tool names."""
        soup = BeautifulSoup(html, "lxml")
        matched = set()

        # Collect all URLs from resource tags
        resource_urls = []
        for tag in soup.find_all(["script", "iframe", "link", "img"]):
            for attr in ("src", "href", "data-src"):
                val = tag.get(attr, "")
                if val:
                    resource_urls.append(val.lower())

        # Collect inline script content (limited — just look for obvious identifiers)
        inline_scripts = []
        for script in soup.find_all("script"):
            if not script.get("src") and script.string:
                inline_scripts.append(script.string.lower())

        combined_resources = " ".join(resource_urls)
        combined_inline = " ".join(inline_scripts)

        for tool, sigs in TOOL_SIGNATURES.items():
            for sig in sigs:
                sig_lower = sig.lower()
                if sig_lower in combined_resources:
                    matched.add(tool)
                    break
                # Also check inline scripts for some patterns
                if sig_lower in combined_inline:
                    matched.add(tool)
                    break

        return matched
