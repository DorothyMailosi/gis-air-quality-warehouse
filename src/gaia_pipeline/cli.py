"""Command-line interface.

    python -m gaia_pipeline run --all --incremental      # scheduled update
    python -m gaia_pipeline run --country cameroon --start 2024-01 --end 2024-12
    python -m gaia_pipeline status
    python -m gaia_pipeline dbt
    python -m gaia_pipeline init-db                      # empty database only
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import load_settings, parse_date, select_countries
from .pipeline import STAGES, RunOptions, run, summarise

LOGGER = logging.getLogger("gaia_pipeline")


def setup_logging(log_dir: Path, verbose: bool) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"gaia_{datetime.now():%Y%m%d}.log"
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    handlers = [logging.StreamHandler(sys.stdout), logging.FileHandler(log_file, encoding="utf-8")]
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format=fmt, handlers=handlers)
    for noisy in ("urllib3", "cdsapi", "datapi", "multiurl", "fiona", "pyogrio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return log_file


def add_country_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--country", action="append", help="country key, name, ISO2 or ISO3 (repeatable)")
    group.add_argument("--all", action="store_true", help="every enabled country in config/countries/")


def add_period_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", help="first month, YYYY-MM (default: period.start in the country config)")
    parser.add_argument("--end", help="last month, YYYY-MM or 'latest' (default: period.end)")
    parser.add_argument("--incremental", action="store_true",
                        help="start after the last month already loaded for the country")
    parser.add_argument("--overwrite", action="store_true", help="re-download and re-process existing files")
    parser.add_argument("--refresh", action="store_true", help="overwrite fact rows that already exist")
    parser.add_argument("--dry-run", action="store_true", help="show which months would run, change nothing")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gaia_pipeline", description="Gaia CAMS air-quality pipeline")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="every stage: boundaries, air quality, weather, health (+ dbt)")
    add_country_args(p)
    add_period_args(p)
    p.add_argument("--stages", default=",".join(STAGES),
                   help=f"comma-separated subset of {','.join(STAGES)}")
    p.add_argument("--skip-dbt", action="store_true", help="do not run dbt build at the end")

    helps = {
        "boundaries": "make sure districts exist (GADM / file)",
        "download": "download CAMS air quality",
        "process": "convert CAMS NetCDF to Parquet",
        "load": "load CAMS Parquet into the warehouse",
        "weather": "ERA5 daily weather: download, process and load",
        "health": "load the country's DHIS2 health export",
    }
    for name in STAGES:
        s = sub.add_parser(name, help=helps[name])
        add_country_args(s)
        if name != "boundaries":
            add_period_args(s)

    d = sub.add_parser("dbt", help="dbt build (or another dbt command) on the analytics models")
    d.add_argument("dbt_command", nargs="?", default="build")
    d.add_argument("dbt_args", nargs=argparse.REMAINDER)

    sub.add_parser("status", help="data coverage per country and pollutant")
    sub.add_parser("countries", help="list configured countries")
    sub.add_parser("init-db", help="create the warehouse schema in an EMPTY database")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    log_file = setup_logging(settings.path("logs_dir"), args.verbose)

    try:
        if args.command == "countries":
            for c in settings.countries.values():
                print(f"{c.key:<12} {c.iso2} {c.iso3} enabled={c.enabled!s:<5} level={c.admin_level} "
                      f"pollutants={','.join(c.pollutants)} period={c.start:%Y-%m}..{c.end:%Y-%m}")
            return 0

        if args.command == "status":
            from .status import coverage, format_table
            print(format_table(coverage(settings)))
            return 0

        if args.command == "init-db":
            from .db import apply_sql_files, connection_scope
            with connection_scope(settings) as conn, conn.cursor() as cur:
                cur.execute("SELECT to_regclass('air_staging.fact_sat_air_quality_obs')")
                if cur.fetchone()[0] is not None:
                    print("The warehouse schema already exists; nothing to do.")
                    return 0
            print("Applied:", ", ".join(apply_sql_files(settings)))
            return 0

        if args.command == "dbt":
            from .dbt_runner import run_dbt
            return run_dbt(settings, args.dbt_command, args.dbt_args)

        countries = select_countries(settings, args.country, args.all)
        stages = tuple(args.stages.split(",")) if args.command == "run" else (args.command,)
        unknown = set(stages) - set(STAGES)
        if unknown:
            raise ValueError(f"Unknown stage(s) {sorted(unknown)}; choose from {STAGES}")

        latest = settings.available_until
        options = RunOptions(stages=stages)
        if args.command != "boundaries":
            options.start = parse_date(args.start, latest) if args.start else None
            options.end = parse_date(args.end, latest) if args.end else None
            if options.end and args.end and len(args.end) == 7:
                # --end 2024-03 means "through March 2024"
                from .download import month_end
                options.end = month_end(options.end)
            options.incremental = args.incremental
            options.overwrite = args.overwrite
            options.refresh = args.refresh
            options.dry_run = args.dry_run

        results = run(settings, countries, options)
        print(json.dumps(summarise(results), indent=2))
        failed = any(r.errors for r in results)

        if args.command == "run" and not args.skip_dbt and not options.dry_run:
            if any(r.changed for r in results):
                from .dbt_runner import run_dbt
                if run_dbt(settings, "build") != 0:
                    LOGGER.error("dbt build failed")
                    failed = True
            else:
                LOGGER.info("No new fact rows: dbt build skipped")

        LOGGER.info("Log file: %s", log_file)
        return 1 if failed else 0
    except Exception as exc:
        LOGGER.error("%s", exc)
        if args.verbose:
            LOGGER.exception("details")
        return 1
