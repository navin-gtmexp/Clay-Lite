"""
Clay-Lite CLI entry point.

Usage:
  python -m clay_lite run projects/my_project.json
  python -m clay_lite new-project --name my_project
  python -m clay_lite validate projects/my_project.json
  python -m clay_lite list-projects
  python -m clay_lite status
"""

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .config import ConfigLoader, CredentialStore
from .runner import ProjectRunner


def main():
    parser = argparse.ArgumentParser(
        prog="clay_lite",
        description=f"Clay-Lite v{__version__} — Lightweight account-based research tool",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── run ───────────────────────────────────────────────────────────────────
    run_parser = subparsers.add_parser(
        "run", help="Run a research project and export results"
    )
    run_parser.add_argument("config", help="Path to the project JSON config file")
    run_parser.add_argument(
        "--no-sheets",
        action="store_true",
        help="Skip Google Sheets export (CSV only)",
    )
    run_parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress progress output"
    )

    # ── new-project ───────────────────────────────────────────────────────────
    new_parser = subparsers.add_parser(
        "new-project", help="Create a new project config from the template"
    )
    new_parser.add_argument(
        "--name",
        required=True,
        help="Project identifier (used as filename and project_id)",
    )
    new_parser.add_argument(
        "--description", "-d", default="", help="Short description of this research project"
    )

    # ── validate ──────────────────────────────────────────────────────────────
    validate_parser = subparsers.add_parser(
        "validate", help="Validate a project config file without running it"
    )
    validate_parser.add_argument("config", help="Path to the project JSON config file")

    # ── list-projects ─────────────────────────────────────────────────────────
    subparsers.add_parser(
        "list-projects", help="List all project configs in the projects/ directory"
    )

    # ── status ────────────────────────────────────────────────────────────────
    subparsers.add_parser(
        "status", help="Show configured API keys and Google Sheets connection status"
    )

    args = parser.parse_args()
    creds = CredentialStore()

    # ── Dispatch ──────────────────────────────────────────────────────────────

    if args.command == "status":
        _cmd_status(creds)

    elif args.command == "list-projects":
        _cmd_list_projects()

    elif args.command == "new-project":
        _cmd_new_project(args, creds)

    elif args.command == "validate":
        _cmd_validate(args)

    elif args.command == "run":
        _cmd_run(args, creds)


def _cmd_status(creds: CredentialStore):
    print(f"\nClay-Lite v{__version__} — Connection Status")
    print("=" * 44)
    creds.print_status()
    print()
    print("  Quick start:")
    print("    1. cp .env.example .env")
    print("    2. python -m clay_lite new-project --name my_research")
    print("    3. Edit projects/my_research.json")
    print("    4. python -m clay_lite run projects/my_research.json")
    print()


def _cmd_list_projects():
    loader = ConfigLoader()
    projects = loader.list_projects("projects")
    if not projects:
        print("No projects found in projects/")
        print("Create one with: python -m clay_lite new-project --name my_project")
        return
    print(f"\nFound {len(projects)} project(s):\n")
    for p in projects:
        try:
            config = loader.load(p)
            print(f"  {p}")
            if config.description:
                print(f"    Description : {config.description}")
            print(f"    Source      : {config.sources.primary}")
            print(f"    Max results : {config.sources.max_results}")
            print(f"    Tech targets: {', '.join(config.tech_detection.target_tools)}")
            print()
        except Exception as e:
            print(f"  {p}  [ERROR: {e}]")


def _cmd_new_project(args, creds: CredentialStore):
    loader = ConfigLoader()
    os.makedirs("projects", exist_ok=True)

    # Sanitize name
    project_id = args.name.lower().replace(" ", "_").replace("-", "_")
    project_id = "".join(c for c in project_id if c.isalnum() or c == "_")
    path = f"projects/{project_id}.json"

    if os.path.exists(path):
        print(f"Project already exists: {path}")
        print("Edit it directly or choose a different name.")
        sys.exit(1)

    loader.create_template(
        path,
        project_id=project_id,
        name=args.description or args.name,
    )
    print(f"\nCreated project: {path}")
    print()
    print("Next steps:")
    print(f"  1. Edit {path} to configure your filters and data source")
    print(f"  2. python -m clay_lite validate {path}")
    print(f"  3. python -m clay_lite run {path}")
    print()
    _print_source_guidance(creds)


