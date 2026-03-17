"""
Google Sheets exporter using OAuth browser-based login.

First-time setup:
  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable "Google Sheets API" and "Google Drive API"
  3. Credentials → Create Credentials → OAuth 2.0 Client ID → Desktop app
  4. Download the JSON and save it to: ~/.config/gspread/credentials.json

On the first run, a browser window will open for you to authorize access.
The token is saved to ~/.config/gspread/authorized_user.json and reused automatically.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..models import Company, ProjectConfig

# Column definitions matching csv_exporter.py layout
# (header, accessor, format_hint)
COLUMNS = [
    ("Company Name", lambda c, _: c.name, None),
    ("Website", lambda c, _: f"https://{c.domain}" if c.domain else "", "url"),
    ("HQ Country", lambda c, _: c.hq_country, None),
    ("HQ State", lambda c, _: c.hq_state, None),
    ("HQ City", lambda c, _: c.hq_city, None),
    ("Employees", lambda c, _: c.employee_count, "number"),
    ("Revenue (USD)", lambda c, _: c.revenue_usd, "currency"),
    ("Industry", lambda c, _: c.industry, None),
    ("Customer Count", lambda c, _: c.customer_count, "number"),
    ("Uses Sisense", lambda c, _: _bool_to_yesno(c.uses_sisense), "yesno"),
    ("Uses Looker", lambda c, _: _bool_to_yesno(c.uses_looker), "yesno"),
    ("Uses GoodData", lambda c, _: _bool_to_yesno(c.uses_gooddata), "yesno"),
    (
        "Other Analytics Tools",
        lambda c, _: ", ".join(
            t for t in c.detected_tools if t not in ("Sisense", "Looker", "GoodData")
        ),
        None,
    ),
    ("Tech Detection Source", lambda c, _: c.tech_detection_source or "", None),
    ("LinkedIn", lambda c, _: c.linkedin_url or "", None),
    ("Data Source", lambda c, _: c.source, None),
    (
        "Enrichment Date",
        lambda c, _: (
            c.enrichment_timestamp.strftime("%Y-%m-%d %H:%M UTC")
            if c.enrichment_timestamp
            else ""
        ),
        None,
    ),
    ("Enrichment Errors", lambda c, _: "; ".join(c.enrichment_errors), None),
    ("Project ID", lambda c, pid: pid, None),
]

# Conditional formatting colors
_GREEN = {"red": 0.718, "green": 0.882, "blue": 0.804}  # #B7E1CC
_RED = {"red": 0.957, "green": 0.800, "blue": 0.800}    # #F4CCCC


def _bool_to_yesno(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unknown"


class GoogleSheetsExporter:
    """
    Exports research results to Google Sheets using OAuth browser login.

    Requires gspread and google-auth-oauthlib to be installed.
    """

    def __init__(self, credentials_file: str):
        self._credentials_file = str(Path(credentials_file).expanduser())

    def export(self, companies: list, config: ProjectConfig) -> Optional[str]:
        """
        Write companies to a Google Sheet. Returns the sheet URL.
        Creates the spreadsheet if it doesn't exist.
        Opens a browser for OAuth on first run.
        """
        try:
            import gspread
        except ImportError:
            raise RuntimeError(
                "gspread is not installed. Run: pip install gspread google-auth-oauthlib"
            )

        gc = self._authenticate()
        sheet_config = config.output.google_sheets
        spreadsheet_name = sheet_config.spreadsheet_name

        # Get or create the spreadsheet
        try:
            spreadsheet = gc.open(spreadsheet_name)
        except Exception:
            spreadsheet = gc.create(spreadsheet_name)
            print(f"  Created new spreadsheet: {spreadsheet_name}")

        # Share with additional emails if configured
        for email in sheet_config.share_with_emails:
            try:
                spreadsheet.share(email, perm_type="user", role="writer")
            except Exception as e:
                print(f"  Warning: could not share with {email}: {e}")

        # Create a new worksheet for this run
        ws_name = sheet_config.worksheet_name or datetime.utcnow().strftime(
            "Results_%Y-%m-%d_%H%M"
        )

        # Check if worksheet already exists
        existing_titles = [ws.title for ws in spreadsheet.worksheets()]
        if ws_name in existing_titles:
            ws_name = ws_name + "_2"

        worksheet = spreadsheet.add_worksheet(title=ws_name, rows=len(companies) + 5, cols=len(COLUMNS))

        # Write headers + data
        headers = [col[0] for col in COLUMNS]
        rows = [headers]
        for company in companies:
            row = []
            for col_name, accessor, fmt in COLUMNS:
                try:
                    val = accessor(company, config.project_id)
                    row.append("" if val is None else val)
                except Exception:
                    row.append("")
            rows.append(row)

        worksheet.update(rows, value_input_option="USER_ENTERED")

        # Apply formatting
        self._format_worksheet(spreadsheet, worksheet, len(companies))

        # Also update/create a "Latest" worksheet that always shows the newest run
        self._update_latest_sheet(spreadsheet, companies, config)

        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}"
        return url

    def _authenticate(self):
        """Authenticate with Google using OAuth. Opens browser on first run."""
        import gspread

        creds_path = Path(self._credentials_file)
        token_path = creds_path.parent / "authorized_user.json"

        if not creds_path.exists() and not token_path.exists():
            raise FileNotFoundError(
                f"Google credentials not found at: {self._credentials_file}\n\n"
                "Setup instructions:\n"
                "  1. Go to https://console.cloud.google.com/\n"
                "  2. Create a project → Enable 'Google Sheets API' and 'Google Drive API'\n"
                "  3. Credentials → Create Credentials → OAuth 2.0 Client ID → Desktop app\n"
                "  4. Download the JSON and save it to:\n"
                f"     {self._credentials_file}\n\n"
                "Then re-run clay_lite — a browser window will open for authorization."
            )

        return gspread.oauth(
            credentials_filename=str(creds_path),
            authorized_user_filename=str(token_path),
        )

    def _format_worksheet(self, spreadsheet, worksheet, num_data_rows: int):
        """Apply header formatting and conditional formatting for Yes/No columns."""
        try:
            import gspread.utils as gu

            sheet_id = worksheet.id

            requests_body = []

            # Freeze header row
            requests_body.append({
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            })

            # Bold header row
            requests_body.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            })

            # Conditional formatting for Yes/No columns (J=9, K=10, L=11, 0-indexed)
            for col_idx in [9, 10, 11]:
                col_letter = chr(ord("A") + col_idx)
                for value, color in [("Yes", _GREEN), ("No", _RED)]:
                    requests_body.append({
                        "addConditionalFormatRule": {
                            "rule": {
                                "ranges": [{
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1,
                                    "endRowIndex": num_data_rows + 1,
                                    "startColumnIndex": col_idx,
                                    "endColumnIndex": col_idx + 1,
                                }],
                                "booleanRule": {
                                    "condition": {
                                        "type": "TEXT_EQ",
                                        "values": [{"userEnteredValue": value}],
                                    },
                                    "format": {"backgroundColor": color},
                                },
                            },
                            "index": 0,
                        }
                    })

            spreadsheet.batch_update({"requests": requests_body})
        except Exception as e:
            # Formatting is non-critical — log and continue
            print(f"  Warning: could not apply sheet formatting: {e}")

    def _update_latest_sheet(self, spreadsheet, companies: list, config: ProjectConfig):
        """Keep a 'Latest' worksheet that always reflects the most recent run."""
        try:
            existing_titles = [ws.title for ws in spreadsheet.worksheets()]
            if "Latest" in existing_titles:
                latest_ws = spreadsheet.worksheet("Latest")
                latest_ws.clear()
            else:
                latest_ws = spreadsheet.add_worksheet(
                    title="Latest", rows=len(companies) + 5, cols=len(COLUMNS)
                )

            headers = [col[0] for col in COLUMNS]
            rows = [headers]
            for company in companies:
                row = []
                for col_name, accessor, fmt in COLUMNS:
                    try:
                        val = accessor(company, config.project_id)
                        row.append("" if val is None else val)
                    except Exception:
                        row.append("")
                rows.append(row)

            latest_ws.update(rows, value_input_option="USER_ENTERED")
        except Exception as e:
            print(f"  Warning: could not update 'Latest' worksheet: {e}")
