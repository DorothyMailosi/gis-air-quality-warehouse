"""Database connection and pipeline audit helpers."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2

from .config import REPO_ROOT, Settings

LOGGER = logging.getLogger(__name__)


def connect(settings: Settings):
    db = settings.database
    if not db.get("password"):
        raise RuntimeError(
            "Database password is not set. Put AIR_DB_PASSWORD in your environment "
            "or in the .env file (see .env.example)."
        )
    connection = psycopg2.connect(
        host=db["host"],
        port=int(db["port"]),
        dbname=db["dbname"],
        user=db["user"],
        password=db["password"],
        application_name="gaia_pipeline",
    )
    schema = db.get("schema", "air_staging")
    with connection.cursor() as cursor:
        # PostGIS is installed in air_staging, so it must be on the search path.
        cursor.execute(f"SET search_path = public, {schema}")
    connection.commit()
    return connection


@contextmanager
def connection_scope(settings: Settings) -> Iterator[Any]:
    connection = connect(settings)
    try:
        yield connection
    finally:
        connection.close()


def apply_sql_files(settings: Settings, directory: Path | None = None) -> list[str]:
    """Run every .sql file in sql/bootstrap in name order."""
    directory = directory or REPO_ROOT / "sql" / "bootstrap"
    applied = []
    with connection_scope(settings) as connection:
        for path in sorted(directory.glob("*.sql")):
            LOGGER.info("Applying %s", path.name)
            with connection, connection.cursor() as cursor:
                cursor.execute(path.read_text(encoding="utf-8"))
            applied.append(path.name)
    return applied


def ensure_pipeline_tables(connection) -> None:
    sql = (REPO_ROOT / "sql" / "bootstrap" / "04_pipeline_tables.sql").read_text(encoding="utf-8")
    with connection, connection.cursor() as cursor:
        cursor.execute(sql)


def log_stage(
    connection,
    run_id: str,
    country_iso2: str,
    stage: str,
    status: str,
    started_at: datetime,
    period_month: date | None = None,
    rows_affected: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    with connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO air_staging.pipeline_run_log
                (run_id, country_iso2, period_month, stage, status,
                 rows_affected, details, started_at, finished_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                country_iso2,
                period_month,
                stage,
                status,
                rows_affected,
                json.dumps(details or {}, default=str),
                started_at,
                datetime.now(timezone.utc),
            ),
        )


def ensure_month_partition(cursor, table: str, month: date) -> None:
    """Create the monthly partition for `month` if it does not exist yet."""
    name = f"{table}_{month:%Y_%m}"
    cursor.execute(
        "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'air_staging' AND c.relname = %s",
        (name,),
    )
    if cursor.fetchone():
        return
    next_month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    LOGGER.info("Creating partition air_staging.%s", name)
    cursor.execute(
        f"CREATE TABLE air_staging.{name} PARTITION OF air_staging.{table} "
        "FOR VALUES FROM (%s::timestamptz) TO (%s::timestamptz)",
        (month.isoformat(), next_month.isoformat()),
    )
