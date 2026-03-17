"""CSV file import source — works without any API keys."""

import csv
import os
from datetime import datetime

from ..models import Company, FilterConfig
from .base import CompanySource


# Column aliases: maps alternative header names → canonical field name
_COLUMN_ALIASES = {
    "company_name": "name",
    "company": "name",
    "organization": "name",
    "website": "domain",
    "url": "domain",
    "homepage": "domain",
    "country": "hq_country",
    "headquarters_country": "hq_country",
    "state": "hq_state",
    "city": "hq_city",
    "employees": "employee_count",
    "headcount": "employee_count",
    "num_employees": "employee_count",
    "revenue": "revenue_usd",
    "annual_revenue": "revenue_usd",
    "arr": "revenue_usd",
    "customers": "customer_count",
    "num_customers": "customer_count",
    "linkedin": "linkedin_url",
    "linkedin_url": "linkedin_url",
    "crunchbase": "crunchbase_url",
}

# Minimum required columns (at least one of each group must be present)
_REQUIRED = {"name", "domain"}


class CsvSource(CompanySource):
    """
    Reads companies from a CSV file.

    Supported columns (case-insensitive, flexible names):
        name / company_name / company / organization
        domain / website / url / homepage
        hq_country / country / headquarters_country
        hq_state / state
        hq_city / city
        employee_count / employees / headcount / num_employees
        revenue_usd / revenue / annual_revenue / arr
        customer_count / customers / num_customers
        industry
        linkedin_url / linkedin
        crunchbase_url / crunchbase

    All columns are optional except name and domain.
    """

    def __init__(self, csv_path: str):
        self._path = csv_path

    @property
    def name(self) -> str:
        return "csv"

    def search(self, filters: FilterConfig, max_results: int) -> list:
        if not os.path.exists(self._path):
            raise FileNotFoundError(
                f"CSV input file not found: {self._path}\n"
                f"Create a CSV with columns: name, domain, hq_country, "
                f"employee_count, revenue_usd, industry"
            )

        companies = []
        with open(self._path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            # Normalize header names
            field_map = self._build_field_map(reader.fieldnames or [])
            missing = _REQUIRED - set(field_map.values())
            if missing:
                raise ValueError(
                    f"CSV is missing required columns: {', '.join(missing)}\n"
                    f"Found columns: {', '.join(reader.fieldnames or [])}"
                )

            for row in reader:
                company = self._parse_row(row, field_map)
                if company:
                    companies.append(company)

                if len(companies) >= max_results * 3:
                    # Read more than needed to account for post-filter losses
                    break

        filtered = self._apply_post_filters(companies, filters)
        return filtered[:max_results]

    def _build_field_map(self, headers: list) -> dict:
        """Map normalized header names to canonical field names."""
        field_map = {}
        for h in headers:
            normalized = h.lower().strip().replace(" ", "_").replace("-", "_")
            canonical = _COLUMN_ALIASES.get(normalized, normalized)
            field_map[h] = canonical
        return field_map

    def _parse_row(self, row: dict, field_map: dict) -> Company:
        """Parse a CSV row into a Company object."""
        data = {}
        for raw_key, value in row.items():
            canonical = field_map.get(raw_key, raw_key.lower())
            data[canonical] = value.strip() if value else ""

        name = data.get("name", "").strip()
        domain = data.get("domain", "").strip()
        if not name or not domain:
            return None

        # Normalize domain
        domain = domain.lower()
        for prefix in ("https://", "http://", "www."):
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        domain = domain.rstrip("/")

        company = Company(
            name=name,
            domain=domain,
            hq_country=data.get("hq_country", "").upper()[:2] or "",
            hq_state=data.get("hq_state", ""),
            hq_city=data.get("hq_city", ""),
            industry=data.get("industry", ""),
            linkedin_url=data.get("linkedin_url") or None,
            crunchbase_url=data.get("crunchbase_url") or None,
            source="csv",
            enrichment_timestamp=datetime.utcnow(),
        )

        company.employee_count = _parse_int(data.get("employee_count"))
        company.revenue_usd = _parse_int(data.get("revenue_usd"))
        company.customer_count = _parse_int(data.get("customer_count"))

        return company


def _parse_int(value: str) -> int:
    """Parse an integer from a string, handling commas, $, K/M suffixes."""
    if not value:
        return None
    v = value.strip().replace(",", "").replace("$", "").replace(" ", "")
    if not v:
        return None
    try:
        if v.upper().endswith("M"):
            return int(float(v[:-1]) * 1_000_000)
        if v.upper().endswith("K"):
            return int(float(v[:-1]) * 1_000)
        return int(float(v))
    except (ValueError, TypeError):
        return None
