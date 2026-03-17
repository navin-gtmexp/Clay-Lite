# Clay-Lite

A lightweight, configurable account-based research tool — like Clay, but self-hosted and free to run.

Research B2B companies at scale, detect which analytics tools they use (Sisense, Looker, GoodData, Tableau, etc.), and export the results directly to Google Sheets.

---

## What It Does

1. **Pulls company lists** from Apollo.io (paid/free tier) or from a CSV file you provide
2. **Filters companies** by: revenue, employee count, HQ country, industry, customer count
3. **Detects analytics tools** each company uses by scanning their public website (free, no API key needed)
4. **Exports to Google Sheets** and/or a local CSV file

### Detected Tools
Sisense · Looker · GoodData · Tableau · Power BI · Metabase · Domo · Qlik · ThoughtSpot · MicroStrategy · Superset · Redash · Chartio

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Open .env and fill in any API keys you have (all optional except Google Sheets)
```

### 3. Set Up Google Sheets (One-Time)

> **Skip this step** if you only want CSV output. Pass `--no-sheets` when running.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable these two APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Go to **Credentials → Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Desktop app**
6. Download the JSON file and save it to:
   ```
   ~/.config/gspread/credentials.json
   ```
7. On your first `run`, a browser window will open to authorize access. After that, the token is saved automatically.

### 4. Create a Research Project

```bash
python -m clay_lite new-project --name my_research
```

This creates `projects/my_research.json`. Open it and configure your filters.

### 5. Check Your Setup

```bash
python -m clay_lite status
```

### 6. Run the Research

```bash
python -m clay_lite run projects/my_research.json
```

---

## Project Config Reference

Each research project is a JSON file in the `projects/` directory.

```json
{
  "project_id": "sisense_targets_us",
  "description": "USA B2B companies with $50M+ revenue, <1000 employees",

  "filters": {
    "hq_country": ["US"],
    "industry_type": "B2B",
    "employee_count_min": 1,
    "employee_count_max": 999,
    "revenue_usd_min": 50000000,
    "revenue_usd_max": null,
    "min_customer_count": null,
    "industry_tags": []
  },

  "tech_detection": {
    "enabled": true,
    "target_tools": ["Sisense", "Looker", "GoodData"],
    "detect_common_analytics": true
  },

  "sources": {
    "primary": "csv",
    "fallback": null,
    "max_results": 500,
    "csv_input": "inputs/companies.csv"
  },

  "output": {
    "google_sheets": {
      "enabled": true,
      "spreadsheet_name": "Clay-Lite: Sisense Targets",
      "worksheet_name": null,
      "credentials_file": "~/.config/gspread/credentials.json",
      "share_with_emails": []
    },
    "csv_enabled": true,
    "csv_filename": null
  }
}
```

### Filter Options

| Field | Type | Description |
|-------|------|-------------|
| `hq_country` | `["US"]` | ISO 2-letter country codes |
| `industry_type` | `"B2B"` | `"B2B"`, `"B2C"`, or `"both"` |
| `employee_count_min` | `int` | Minimum employees (inclusive) |
| `employee_count_max` | `int` | Maximum employees (inclusive) |
| `revenue_usd_min` | `int` | Minimum annual revenue in USD |
| `revenue_usd_max` | `int` or `null` | Maximum revenue (`null` = no limit) |
| `min_customer_count` | `int` or `null` | Minimum number of customers |
| `industry_tags` | `[]` | Industry tags to filter by (source-dependent) |

### Data Sources

| Source | Requires | Notes |
|--------|----------|-------|
| `csv` | A CSV file | Works immediately, no API key needed |
| `apollo` | `APOLLO_API_KEY` in `.env` | Rich B2B filters; free tier available |

**Using CSV mode:**
- Copy `inputs/companies_template.csv` to `inputs/companies.csv`
- Add your target companies (export from LinkedIn, CRM, etc.)
- Supported columns: `name`, `domain`, `hq_country`, `hq_state`, `hq_city`, `employee_count`, `revenue_usd`, `industry`, `customer_count`, `linkedin_url`

**Getting Apollo.io access (free tier):**
1. Sign up at [apollo.io](https://app.apollo.io)
2. Go to Settings → Integrations → API
3. Copy your API key
4. Add to `.env`: `APOLLO_API_KEY=your_key_here`
5. Change `sources.primary` to `"apollo"` in your project JSON

---

## Google Sheets Output Format

Each run creates a new timestamped worksheet in the spreadsheet. A `Latest` worksheet is always updated with the most recent results.

| Column | Content |
|--------|---------|
| A | Company Name |
| B | Website (clickable) |
| C | HQ Country |
| D | HQ State |
| E | HQ City |
| F | Employees |
| G | Revenue (USD) |
| H | Industry |
| I | Customer Count |
| J | Uses Sisense (`Yes`/`No`/`Unknown`) |
| K | Uses Looker |
| L | Uses GoodData |
| M | Other Analytics Tools Detected |
| N | Tech Detection Source |
| O | LinkedIn URL |
| P | Data Source |
| Q | Enrichment Date |
| R | Enrichment Errors |
| S | Project ID |

Columns J/K/L have conditional formatting: **green for Yes**, **red for No**.

---

## CLI Reference

```bash
# Check API/Sheets connection status
python -m clay_lite status

