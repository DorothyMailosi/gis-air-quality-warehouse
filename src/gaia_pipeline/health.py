"""Load district health data (DHIS2 exports) into the warehouse.

Each country's `health` block in config/countries/<country>.yml describes one
export file (CSV or Excel, one column per indicator):

    health:
      file: MALAWI/malawi OPD and ARI data.csv     # relative to paths.health_dir
      district_column: District
      period: {month_column: Month, year_column: Year}   # or {column: PERIOD, format: "%B %Y"}
      indicators:                                  # file column -> health_indicator.code
        "HMIS # of OPD Attendance": opd_attendance
      denominator_column: Population estimates     # optional
      district_mapping: config/mappings/malawi_dhis2_districts.csv
      use_suggested_mapping: false                 # apply suggested_admin_code corrections
      source: {source_type: DHIS2, name: Malawi DHIS2}

Rules
* Blank cells mean "not reported" and are skipped (never loaded as rows).
* Several DHIS2 districts mapped to one admin unit (e.g. Mzimba North +
  Mzimba South) are summed, including the denominator.
* The file is authoritative for the indicators and months it contains: rows
  already in the warehouse for those (country, indicator, month) are replaced,
  so re-running never duplicates.
* An unchanged file (same SHA-256 as the last successful load) is skipped
  unless --refresh is given.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .config import CountryConfig, Settings

LOGGER = logging.getLogger(__name__)

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
MONTHS.update({  # French DHIS2 exports
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
})


def resolve_file(settings: Settings, cfg: dict[str, Any]) -> Path:
    path = Path(cfg["file"])
    if not path.is_absolute():
        path = settings.path("health_dir") / path
    if not path.exists():
        raise FileNotFoundError(
            f"Health file not found: {path}. Set GAIA_HEALTH_DATA_DIR (in .env) to the folder that holds it."
        )
    return path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_table(path: Path, cfg: dict[str, Any]) -> pd.DataFrame:
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        frame = pd.read_excel(path, sheet_name=cfg.get("sheet", 0))
    else:
        frame = pd.read_csv(path, encoding=cfg.get("encoding", "utf-8-sig"))
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame.dropna(how="all")


def parse_month_name(text: Any) -> int | None:
    key = str(text).strip().lower().rstrip(".")
    if key.isdigit():
        return int(key)
    return MONTHS.get(key)


def period_starts(frame: pd.DataFrame, cfg: dict[str, Any]) -> pd.Series:
    period = cfg["period"]
    if "column" in period:
        raw = frame[period["column"]].astype(str).str.strip()
        fmt = period.get("format")
        if fmt:
            parsed = pd.to_datetime(raw, format=fmt, errors="coerce")
        else:
            parsed = pd.to_datetime(raw, errors="coerce")
        if parsed.isna().any():
            # e.g. "Janvier 2021" or "202101"
            def fallback(text: str):
                match = re.match(r"^\s*([A-Za-zéèûôÉ]+)\s+(\d{4})\s*$", text)
                if match and parse_month_name(match.group(1)):
                    return pd.Timestamp(int(match.group(2)), parse_month_name(match.group(1)), 1)
                match = re.match(r"^\s*(\d{4})-?(\d{2})\s*$", text)
                if match:
                    return pd.Timestamp(int(match.group(1)), int(match.group(2)), 1)
                return pd.NaT
            parsed = parsed.where(parsed.notna(), raw.map(fallback))
    else:
        months = frame[period["month_column"]].map(parse_month_name)
        years = pd.to_numeric(frame[period["year_column"]], errors="coerce")
        parsed = pd.to_datetime(
            {"year": years, "month": months, "day": 1}, errors="coerce"
        )
    bad = parsed.isna().sum()
    if bad:
        LOGGER.warning("%s rows have an unreadable period and are skipped", int(bad))
    return parsed.dt.to_period("M").dt.to_timestamp()


def to_number(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace(",", "", regex=False).str.replace(" ", "", regex=False).str.strip()
    cleaned = cleaned.replace({"": None, "nan": None, "None": None, "-": None})
    return pd.to_numeric(cleaned, errors="coerce")


def read_mapping(settings: Settings, cfg: dict[str, Any]) -> pd.DataFrame | None:
    mapping = cfg.get("district_mapping")
    if not mapping:
        return None
    path = Path(mapping)
    path = path if path.is_absolute() else settings.root / path
    frame = pd.read_csv(path)
    if cfg.get("use_suggested_mapping") and "suggested_admin_code" in frame.columns:
        fix = frame["suggested_admin_code"].notna()
        LOGGER.info("Applying %s suggested mapping corrections", int(fix.sum()))
        frame.loc[fix, "admin_code"] = frame.loc[fix, "suggested_admin_code"]
        frame.loc[fix, "admin_level"] = 2
    return frame


def prepare(settings: Settings, country: CountryConfig) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read the export and return long rows: district, period_start, indicator, value, denominator."""
    cfg = country.health
    path = resolve_file(settings, cfg)
    frame = read_table(path, cfg)
    district_col = cfg["district_column"]
    indicators: dict[str, str] = cfg["indicators"]
    missing = [c for c in [district_col, *indicators] if c not in frame.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}. Columns: {list(frame.columns)}")

    frame["period_start"] = period_starts(frame, cfg)
    frame["district"] = frame[district_col].astype(str).str.strip()
    denominator_col = cfg.get("denominator_column")
    frame["denominator"] = to_number(frame[denominator_col]) if denominator_col else None
    frame = frame.dropna(subset=["period_start"])

    long = frame.melt(
        id_vars=["district", "period_start", "denominator"],
        value_vars=list(indicators),
        var_name="source_column",
        value_name="raw_value",
    )
    long["indicator_code"] = long["source_column"].map(indicators)
    long["value"] = to_number(long["raw_value"])
    blank = int(long["value"].isna().sum())
    long = long.dropna(subset=["value"])
    report = {
        "file": path.name,
        "sha256": file_sha256(path),
        "source_rows": len(frame),
        "districts_in_file": int(frame["district"].nunique()),
        "values": len(long),
        "blank_values_skipped": blank,
        # The file covers every month it lists, including months with only blanks.
        "first_month": str(frame["period_start"].min().date()),
        "last_month": str(frame["period_start"].max().date()),
    }
    return long[["district", "period_start", "indicator_code", "value", "denominator"]], report


