"""Command-line interface. Run `python -m vcdiscovery.cli --help` for the list of commands."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import BASE_DIR, get_settings
from .db import configure, init_db, session_scope


def _setup():
    settings = get_settings()
    configure(settings.resolved_database_url)
    init_db()
    return settings


def cmd_init_db(_args):
    settings = _setup()
    print(f"Database ready: {settings.resolved_database_url}")


def cmd_run(args):
    from .pipeline import run_discovery

    settings = _setup()
    result = run_discovery(settings, keys=args.source or None, groups=args.group or None, trigger="cli")
    for r in result["results"]:
        line = f"  {r['source']:<22} {r['status']:<8} fetched={r.get('fetched', 0)} new={r.get('new', 0)} " \
               f"duplicates={r.get('duplicate', 0)} new_companies={r.get('startups_created', 0)}"
        print(line + (f"  ERROR: {r['error']}" if r.get("error") else ""))
    for s in result["skipped"]:
        print(f"  {s['key']:<22} skipped  {s['reason']}")
    if not result["results"]:
        print("No sources ran. Check config/sources.json and your .env file.")


def cmd_check_sources(args):
    """Fetch each source once (nothing is saved) to confirm it is reachable and returns data."""
    from .http import SourceUnavailable
    from .pipeline import make_client, make_sec_client
    from .sources import build_sources
    from .sources.sec_formd import SecFormDSource

    settings = _setup()
    sources, skipped = build_sources(settings, include_disabled=args.include_disabled)
    client = make_client(settings)
    ok = True
    for src in sources:
        if isinstance(src, SecFormDSource):
            src.max_filings = 2
            sec = make_sec_client(settings)
            fetch_client = sec
        else:
            fetch_client = client
        try:
            items = src.fetch(fetch_client)
            print(f"  OK    {src.key:<22} {len(items)} item(s)" + (f"  e.g. {items[0].title if hasattr(items[0], 'title') else items[0].issuer_name}" if items else ""))
        except (SourceUnavailable, Exception) as exc:
            ok = False
            print(f"  FAIL  {src.key:<22} {type(exc).__name__}: {exc}")
    for s in skipped:
        print(f"  SKIP  {s['key']:<22} {s['reason']}")
    client.close()
    sys.exit(0 if ok else 1)


def cmd_serve(args):
    import uvicorn

    from .api import create_app

    settings = get_settings()
    if args.scheduler:
        settings.enable_scheduler = True
    uvicorn.run(create_app(settings), host=args.host, port=args.port)


def cmd_schedule(_args):
    from .scheduler import build_scheduler, describe

    settings = _setup()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for job in describe():
        print(f"  {job['job']:<10} {job['schedule_utc']}")
    print("Scheduler running. Press Ctrl+C to stop.")
    build_scheduler(settings, blocking=True).start()


def cmd_refresh_scores(_args):
    from .scheduler import run_score_refresh

    settings = _setup()
    print(run_score_refresh(settings, trigger="cli"))


def cmd_import_tracker(args):
    from .csv_io import import_tracker_snapshot

    _setup()
    path = Path(args.path) if args.path else BASE_DIR.parent / "vc-investment-tracker-web" / "dist" / "data" / "demo-data.json"
    with session_scope() as session:
        print(import_tracker_snapshot(session, path))


def cmd_import_csv(args):
    from .csv_io import import_startups_csv

    _setup()
    with session_scope() as session:
        result = import_startups_csv(session, Path(args.path).read_text(encoding="utf-8-sig"))
    print(result)


def cmd_export_csv(args):
    from .csv_io import export_filings_csv, export_rounds_csv, export_startups_csv

    _setup()
    out = Path(args.directory)
    out.mkdir(parents=True, exist_ok=True)
    with session_scope() as session:
        (out / "startups.csv").write_text(export_startups_csv(session), encoding="utf-8")
        (out / "funding_rounds.csv").write_text(export_rounds_csv(session), encoding="utf-8")
        (out / "sec_filings.csv").write_text(export_filings_csv(session), encoding="utf-8")
    print(f"Wrote startups.csv, funding_rounds.csv and sec_filings.csv to {out.resolve()}")


def cmd_export_snapshot(args):
    from .dashboard_export import build_snapshot

    settings = _setup()
    with session_scope() as session:
        snap = build_snapshot(session, settings)
    Path(args.path).write_text(json.dumps(snap, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(snap['startups'])} startups, {len(snap['rounds'])} rounds, {len(snap['claims'])} claims to {args.path}")


def cmd_print_schema(_args):
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateIndex, CreateTable

    from . import models  # noqa: F401
    from .db import Base

    dialect = postgresql.dialect() if _args.postgres else sqlite.dialect()
    for table in Base.metadata.sorted_tables:
        print(str(CreateTable(table).compile(dialect=dialect)).strip() + ";\n")
        for index in table.indexes:
            print(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
        print()


def cmd_status(_args):
    from sqlalchemy import func, select

    from .models import DuplicateCandidate, JobRun, NewsArticle, SecFiling, Startup

    _setup()
    with session_scope() as s:
        print("Startups:", s.scalar(select(func.count(Startup.id))),
              "| Articles:", s.scalar(select(func.count(NewsArticle.id))),
              "| Form D filings:", s.scalar(select(func.count(SecFiling.id))),
              "| Open duplicate checks:", s.scalar(select(func.count(DuplicateCandidate.id)).where(DuplicateCandidate.status == "open")))
        print("Recent jobs:")
        for j in s.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(10)):
            print(f"  {j.started_at:%Y-%m-%d %H:%M} {j.source_key or j.job_name:<22} {j.status:<8} new={j.items_new} {j.error_message or ''}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m vcdiscovery.cli", description="VC Discovery Engine")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create the database tables").set_defaults(func=cmd_init_db)
    p = sub.add_parser("run", help="Run discovery now")
    p.add_argument("--source", action="append", help="Source key (repeatable). Default: all enabled")
    p.add_argument("--group", action="append", help="news | funding | community | regulatory (repeatable)")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("check-sources", help="Test that each source is reachable (saves nothing)")
    p.add_argument("--include-disabled", action="store_true")
    p.set_defaults(func=cmd_check_sources)
    p = sub.add_parser("serve", help="Start the API server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--scheduler", action="store_true", help="Also run scheduled jobs inside the server")
    p.set_defaults(func=cmd_serve)
    sub.add_parser("schedule", help="Run the scheduler in this terminal").set_defaults(func=cmd_schedule)
    sub.add_parser("refresh-scores", help="Recompute investment scores").set_defaults(func=cmd_refresh_scores)
    p = sub.add_parser("import-tracker", help="Import the dashboard's demo-data.json research snapshot")
    p.add_argument("path", nargs="?", help="Default: ../vc-investment-tracker-web/dist/data/demo-data.json")
    p.set_defaults(func=cmd_import_tracker)
    p = sub.add_parser("import-csv", help="Import companies from a CSV file")
    p.add_argument("path")
    p.set_defaults(func=cmd_import_csv)
    p = sub.add_parser("export-csv", help="Export startups, funding rounds and SEC filings to CSV")
    p.add_argument("directory", nargs="?", default="exports")
    p.set_defaults(func=cmd_export_csv)
    p = sub.add_parser("export-snapshot", help="Write a dashboard-compatible JSON snapshot")
    p.add_argument("path")
    p.set_defaults(func=cmd_export_snapshot)
    p = sub.add_parser("print-schema", help="Print the SQL schema")
    p.add_argument("--postgres", action="store_true")
    p.set_defaults(func=cmd_print_schema)
    sub.add_parser("status", help="Show record counts and recent jobs").set_defaults(func=cmd_status)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