# Create a new project config from the template
python -m clay_lite new-project --name my_project
python -m clay_lite new-project --name my_project --description "Looker targets in the UK"

# Validate a config without running
python -m clay_lite validate projects/my_project.json

# Run a project
python -m clay_lite run projects/my_project.json

# Run without Google Sheets (CSV only)
python -m clay_lite run projects/my_project.json --no-sheets

# List all projects
python -m clay_lite list-projects
```

---

## Tech Detection: How It Works

Clay-Lite scans each company's public homepage for JavaScript CDN signatures, embedded iframe patterns, and script references.

**Example signals it looks for:**
- Sisense: `cdn.sisense.com`, `sisense/embed`, `SisensePrism`
- Looker: `lookercdn.com`, `looker.com/embed`, `looker_embed`
- GoodData: `secure.gooddata.com`, `sdk.gooddata.com`

**Coverage:**
- Works best for companies that embed analytics in their public website
- Companies that use analytics only internally may not be detected
- Detection source is always noted in column N so you know the confidence level

**Optional BuiltWith API** (higher accuracy):
- Sign up at [builtwith.com](https://api.builtwith.com/)
- Add to `.env`: `BUILTWITH_API_KEY=your_key_here`
- BuiltWith indexes technology usage across millions of sites

---

## Project Structure

```
Clay-Lite/
├── clay_lite/              # Main package
│   ├── cli.py              # Command-line interface
│   ├── runner.py           # Research pipeline orchestrator
│   ├── models.py           # Data models
│   ├── config.py           # Config loading + credential management
│   ├── sources/
│   │   ├── apollo.py       # Apollo.io API adapter
│   │   └── csv_source.py   # CSV file import
│   ├── enrichers/
│   │   └── scraper.py      # Free HTML scraper for tech detection
│   └── exporters/
│       ├── google_sheets.py # Google Sheets (OAuth)
│       └── csv_exporter.py  # Local CSV
├── projects/               # Your research project configs (JSON)
├── inputs/                 # CSV input files for CSV source mode
├── outputs/                # CSV output files
├── requirements.txt
└── .env.example
```

---

## Notes & Limitations

- **Customer count filter**: When using Apollo, the customer count filter is applied *after* fetching results (Apollo doesn't support this filter server-side). Set `max_results` higher than your expected final count to compensate.
- **Tech detection coverage**: The free scraper only detects tools that are embedded in a company's public homepage. Internal-only tools won't appear.
- **Rate limits**: The scraper is respectful — it uses a 10-second timeout and doesn't hammer sites. BuiltWith API requests respect your plan's rate limits.
- **Google Sheets**: The first run opens a browser for OAuth authorization. Subsequent runs are fully automatic.