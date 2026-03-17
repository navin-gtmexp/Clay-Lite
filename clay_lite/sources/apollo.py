"""Apollo.io API source for company search."""

import time
from datetime import datetime
from typing import Optional

import requests

from ..models import Company, FilterConfig
from .base import CompanySource

APOLLO_BASE_URL = "https://api.apollo.io/api/v1"

# Apollo revenue range strings (min, max in USD)
# Apollo uses pre-defined ranges — we pick the closest match
_REVENUE_RANGE_MAP = [
    (0, 1_000_000, "1,1000000"),
    (1_000_000, 10_000_000, "1000000,10000000"),
    (10_000_000, 50_000_000, "10000000,50000000"),
    (50_000_000, 100_000_000, "50000000,100000000"),
    (100_000_000, 500_000_000, "100000000,500000000"),
    (500_000_000, 1_000_000_000, "500000000,1000000000"),
    (1_000_000_000, None, "1000000000,"),
]


class ApolloSource(CompanySource):
    """
    Searches for companies via the Apollo.io API.

    Requires APOLLO_API_KEY environment variable.
    Free tier: 50 requests/minute, limited fields.
    Paid tier: higher limits + more data fields.
    """

    def __init__(self, api_key: str, rate_limit_delay: float = 1.5):
        self._api_key = api_key
        self._delay = rate_limit_delay

    @property
    def name(self) -> str:
        return "apollo"

    def search(self, filters: FilterConfig, max_results: int) -> list:
        companies = []
        page = 1
        per_page = min(100, max_results)

        while len(companies) < max_results:
            payload = self._build_payload(filters, page, per_page)
            try:
                batch = self._fetch_page(payload)
            except requests.HTTPError as e:
                print(f"  [Apollo] HTTP error on page {page}: {e}")
                break

            if not batch:
                break

            companies.extend(batch)
            page += 1
            time.sleep(self._delay)

            if len(batch) < per_page:
                break  # Last page

        return self._apply_post_filters(companies, filters)[:max_results]

    def _build_payload(self, filters: FilterConfig, page: int, per_page: int) -> dict:
        payload = {
            "page": page,
            "per_page": per_page,
        }

        # Country filter
        if filters.hq_country:
            payload["organization_locations"] = [
                _country_code_to_apollo(c) for c in filters.hq_country
            ]

        # Employee count
        if filters.employee_count_min is not None or filters.employee_count_max is not None:
            lo = filters.employee_count_min or 1
            hi = filters.employee_count_max or 999999
            payload["organization_num_employees_ranges"] = [f"{lo},{hi}"]

        # Revenue ranges (Apollo uses predefined buckets)
        rev_ranges = _pick_revenue_ranges(
            filters.revenue_usd_min, filters.revenue_usd_max
        )
        if rev_ranges:
            payload["organization_annual_revenue_ranges"] = rev_ranges

        # Industry tags
        if filters.industry_tags:
            payload["organization_industry_tag_ids"] = filters.industry_tags

        return payload

    def _fetch_page(self, payload: dict) -> list:
        resp = requests.post(
            f"{APOLLO_BASE_URL}/mixed_companies/search",
            json=payload,
            headers={
                "Cache-Control": "no-cache",
                "Content-Type": "application/json",
                "x-api-key": self._api_key,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        organizations = data.get("organizations", [])
        return [self._parse_org(org) for org in organizations if org]

    def _parse_org(self, org: dict) -> Company:
        domain = org.get("primary_domain") or org.get("website_url") or ""
        domain = domain.lower().replace("http://", "").replace("https://", "").replace("www.", "").rstrip("/")

        return Company(
            name=org.get("name", ""),
            domain=domain,
            hq_country=_extract_country(org),
            hq_city=org.get("city", ""),
            hq_state=org.get("state", ""),
            employee_count=org.get("estimated_num_employees"),
            revenue_usd=_parse_revenue(org.get("annual_revenue")),
            industry=org.get("industry", ""),
            linkedin_url=org.get("linkedin_url"),
            source="apollo",
            source_id=org.get("id"),
            enrichment_timestamp=datetime.utcnow(),
        )


def _country_code_to_apollo(code: str) -> str:
    """Convert ISO country code to Apollo location string."""
    mapping = {
        "US": "United States",
        "GB": "United Kingdom",
        "CA": "Canada",
        "AU": "Australia",
        "DE": "Germany",
        "FR": "France",
        "IN": "India",
    }
    return mapping.get(code.upper(), code)


def _extract_country(org: dict) -> str:
    country = org.get("country") or ""
    # Apollo sometimes returns full country names
    mapping = {
        "United States": "US",
        "United Kingdom": "GB",
        "Canada": "CA",
        "Australia": "AU",
        "Germany": "DE",
        "France": "FR",
        "India": "IN",
    }
    return mapping.get(country, country[:2].upper() if len(country) >= 2 else country)


def _parse_revenue(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pick_revenue_ranges(min_rev: Optional[int], max_rev: Optional[int]) -> list:
    """Select Apollo revenue range strings that overlap with [min_rev, max_rev]."""
    if min_rev is None and max_rev is None:
        return []
    ranges = []
    for lo, hi, label in _REVENUE_RANGE_MAP:
        range_lo = lo
        range_hi = hi if hi is not None else float("inf")
        filter_lo = min_rev if min_rev is not None else 0
        filter_hi = max_rev if max_rev is not None else float("inf")
        if range_lo < filter_hi and range_hi > filter_lo:
            ranges.append(label)
    return ranges
