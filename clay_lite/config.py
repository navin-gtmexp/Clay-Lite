"""Configuration loader and credential store for Clay-Lite."""

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .models import (
    FilterConfig,
    GoogleSheetsConfig,
    OutputConfig,
    ProjectConfig,
    SourceConfig,
    TechDetectionConfig,
)


class ConfigLoader:
    """Loads and validates project JSON config files."""

    PROJECT_TEMPLATE = {
        "project_id": "my_research_project",
        "description": "Describe your research goal here",
        "filters": {
            "hq_country": ["US"],
            "industry_type": "B2B",
            "employee_count_min": 1,
            "employee_count_max": 999,
            "revenue_usd_min": 50000000,
            "revenue_usd_max": None,
            "min_customer_count": None,
            "industry_tags": [],
        },
        "tech_detection": {
            "enabled": True,
            "target_tools": ["Sisense", "Looker", "GoodData"],
            "detect_common_analytics": True,
        },
        "sources": {
            "primary": "csv",
            "fallback": None,
            "max_results": 500,
            "csv_input": "inputs/companies.csv",
        },
        "output": {
            "google_sheets": {
                "enabled": True,
                "spreadsheet_name": "Clay-Lite: My Research",
                "worksheet_name": None,
                "credentials_file": "~/.config/gspread/credentials.json",
                "share_with_emails": [],
            },
            "csv_enabled": True,
            "csv_filename": None,
        },
    }

    def load(self, path: str) -> ProjectConfig:
        """Load a project config from a JSON file."""
        with open(path) as f:
            raw = json.load(f)

        errors = self.validate(raw)
        if errors:
            raise ValueError(
                f"Config validation errors in {path}:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        return self._parse(raw)

    def validate(self, raw: dict) -> list:
        """Return a list of validation error messages (empty = valid)."""
        errors = []

        if not raw.get("project_id"):
            errors.append("project_id is required")

        filters = raw.get("filters", {})
        emp_min = filters.get("employee_count_min")
        emp_max = filters.get("employee_count_max")
        if emp_min is not None and emp_max is not None and emp_min > emp_max:
            errors.append(
                f"employee_count_min ({emp_min}) must be <= employee_count_max ({emp_max})"
            )

        rev_min = filters.get("revenue_usd_min")
        rev_max = filters.get("revenue_usd_max")
        if rev_min is not None and rev_max is not None and rev_min > rev_max:
            errors.append(
                f"revenue_usd_min ({rev_min}) must be <= revenue_usd_max ({rev_max})"
            )

        sources = raw.get("sources", {})
        if sources.get("max_results", 500) < 1:
            errors.append("sources.max_results must be >= 1")

        tech = raw.get("tech_detection", {})
        if tech.get("enabled") and not tech.get("target_tools"):
            errors.append(
                "tech_detection.target_tools must be non-empty when enabled=true"
            )

        output = raw.get("output", {})
        sheets = output.get("google_sheets", {})
        csv_on = output.get("csv_enabled", True)
        if not sheets.get("enabled", True) and not csv_on:
            errors.append("At least one output method (google_sheets or csv) must be enabled")

        return errors

    def _parse(self, raw: dict) -> ProjectConfig:
        f = raw.get("filters", {})
        filters = FilterConfig(
            hq_country=f.get("hq_country", ["US"]),
            industry_type=f.get("industry_type", "B2B"),
            employee_count_min=f.get("employee_count_min"),
            employee_count_max=f.get("employee_count_max"),
            revenue_usd_min=f.get("revenue_usd_min"),
            revenue_usd_max=f.get("revenue_usd_max"),
            min_customer_count=f.get("min_customer_count"),
            industry_tags=f.get("industry_tags", []),
        )

        t = raw.get("tech_detection", {})
        tech = TechDetectionConfig(
            enabled=t.get("enabled", True),
            target_tools=t.get("target_tools", ["Sisense", "Looker", "GoodData"]),
            detect_common_analytics=t.get("detect_common_analytics", True),
        )

        s = raw.get("sources", {})
        sources = SourceConfig(
            primary=s.get("primary", "csv"),
            fallback=s.get("fallback"),
            max_results=s.get("max_results", 500),
            csv_input=s.get("csv_input"),
        )

        o = raw.get("output", {})
        gs = o.get("google_sheets", {})
        sheets_config = GoogleSheetsConfig(
            enabled=gs.get("enabled", True),
            spreadsheet_name=gs.get("spreadsheet_name", "Clay-Lite Results"),
            worksheet_name=gs.get("worksheet_name"),
            credentials_file=gs.get(
                "credentials_file", "~/.config/gspread/credentials.json"
            ),
            share_with_emails=gs.get("share_with_emails", []),
        )
        output_config = OutputConfig(
            google_sheets=sheets_config,
            csv_enabled=o.get("csv_enabled", True),
            csv_filename=o.get("csv_filename"),
        )

        return ProjectConfig(
            project_id=raw["project_id"],
            description=raw.get("description", ""),
            filters=filters,
            tech_detection=tech,
            sources=sources,
            output=output_config,
        )

    def create_template(self, path: str, project_id: str, name: Optional[str] = None):
        """Write a new project template JSON to disk."""
        template = dict(self.PROJECT_TEMPLATE)
        template["project_id"] = project_id
        if name:
            template["description"] = name
            template["output"]["google_sheets"]["spreadsheet_name"] = (
                f"Clay-Lite: {name}"
            )
        with open(path, "w") as f:
            json.dump(template, f, indent=2)

    def list_projects(self, directory: str = "projects") -> list:
        """Return a list of project JSON paths in the given directory."""
        p = Path(directory)
        if not p.exists():
            return []
        return sorted(str(f) for f in p.glob("*.json"))


class CredentialStore:
    """Loads and validates API keys from .env."""

    def __init__(self, env_path: str = ".env"):
        load_dotenv(env_path, override=False)

    @property
    def apollo_api_key(self) -> Optional[str]:
        return os.getenv("APOLLO_API_KEY") or None

    @property
    def crunchbase_api_key(self) -> Optional[str]:
        return os.getenv("CRUNCHBASE_API_KEY") or None

    @property
    def builtwith_api_key(self) -> Optional[str]:
        return os.getenv("BUILTWITH_API_KEY") or None

    @property
    def google_credentials_file(self) -> str:
        raw = os.getenv("GOOGLE_CREDENTIALS_FILE", "~/.config/gspread/credentials.json")
        return str(Path(raw).expanduser())

    def available_sources(self) -> list:
        sources = ["csv"]
        if self.apollo_api_key:
            sources.append("apollo")
        if self.crunchbase_api_key:
            sources.append("crunchbase")
        return sources

    def google_sheets_ready(self) -> bool:
        creds_path = Path(self.google_credentials_file)
        token_path = creds_path.parent / "authorized_user.json"
        return creds_path.exists() or token_path.exists()

    def print_status(self):
        print("\n  Data Sources:")
        print(f"    Apollo.io    : {'✓ API key found' if self.apollo_api_key else '✗ No key (set APOLLO_API_KEY in .env)'}")
        print(f"    Crunchbase   : {'✓ API key found' if self.crunchbase_api_key else '✗ No key (set CRUNCHBASE_API_KEY in .env)'}")
        print(f"    BuiltWith    : {'✓ API key found' if self.builtwith_api_key else '- No key (free scraper will be used)'}")
        print(f"    CSV import   : ✓ Always available")
        print(f"\n  Google Sheets:")
        creds_path = Path(self.google_credentials_file)
        token_path = creds_path.parent / "authorized_user.json"
        if token_path.exists():
            print(f"    ✓ Authorized (token found at {token_path})")
        elif creds_path.exists():
            print(f"    ~ Credentials file found — will prompt for browser login on first run")
        else:
            print(f"    ✗ No credentials ({creds_path})")
            print(f"      → See README.md for Google Sheets setup instructions")