def _cmd_validate(args):
    loader = ConfigLoader()
    try:
        config = loader.load(args.config)
        print(f"\n✓ Config is valid: {args.config}")
        print(f"  Project ID  : {config.project_id}")
        print(f"  Description : {config.description}")
        print(f"  Source      : {config.sources.primary}")
        print(f"  Max results : {config.sources.max_results}")
        print(f"  Tech targets: {', '.join(config.tech_detection.target_tools)}")
        print(f"  Filters:")
        f = config.filters
        print(f"    Countries  : {', '.join(f.hq_country)}")
        print(f"    Employees  : {f.employee_count_min or 'any'} – {f.employee_count_max or 'any'}")
        if f.revenue_usd_min:
            print(f"    Revenue    : ${f.revenue_usd_min:,}+")
        if f.min_customer_count:
            print(f"    Customers  : {f.min_customer_count}+")
        print()
    except (ValueError, FileNotFoundError) as e:
        print(f"\n✗ Config error in {args.config}:\n  {e}")
        sys.exit(1)


def _cmd_run(args, creds: CredentialStore):
    loader = ConfigLoader()

    try:
        config = loader.load(args.config)
    except (ValueError, FileNotFoundError) as e:
        print(f"\nConfig error: {e}")
        sys.exit(1)

    if args.no_sheets:
        config.output.google_sheets.enabled = False

    print(f"\nClay-Lite v{__version__}")
    print(f"Project: {config.project_id}")
    if config.description:
        print(f"  {config.description}")
    print("-" * 50)

    runner = ProjectRunner(config=config, credentials=creds)
    result = runner.run(verbose=not args.quiet)

    # ── Summary ───────────────────────────────────────────────────────────────
    if result.completed_at is None:
        result.completed_at = result.started_at
    duration = (result.completed_at - result.started_at).total_seconds()
    print(f"\n{'='*50}")
    print(f"COMPLETE in {duration:.0f}s")
    print(f"  Companies found    : {result.total_found}")
    print(f"  Companies exported : {result.total_exported}")

    if config.tech_detection.enabled:
        print(f"\n  Tech detection results:")
        print(f"    Uses Sisense   : {result.uses_sisense_count}")
        print(f"    Uses Looker    : {result.uses_looker_count}")
        print(f"    Uses GoodData  : {result.uses_gooddata_count}")

    if result.csv_path:
        print(f"\n  CSV: {result.csv_path}")
    if result.sheet_url:
        print(f"  Google Sheet: {result.sheet_url}")

    if result.errors:
        print(f"\n  Warnings/Errors:")
        for err in result.errors:
            # Only show first line to avoid wall of text
            first_line = err.split("\n")[0]
            print(f"    - {first_line}")

    print()
    sys.exit(0 if not result.errors else 1)


def _print_source_guidance(creds: CredentialStore):
    available = creds.available_sources()
    if "apollo" not in available and "crunchbase" not in available:
        print("  Note: No API keys configured. The default source is 'csv'.")
        print("  To use CSV mode:")
        print("    1. Create a CSV file with columns: name, domain, hq_country,")
        print("       employee_count, revenue_usd, industry")
        print("    2. Set sources.csv_input in your project JSON to the CSV path")
        print()
        print("  To enable Apollo.io (free tier available):")
        print("    1. Sign up at https://app.apollo.io")
        print("    2. Get your API key from Settings → Integrations → API")
        print("    3. Add to .env:  APOLLO_API_KEY=your_key_here")
        print("    4. Change sources.primary to 'apollo' in your project JSON")
        print()


if __name__ == "__main__":
    main()