def resolve_admin_ids(cursor, settings: Settings, country: CountryConfig, long: pd.DataFrame) -> pd.DataFrame:
    cursor.execute(
        """
        SELECT au.admin_id, au.code, au.level, au.name
        FROM air_staging.admin_unit au
        JOIN air_staging.country c ON c.country_id = au.country_id
        WHERE UPPER(c.iso2) = %s
        """,
        (country.iso2,),
    )
    units = pd.DataFrame(cursor.fetchall(), columns=["admin_id", "code", "level", "name"])
    mapping = read_mapping(settings, country.health)

    lookup: dict[str, int] = {}
    if mapping is not None:
        by_code = dict(zip(units["code"], units["admin_id"]))
        for row in mapping.itertuples():
            if isinstance(row.admin_code, str) and row.admin_code in by_code:
                lookup[str(row.dhis2_district_name).strip().lower()] = int(by_code[row.admin_code])
    # Fallback: exact (case-insensitive) name match at the country's admin level.
    level_units = units[units["level"] == country.admin_level]
    for name, admin_id in zip(level_units["name"], level_units["admin_id"]):
        lookup.setdefault(str(name).strip().lower(), int(admin_id))

    long = long.copy()
    long["admin_id"] = long["district"].str.lower().map(lookup)
    unmatched = sorted(long.loc[long["admin_id"].isna(), "district"].unique())
    if unmatched:
        raise ValueError(
            f"{len(unmatched)} health district(s) have no admin unit: {unmatched}. "
            f"Add them to {country.health.get('district_mapping', 'a district_mapping CSV')}."
        )
    long["admin_id"] = long["admin_id"].astype(int)
    return long


def indicator_ids(cursor, codes: list[str]) -> dict[str, int]:
    cursor.execute("SELECT code, indicator_id FROM air_staging.health_indicator WHERE code = ANY(%s)", (codes,))
    found = dict(cursor.fetchall())
    missing = sorted(set(codes) - set(found))
    if missing:
        raise ValueError(
            f"Unknown health indicator code(s) {missing}. Add them to air_staging.health_indicator "
            "(and sql/bootstrap/03_reference_data.sql)."
        )
    return found


