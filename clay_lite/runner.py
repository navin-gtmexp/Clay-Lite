"""
ProjectRunner: orchestrates the full research pipeline.

Pipeline:
  1. Resolve data source (CSV, Apollo, etc.)
  2. Fetch companies and apply filters
  3. Deduplicate by normalized domain
  4. Enrich with tech detection (concurrent)
  5. Export to Google Sheets + CSV
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from .config import CredentialStore
from .enrichers.scraper import ScraperEnricher
from .exporters.csv_exporter import CsvExporter
from .exporters.google_sheets import GoogleSheetsExporter
from .models import Company, ProjectConfig, RunResult
from .sources.apollo import ApolloSource
from .sources.csv_source import CsvSource


class ProjectRunner:
    """Runs a full research project end to end."""

    def __init__(self, config: ProjectConfig, credentials: CredentialStore):
        self._config = config
        self._creds = credentials

    def run(self, verbose: bool = True) -> RunResult:
        config = self._config
        result = RunResult(
            project_id=config.project_id,
            started_at=datetime.utcnow(),
        )

        _log = print if verbose else (lambda *a, **k: None)

        # ── Step 1: Fetch companies ───────────────────────────────────────────
        _log(f"\n[1/4] Fetching companies from source: {config.sources.primary}")
        try:
            source = self._build_source(config.sources.primary)
            companies = source.search(config.filters, config.sources.max_results)
        except FileNotFoundError as e:
            result.errors.append(str(e))
            _log(f"  ERROR: {e}")
            return result
        except Exception as e:
            result.errors.append(f"Source error ({config.sources.primary}): {e}")
            _log(f"  ERROR from {config.sources.primary}: {e}")
            companies = []

        # Try fallback source if configured and primary returned nothing
        if not companies and config.sources.fallback:
            _log(f"  Primary returned 0 results. Trying fallback: {config.sources.fallback}")
            try:
                fallback = self._build_source(config.sources.fallback)
                companies = fallback.search(config.filters, config.sources.max_results)
            except Exception as e:
                result.errors.append(f"Fallback source error: {e}")
                _log(f"  ERROR from fallback: {e}")

        result.total_found = len(companies)
        _log(f"  Found {len(companies)} companies")

        if not companies:
            _log("  No companies to process. Exiting.")
            result.completed_at = datetime.utcnow()
            result.errors.append("No companies found — check your source config and filters")
            return result

        # ── Step 2: Deduplicate ───────────────────────────────────────────────
        _log(f"\n[2/4] Deduplicating...")
        companies = _deduplicate(companies)
        _log(f"  {len(companies)} unique companies after deduplication")

        # ── Step 3: Tech detection ────────────────────────────────────────────
        if config.tech_detection.enabled:
            _log(f"\n[3/4] Running tech detection (scraper) on {len(companies)} domains...")
            companies = self._run_enrichment(companies, verbose=verbose)
            result.total_enriched = sum(
                1 for c in companies if c.tech_detection_source is not None
            )

            # Count tool usage
            result.uses_sisense_count = sum(1 for c in companies if c.uses_sisense)
            result.uses_looker_count = sum(1 for c in companies if c.uses_looker)
            result.uses_gooddata_count = sum(1 for c in companies if c.uses_gooddata)
        else:
            _log(f"\n[3/4] Tech detection disabled — skipping")

        # ── Step 4: Export ────────────────────────────────────────────────────
        _log(f"\n[4/4] Exporting results...")

        # CSV export (always attempted if enabled)
        if config.output.csv_enabled:
            try:
                csv_exp = CsvExporter(output_dir="outputs")
                csv_path = csv_exp.export(
                    companies,
                    config,
                    filename=config.output.csv_filename,
                )
                result.csv_path = csv_path
                _log(f"  CSV: {csv_path}")
            except Exception as e:
                result.errors.append(f"CSV export error: {e}")
                _log(f"  CSV export failed: {e}")

        # Google Sheets export
        if config.output.google_sheets.enabled:
            try:
                gs_exp = GoogleSheetsExporter(
                    credentials_file=config.output.google_sheets.credentials_file
                )
                sheet_url = gs_exp.export(companies, config)
                result.sheet_url = sheet_url
                _log(f"  Google Sheet: {sheet_url}")
            except FileNotFoundError as e:
                result.errors.append(f"Google Sheets setup required: {e}")
                _log(f"\n  [Google Sheets] Setup required:\n{e}")
            except Exception as e:
                result.errors.append(f"Google Sheets export error: {e}")
                _log(f"  Google Sheets export failed: {e}")

        result.total_exported = len(companies)
        result.completed_at = datetime.utcnow()
        return result

    def _build_source(self, source_name: str):
        """Instantiate the appropriate source adapter."""
        if source_name == "csv":
            csv_path = self._config.sources.csv_input
            if not csv_path:
                raise ValueError(
                    "sources.csv_input must be set in the project config when using the CSV source.\n"
                    "Example: create a CSV file at inputs/companies.csv and set:\n"
                    '  "sources": {"primary": "csv", "csv_input": "inputs/companies.csv"}'
                )
            return CsvSource(csv_path=csv_path)

        elif source_name == "apollo":
            api_key = self._creds.apollo_api_key
            if not api_key:
                raise ValueError(
                    "APOLLO_API_KEY is not set in your .env file.\n"
                    "Get a free API key at: https://app.apollo.io/#/settings/integrations/api\n"
                    "Then add to .env:  APOLLO_API_KEY=your_key_here"
                )
            return ApolloSource(api_key=api_key)

        else:
            raise ValueError(
                f"Unknown source: {source_name!r}. "
                f"Supported sources: csv, apollo"
            )

    def _run_enrichment(self, companies: list, verbose: bool = True) -> list:
        """Run tech detection on all companies using a thread pool."""
        enricher = ScraperEnricher(self._config.tech_detection)
        enriched = []
        errors = 0

        # Use up to 8 concurrent workers (network I/O bound)
        max_workers = min(8, len(companies))

        if verbose:
            try:
                from tqdm import tqdm
                progress = tqdm(total=len(companies), unit="company", ncols=70)
            except ImportError:
                progress = None
        else:
            progress = None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(enricher.enrich, c): c for c in companies}
            for future in as_completed(futures):
                try:
                    enriched.append(future.result())
                except Exception as e:
                    company = futures[future]
                    company.enrichment_errors.append(f"Enrichment failed: {e}")
                    company.tech_detection_source = "none"
                    enriched.append(company)
                    errors += 1
                if progress:
                    progress.update(1)

        if progress:
            progress.close()

        if errors and verbose:
            print(f"  {errors} companies had enrichment errors (see Enrichment Errors column)")

        return enriched


def _deduplicate(companies: list) -> list:
    """Remove duplicate companies by normalized domain. Keeps the first occurrence."""
    seen = {}
    for company in companies:
        key = company.normalize_domain()
        if key not in seen:
            seen[key] = company
    return list(seen.values())
