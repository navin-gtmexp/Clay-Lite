"""CSV file exporter — always available, no authentication needed."""

import csv
import os
from datetime import datetime
from pathlib import Path

from ..models import Company, ProjectConfig

# Column definitions: (header_label, Company field accessor)
COLUMNS = [
    ("Company Name", lambda c: c.name),
    ("Website", lambda c: c.domain),
    ("HQ Country", lambda c: c.hq_country),
    ("HQ State", lambda c: c.hq_state),
    ("HQ City", lambda c: c.hq_city),
    ("Employees", lambda c: c.employee_count),
    ("Revenue (USD)", lambda c: c.revenue_usd),
    ("Industry", lambda c: c.industry),
    ("Customer Count", lambda c: c.customer_count),
    ("Uses Sisense", lambda c: _bool_to_yesno(c.uses_sisense)),
    ("Uses Looker", lambda c: _bool_to_yesno(c.uses_looker)),
    ("Uses GoodData", lambda c: _bool_to_yesno(c.uses_gooddata)),
    ("Other Analytics Tools", lambda c: ", ".join(
        t for t in c.detected_tools if t not in ("Sisense", "Looker", "GoodData")
    )),
    ("Tech Detection Source", lambda c: c.tech_detection_source or ""),
    ("LinkedIn", lambda c: c.linkedin_url or ""),
    ("Data Source", lambda c: c.source),
    ("Enrichment Date", lambda c: (
        c.enrichment_timestamp.strftime("%Y-%m-%d %H:%M UTC")
        if c.enrichment_timestamp else ""
    )),
    ("Enrichment Errors", lambda c: "; ".join(c.enrichment_errors)),
    ("Project ID", lambda c: ""),  # Filled in during export
]


class CsvExporter:
    """Writes company results to a local CSV file."""

    def __init__(self, output_dir: str = "outputs"):
        self._output_dir = output_dir

    def export(self, companies: list, config: ProjectConfig, filename: str = None) -> str:
        """Write companies to CSV. Returns the path of the created file."""
        os.makedirs(self._output_dir, exist_ok=True)

        if filename is None:
            timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M")
            filename = f"{config.project_id}_{timestamp}.csv"

        path = os.path.join(self._output_dir, filename)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([col[0] for col in COLUMNS])
            for company in companies:
                row = []
                for header, accessor in COLUMNS:
                    if header == "Project ID":
                        row.append(config.project_id)
                    else:
                        try:
                            row.append(accessor(company) if accessor(company) is not None else "")
                        except Exception:
                            row.append("")
                writer.writerow(row)

        return path


def _bool_to_yesno(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unknown"