def source_id(cursor, cfg: dict[str, Any]) -> int:
    src = cfg.get("source") or {}
    cursor.execute(
        "SELECT source_id FROM air_staging.source_system WHERE source_type = %s AND name = %s ORDER BY source_id LIMIT 1",
        (src.get("source_type", "DHIS2"), src["name"]),
    )
    row = cursor.fetchone()
    if row:
        return int(row[0])
    cursor.execute(
        "INSERT INTO air_staging.source_system (source_type, name, url) VALUES (%s, %s, %s) RETURNING source_id",
        (src.get("source_type", "DHIS2"), src["name"], src.get("url")),
    )
    return int(cursor.fetchone()[0])


def last_loaded_hash(cursor, country: CountryConfig) -> str | None:
    cursor.execute(
        """
        SELECT details->>'sha256' FROM air_staging.pipeline_run_log
        WHERE country_iso2 = %s AND stage = 'health' AND status = 'success'
        ORDER BY finished_at DESC LIMIT 1
        """,
        (country.iso2,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def load(settings: Settings, connection, country: CountryConfig, refresh: bool = False, dry_run: bool = False) -> dict[str, Any]:
    long, report = prepare(settings, country)
    with connection, connection.cursor() as cursor:
        if not refresh and not dry_run and last_loaded_hash(cursor, country) == report["sha256"]:
            LOGGER.info("%s health: %s unchanged since last load, skipped", country.name, report["file"])
            return {**report, "skipped": True, "inserted": 0, "deleted": 0}

        long = resolve_admin_ids(cursor, settings, country, long)
        ids = indicator_ids(cursor, sorted(long["indicator_code"].unique()))
        long["indicator_id"] = long["indicator_code"].map(ids)

        # Sum districts that share an admin unit; denominators summed once per district.
        values = long.groupby(["admin_id", "indicator_id", "period_start"], as_index=False)["value"].sum()
        denominators = (
            long.drop_duplicates(["district", "period_start"])
            .groupby(["admin_id", "period_start"], as_index=False)["denominator"]
            .sum(min_count=1)
        )
        merged_districts = (
            long.groupby(["admin_id"])["district"].unique().map(lambda d: sorted(d)).to_dict()
        )
        values = values.merge(denominators, on=["admin_id", "period_start"], how="left")
        report["fact_rows"] = len(values)
        report["admin_units"] = int(values["admin_id"].nunique())

        if dry_run:
            LOGGER.info("%s health (dry run): would load %s rows for %s admin units", country.name,
                        len(values), report["admin_units"])
            return {**report, "inserted": 0, "deleted": 0}

        src_id = source_id(cursor, country.health)
        cursor.execute(
            """
            DELETE FROM air_staging.fact_health_district_aggregates h
            USING air_staging.admin_unit au, air_staging.country c
            WHERE h.admin_id = au.admin_id AND au.country_id = c.country_id
              AND UPPER(c.iso2) = %s
              AND h.indicator_id = ANY(%s)
              AND h.period_type = 'monthly'
              AND h.period_start BETWEEN %s AND %s
            """,
            (country.iso2, list(ids.values()), report["first_month"], report["last_month"]),
        )
        deleted = cursor.rowcount

        rows = []
        for r in values.itertuples(index=False):
            start: date = r.period_start.date()
            end = (r.period_start + pd.offsets.MonthEnd(0)).date()
            denominator = None if pd.isna(r.denominator) else float(r.denominator)
            attrs = {"dataset": report["file"], "districts": list(merged_districts.get(r.admin_id, []))}
            rows.append((int(r.admin_id), int(r.indicator_id), src_id, start, end, "monthly",
                         float(r.value), float(r.value), denominator, "loaded", json.dumps(attrs, ensure_ascii=False)))
        from psycopg2.extras import execute_values

        execute_values(
            cursor,
            """
            INSERT INTO air_staging.fact_health_district_aggregates
                (admin_id, indicator_id, source_id, period_start, period_end, period_type,
                 value, numerator, denominator, qc_status, attrs)
            VALUES %s
            """,
            rows,
            template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
            page_size=1000,
        )
        inserted = len(rows)

    LOGGER.info("%s health: replaced %s rows with %s rows (%s admin units, %s..%s); %s blank values skipped",
                country.name, deleted, inserted, report["admin_units"], report["first_month"],
                report["last_month"], report["blank_values_skipped"])
    return {**report, "inserted": inserted, "deleted": deleted}
