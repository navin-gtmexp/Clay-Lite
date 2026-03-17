"""Core data models for Clay-Lite."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Company:
    """Represents a single company record, including enrichment data."""

    # Identity
    name: str
    domain: str  # Normalized domain — used as the dedup key

    # Location
    hq_country: str = ""
    hq_city: str = ""
    hq_state: str = ""

    # Firmographics
    employee_count: Optional[int] = None
    revenue_usd: Optional[int] = None
    industry: str = ""
    customer_count: Optional[int] = None

    # Tech detection (None = not yet checked)
    uses_sisense: Optional[bool] = None
    uses_looker: Optional[bool] = None
    uses_gooddata: Optional[bool] = None
    detected_tools: list = field(default_factory=list)  # All matched tools
    tech_detection_source: Optional[str] = None  # "scraper" | "builtwith" | "none"

    # Source metadata
    source: str = ""  # "apollo" | "crunchbase" | "csv"
    source_id: Optional[str] = None
    linkedin_url: Optional[str] = None
    crunchbase_url: Optional[str] = None

    # Enrichment metadata
    enrichment_timestamp: Optional[datetime] = None
    enrichment_errors: list = field(default_factory=list)

    def normalize_domain(self) -> str:
        """Return a normalized version of the domain for deduplication."""
        d = self.domain.lower().strip()
        for prefix in ("https://", "http://", "www."):
            if d.startswith(prefix):
                d = d[len(prefix):]
        return d.rstrip("/")


@dataclass
class FilterConfig:
    """Filter criteria for a research project."""

    hq_country: list = field(default_factory=lambda: ["US"])
    industry_type: str = "B2B"  # "B2B" | "B2C" | "both"
    employee_count_min: Optional[int] = 1
    employee_count_max: Optional[int] = 999
    revenue_usd_min: Optional[int] = 50_000_000
    revenue_usd_max: Optional[int] = None
    min_customer_count: Optional[int] = None
    industry_tags: list = field(default_factory=list)  # e.g. ["SaaS", "Analytics"]


@dataclass
class TechDetectionConfig:
    """Configuration for tech/competitor detection."""

    enabled: bool = True
    target_tools: list = field(
        default_factory=lambda: ["Sisense", "Looker", "GoodData"]
    )
    # Also detect these common analytics tools even if not in target_tools
    detect_common_analytics: bool = True


@dataclass
class SourceConfig:
    """Data source configuration."""

    primary: str = "csv"  # "apollo" | "crunchbase" | "csv"
    fallback: Optional[str] = None
    max_results: int = 500
    csv_input: Optional[str] = None  # Path to CSV file (for "csv" source)


@dataclass
class GoogleSheetsConfig:
    """Google Sheets export configuration."""

    enabled: bool = True
    spreadsheet_name: str = "Clay-Lite Results"
    worksheet_name: Optional[str] = None  # Auto-generated if None (timestamp-based)
    credentials_file: str = "~/.config/gspread/credentials.json"
    share_with_emails: list = field(default_factory=list)


@dataclass
class OutputConfig:
    """Output configuration."""

    google_sheets: GoogleSheetsConfig = field(default_factory=GoogleSheetsConfig)
    csv_enabled: bool = True
    csv_filename: Optional[str] = None  # Auto-generated if None


@dataclass
class ProjectConfig:
    """Full configuration for a research project."""

    project_id: str
    description: str = ""
    filters: FilterConfig = field(default_factory=FilterConfig)
    tech_detection: TechDetectionConfig = field(default_factory=TechDetectionConfig)
    sources: SourceConfig = field(default_factory=SourceConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


@dataclass
class RunResult:
    """Result of a completed project run."""

    project_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_found: int = 0
    total_enriched: int = 0
    total_exported: int = 0
    uses_sisense_count: int = 0
    uses_looker_count: int = 0
    uses_gooddata_count: int = 0
    errors: list = field(default_factory=list)
    sheet_url: Optional[str] = None
    csv_path: Optional[str] = None
