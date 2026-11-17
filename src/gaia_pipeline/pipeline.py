"""Orchestration per country.

    boundaries -> CAMS air quality (download -> process -> load, per month)
               -> ERA5 weather     (download -> process -> load, per month)
               -> health           (DHIS2 export file -> fact_health_district_aggregates)

Each stream is independent: a failure in one is logged and the others still run.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from . import boundaries, download, health, load, process, weather
from .config import CountryConfig, Settings
from .db import connection_scope, ensure_pipeline_tables, log_stage

LOGGER = logging.getLogger(__name__)

AIR_STAGES = ("download", "process", "load")
STAGES = ("boundaries", *AIR_STAGES, "weather", "health")


@dataclass
class RunOptions:
    stages: tuple[str, ...] = STAGES
    start: date | None = None
    end: date | None = None
    incremental: bool = False
    overwrite: bool = False   # re-download / re-process files that exist
    refresh: bool = False     # overwrite existing fact rows / reload unchanged health files
    dry_run: bool = False


@dataclass
class CountryResult:
    country: str
    months: list[str] = field(default_factory=list)
    weather_months: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    facts_inserted: int = 0
    weather_inserted: int = 0
    health_inserted: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.facts_inserted or self.weather_inserted or self.health_inserted)


def _next_month(month: date) -> date:
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


def plan_months(settings: Settings, connection, country: CountryConfig, options: RunOptions) -> list[date]:
    start = options.start or country.start
    end = min(options.end or country.end, settings.available_until)
    if options.incremental and connection is not None:
        last = load.last_loaded_month(connection, settings, country)
        if last is not None:
            start = max(start, _next_month(last))
            LOGGER.info("%s: last loaded month %s -> starting at %s", country.name, f"{last:%Y-%m}", f"{start:%Y-%m}")
    if start > end:
        return []
    return list(download.month_starts(start, end))


def plan_weather_months(settings: Settings, connection, country: CountryConfig, options: RunOptions) -> list[date]:
    months = weather.plan_months(settings, country, options.start, options.end)
    if options.incremental and connection is not None and months:
        last = load.last_loaded_month(connection, settings, country, load.ERA5)
        if last is not None:
            months = [m for m in months if m > last]
            LOGGER.info("%s weather: last loaded month %s", country.name, f"{last:%Y-%m}")
    return months


def _record_failure(connection, run_id: str, country: CountryConfig, stage: str, started: datetime,
                    month: date | None, exc: Exception, result: CountryResult) -> None:
    label = f" {month:%Y-%m}" if month else ""
    message = f"{country.name}{label} [{stage}]: {exc}"
    LOGGER.error(message)
    result.errors.append(message)
    if connection is None:
        return
    try:
        connection.rollback()
        log_stage(connection, run_id, country.iso2, stage, "failed", started,
                  period_month=month, details={"error": str(exc)})
    except Exception:
        LOGGER.exception("Could not write failure to pipeline_run_log")


def _run_air_quality(settings, connection, country, options, run_id, result) -> None:
    months = plan_months(settings, connection, country, options)
    if not months:
        LOGGER.info("%s: air quality up to date (until %s)", country.name, f"{settings.available_until:%Y-%m}")
        return
    LOGGER.info("%s: air quality, %s month(s) %s .. %s", country.name, len(months),
                f"{months[0]:%Y-%m}", f"{months[-1]:%Y-%m}")
    if options.dry_run:
        result.months = [f"{m:%Y-%m}" for m in months]
        return

    client = None
    for month in months:
        stage = "download"
        started = datetime.now(timezone.utc)
        try:
            if "download" in options.stages:
                client = client or download.make_client(settings)
                download.download_month(settings, country, month, client=client, overwrite=options.overwrite)
            parquet = None
            if "process" in options.stages:
                stage = "process"
                parquet, report = process.process_month(settings, country, month, overwrite=options.overwrite)
                if connection is not None and not report.get("skipped"):
                    log_stage(connection, run_id, country.iso2, "process", "success", started,
                              period_month=month, rows_affected=report.get("final_rows"), details=report)
            if "load" in options.stages:
                stage = "load"
                parquet = parquet or process.processed_path(settings, country, month)
                if not parquet.exists():
                    raise FileNotFoundError(f"Processed file missing: {parquet}")
                info = load.load_month(settings, connection, country, month, parquet, refresh=options.refresh)
                result.facts_inserted += info["facts"]
                log_stage(connection, run_id, country.iso2, "load", "success", started,
                          period_month=month, rows_affected=info["facts"], details=info)
            result.months.append(f"{month:%Y-%m}")
        except Exception as exc:  # noqa: BLE001 - record, then move on to the next stream
            _record_failure(connection, run_id, country, stage, started, month, exc, result)
            # A failed month usually means later months fail too (e.g. not yet published).
            break


def _run_weather(settings, connection, country, options, run_id, result) -> None:
    if not country.weather.get("enabled", False):
        return
    months = plan_weather_months(settings, connection, country, options)
    if not months:
        LOGGER.info("%s: weather up to date (until %s)", country.name, f"{settings.era5_available_until:%Y-%m}")
        return
    LOGGER.info("%s: weather, %s month(s) %s .. %s", country.name, len(months),
                f"{months[0]:%Y-%m}", f"{months[-1]:%Y-%m}")
    if options.dry_run:
        result.weather_months = [f"{m:%Y-%m}" for m in months]
        return

    client = None
    for month in months:
        started = datetime.now(timezone.utc)
        stage = "weather"
        try:
            client = client or weather.make_client(settings)
            weather.download_month(settings, country, month, client=client, overwrite=options.overwrite)
            parquet, _ = weather.process_month(settings, country, month, overwrite=options.overwrite)
            info = load.load_month(settings, connection, country, month, parquet,
                                   refresh=options.refresh, target=load.ERA5)
            result.weather_inserted += info["facts"]
            log_stage(connection, run_id, country.iso2, "weather", "success", started,
                      period_month=month, rows_affected=info["facts"], details=info)
            result.weather_months.append(f"{month:%Y-%m}")
        except Exception as exc:  # noqa: BLE001
            _record_failure(connection, run_id, country, stage, started, month, exc, result)
            break


def _run_health(settings, connection, country, options, run_id, result) -> None:
    if not country.health or not country.health.get("enabled", True):
        return
    started = datetime.now(timezone.utc)
    try:
        info = health.load(settings, connection, country, refresh=options.refresh, dry_run=options.dry_run)
        result.health_inserted += info.get("inserted", 0)
        if not options.dry_run and not info.get("skipped"):
            log_stage(connection, run_id, country.iso2, "health", "success", started,
                      rows_affected=info.get("inserted"), details=info)
    except Exception as exc:  # noqa: BLE001
        _record_failure(connection, run_id, country, "health", started, None, exc, result)


def run_country(settings: Settings, country: CountryConfig, options: RunOptions, run_id: str) -> CountryResult:
    result = CountryResult(country=country.name)
    db_stages = {"boundaries", "load", "weather", "health"}
    needs_db = bool(db_stages & set(options.stages)) or options.incremental

    def _run(connection) -> None:
        # --dry-run is read-only: no tables, boundaries or files are created.
        if connection is not None and not options.dry_run:
            ensure_pipeline_tables(connection)

        if "boundaries" in options.stages and not options.dry_run:
            started = datetime.now(timezone.utc)
            try:
                info = boundaries.ensure_boundaries(settings, connection, country)
                log_stage(connection, run_id, country.iso2, "boundaries", "success", started,
                          rows_affected=info["admin_units_inserted"], details=info)
            except Exception as exc:  # noqa: BLE001 - without districts nothing else can load
                _record_failure(connection, run_id, country, "boundaries", started, None, exc, result)
                return

        if set(AIR_STAGES) & set(options.stages):
            _run_air_quality(settings, connection, country, options, run_id, result)
        if "weather" in options.stages:
            _run_weather(settings, connection, country, options, run_id, result)
        if "health" in options.stages:
            _run_health(settings, connection, country, options, run_id, result)

    if needs_db:
        with connection_scope(settings) as connection:
            _run(connection)
    else:
        _run(None)
    return result


def run(settings: Settings, countries: list[CountryConfig], options: RunOptions) -> list[CountryResult]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    LOGGER.info("Run %s: %s; stages=%s", run_id, ", ".join(c.name for c in countries), ",".join(options.stages))
    results = []
    for country in countries:
        try:
            results.append(run_country(settings, country, options, run_id))
        except Exception as exc:
            LOGGER.exception("%s failed", country.name)
            results.append(CountryResult(country=country.name, errors=[f"{country.name}: {exc}"]))
    return results


def _span(months: list[str]) -> str:
    return f"{months[0]} .. {months[-1]} ({len(months)})" if months else "none"


def summarise(results: list[CountryResult]) -> dict[str, Any]:
    return {
        r.country: {
            "air_quality_months": _span(r.months),
            "air_quality_rows": r.facts_inserted,
            "weather_months": _span(r.weather_months),
            "weather_rows": r.weather_inserted,
            "health_rows": r.health_inserted,
            "errors": r.errors,
        }
        for r in results
    }
