"""Load processed gridded Parquet (CAMS air quality, ERA5 weather) into the warehouse.

Steps for one country-month:

1. COPY the Parquet rows into air_staging.stg_gridded_observations.
2. Map each grid cell to the country's admin units (air_staging.grid_cell_admin_map),
   separately for each source grid:
   - 'covers'  : the cell centre lies inside the admin polygon
   - 'nearest' : the admin unit contains no cell centre (small districts, or
                 small stored polygons), so its closest cell represents it.
3. Insert the admin-unit average per time step and variable into the fact
   table (idempotent: ON CONFLICT).
4. Remove the staged rows.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from .config import CountryConfig, Settings
from .db import ensure_month_partition

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Target:
    """Where one kind of gridded data goes."""

    grid: str               # key in grid_cell_admin_map
    fact_table: str
    source_key: str         # settings section holding source_type/name
    dataset_prefix: str


CAMS = Target(grid="cams_eac4", fact_table="fact_sat_air_quality_obs",
              source_key="source_system", dataset_prefix="eac4")
ERA5 = Target(grid="era5", fact_table="fact_meteorology_obs",
              source_key="era5", dataset_prefix="era5")


def dataset_code(country: CountryConfig, month: date, target: Target = CAMS) -> str:
    return f"{country.iso3}_{target.dataset_prefix}_{month:%Y-%m}"


def get_source_id(cursor, settings: Settings, target: Target = CAMS) -> int:
    section = settings.raw[target.source_key]
    src = section.get("source_system", section)
    cursor.execute(
        """
        SELECT source_id FROM air_staging.source_system
        WHERE UPPER(source_type) = UPPER(%s) AND name = %s
        ORDER BY source_id LIMIT 1
        """,
        (src["source_type"], src["name"]),
    )
    row = cursor.fetchone()
    if row:
        return int(row[0])
    cursor.execute(
        """
        INSERT INTO air_staging.source_system (source_type, name, version, url)
        VALUES (%s, %s, %s, %s) RETURNING source_id
        """,
        (src["source_type"], src["name"], src.get("version"), src.get("url")),
    )
    return int(cursor.fetchone()[0])


def get_country_id(cursor, country: CountryConfig) -> int:
    cursor.execute("SELECT country_id FROM air_staging.country WHERE UPPER(TRIM(iso2)) = %s", (country.iso2,))
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"{country.name} is not in air_staging.country; run the boundaries stage first.")
    return int(row[0])


def stage_rows(cursor, frame: pd.DataFrame, code: str) -> int:
    cursor.execute("DELETE FROM air_staging.stg_gridded_observations WHERE dataset_code = %s", (code,))
    buffer = io.StringIO()
    out = frame[["obs_time", "latitude", "longitude", "variable_code", "value"]].copy()
    out.insert(0, "dataset_code", code)
    out["obs_time"] = out["obs_time"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    out.to_csv(buffer, index=False, header=False)
    buffer.seek(0)
    cursor.copy_expert(
        """
        COPY air_staging.stg_gridded_observations
            (dataset_code, obs_time, latitude, longitude, variable_code, value)
        FROM STDIN WITH (FORMAT csv)
        """,
        buffer,
    )
    return len(out)


def update_grid_map(cursor, settings: Settings, code: str, country_id: int, level: int, grid: str) -> dict[str, int]:
    cursor.execute("DROP TABLE IF EXISTS tmp_cells")
    cursor.execute(
        """
        CREATE TEMP TABLE tmp_cells ON COMMIT DROP AS
        SELECT DISTINCT latitude, longitude,
               ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) AS geom
        FROM air_staging.stg_gridded_observations
        WHERE dataset_code = %s
        """,
        (code,),
    )

    # City row for each admin unit (same name, as in the rest of the warehouse).
    admin_city = """
        SELECT au.admin_id, au.geom,
               (SELECT c.city_id FROM air_staging.city c
                 WHERE c.country_id = au.country_id
                   AND LOWER(TRIM(c.name)) = LOWER(TRIM(au.name))
                 ORDER BY c.city_id LIMIT 1) AS city_id
        FROM air_staging.admin_unit au
        WHERE au.country_id = %(country_id)s AND au.level = %(level)s
    """
    params: dict[str, Any] = {"country_id": country_id, "level": level, "grid": grid}

    cursor.execute(
        f"""
        INSERT INTO air_staging.grid_cell_admin_map
            (grid, country_id, admin_level, latitude, longitude, admin_id, city_id, match_method, distance_km)
        SELECT %(grid)s, %(country_id)s, %(level)s, t.latitude, t.longitude, a.admin_id, a.city_id, 'covers', 0
        FROM tmp_cells t
        JOIN ({admin_city}) a ON ST_Covers(a.geom, t.geom)
        WHERE a.city_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """,
        params,
    )
    covers = cursor.rowcount

    # Admin units that now have a 'covers' cell no longer need a 'nearest' one.
    cursor.execute(
        """
        DELETE FROM air_staging.grid_cell_admin_map n
        WHERE n.grid = %(grid)s AND n.country_id = %(country_id)s AND n.admin_level = %(level)s
          AND n.match_method = 'nearest'
          AND EXISTS (SELECT 1 FROM air_staging.grid_cell_admin_map c
                      WHERE c.grid = n.grid AND c.country_id = n.country_id
                        AND c.admin_level = n.admin_level
                        AND c.admin_id = n.admin_id AND c.match_method = 'covers')
        """,
        params,
    )

    nearest = 0
    if settings.load.get("nearest_cell_fallback", True):
        params["max_m"] = float(settings.load.get("nearest_cell_max_km", 100)) * 1000
        cursor.execute(
            f"""
            INSERT INTO air_staging.grid_cell_admin_map
                (grid, country_id, admin_level, latitude, longitude, admin_id, city_id, match_method, distance_km)
            SELECT %(grid)s, %(country_id)s, %(level)s, n.latitude, n.longitude, a.admin_id, a.city_id,
                   'nearest', round((n.dist_m / 1000)::numeric, 2)
            FROM ({admin_city}) a
            CROSS JOIN LATERAL (
                SELECT t.latitude, t.longitude,
                       ST_Distance(t.geom::geography, ST_PointOnSurface(a.geom)::geography) AS dist_m
                FROM tmp_cells t
                ORDER BY t.geom <-> ST_PointOnSurface(a.geom)
                LIMIT 1
            ) n
            WHERE a.city_id IS NOT NULL
              AND n.dist_m <= %(max_m)s
              AND NOT EXISTS (SELECT 1 FROM air_staging.grid_cell_admin_map m
                              WHERE m.grid = %(grid)s AND m.country_id = %(country_id)s
                                AND m.admin_level = %(level)s AND m.admin_id = a.admin_id)
            ON CONFLICT DO NOTHING
            """,
            params,
        )
        nearest = cursor.rowcount

    cursor.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM air_staging.admin_unit
              WHERE country_id = %(country_id)s AND level = %(level)s),
            (SELECT COUNT(DISTINCT admin_id) FROM air_staging.grid_cell_admin_map
              WHERE grid = %(grid)s AND country_id = %(country_id)s AND admin_level = %(level)s),
            (SELECT COUNT(*) FROM tmp_cells t
              WHERE NOT EXISTS (SELECT 1 FROM air_staging.grid_cell_admin_map m
                                WHERE m.grid = %(grid)s AND m.country_id = %(country_id)s
                                  AND m.admin_level = %(level)s
                                  AND m.latitude = t.latitude AND m.longitude = t.longitude))
        """,
        params,
    )
    total_units, mapped_units, outside_cells = cursor.fetchone()
    return {
        "new_covers_links": covers,
        "new_nearest_links": nearest,
        "admin_units": int(total_units),
        "admin_units_with_data": int(mapped_units),
        "cells_outside_country": int(outside_cells),
    }


def _conflict_clause(settings: Settings, refresh: bool, columns: str) -> str:
    if refresh or settings.load.get("on_conflict") == "update":
        return f"DO UPDATE SET {columns}"
    return "DO NOTHING"


def insert_air_quality(cursor, settings: Settings, code: str, country_id: int, level: int,
                       source_id: int, refresh: bool) -> int:
    load_cfg = settings.load
    conflict = _conflict_clause(
        settings, refresh,
        "value_ugm3 = EXCLUDED.value_ugm3, qc_status = EXCLUDED.qc_status, lat = EXCLUDED.lat, lon = EXCLUDED.lon",
    )
    cursor.execute(
        f"""
        INSERT INTO air_staging.fact_sat_air_quality_obs
            (obs_time, city_id, admin_id, pollutant_id, source_id, value_ugm3, qc_status, lat, lon)
        SELECT s.obs_time, m.city_id, m.admin_id, p.pollutant_id, %(source_id)s,
               AVG(s.value),
               CASE WHEN bool_or(m.match_method = 'covers') THEN %(qc)s ELSE %(qc_nearest)s END,
               AVG(s.latitude), AVG(s.longitude)
        FROM air_staging.stg_gridded_observations s
        JOIN air_staging.grid_cell_admin_map m
          ON m.grid = %(grid)s AND m.country_id = %(country_id)s AND m.admin_level = %(level)s
         AND m.latitude = s.latitude AND m.longitude = s.longitude
        JOIN air_staging.pollutant p ON LOWER(p.code) = LOWER(s.variable_code)
        WHERE s.dataset_code = %(code)s
        GROUP BY s.obs_time, m.city_id, m.admin_id, p.pollutant_id
        ON CONFLICT (obs_time, city_id, admin_id, pollutant_id, source_id) {conflict}
        """,
        {
            "source_id": source_id,
            "qc": load_cfg.get("qc_status", "processed"),
            "qc_nearest": load_cfg.get("qc_status_nearest", "processed_nearest"),
            "grid": CAMS.grid,
            "country_id": country_id,
            "level": level,
            "code": code,
        },
    )
    return cursor.rowcount


def ensure_met_variables(cursor, settings: Settings) -> None:
    for code, spec in settings.variables.get("weather", {}).items():
        cursor.execute(
            """
            INSERT INTO air_staging.met_variable (code, display_name, unit)
            SELECT %s, %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM air_staging.met_variable WHERE LOWER(code) = LOWER(%s))
            """,
            (code, spec["display_name"], spec["unit"], code),
        )


def insert_weather(cursor, settings: Settings, code: str, country_id: int, level: int,
                   source_id: int, refresh: bool) -> int:
    load_cfg = settings.load
    conflict = _conflict_clause(
        settings, refresh,
        "value_disp = EXCLUDED.value_disp, admin_id = EXCLUDED.admin_id, qc_status = EXCLUDED.qc_status, "
        "lat = EXCLUDED.lat, lon = EXCLUDED.lon",
    )
    ensure_met_variables(cursor, settings)
    # The meteorology key is (time, city, variable, source): one row per city.
    cursor.execute(
        f"""
        INSERT INTO air_staging.fact_meteorology_obs
            (obs_time, city_id, admin_id, met_var_id, source_id, value_disp, qc_status, lat, lon)
        SELECT s.obs_time, m.city_id, MIN(m.admin_id), v.met_var_id, %(source_id)s,
               AVG(s.value),
               CASE WHEN bool_or(m.match_method = 'covers') THEN %(qc)s ELSE %(qc_nearest)s END,
               AVG(s.latitude), AVG(s.longitude)
        FROM air_staging.stg_gridded_observations s
        JOIN air_staging.grid_cell_admin_map m
          ON m.grid = %(grid)s AND m.country_id = %(country_id)s AND m.admin_level = %(level)s
         AND m.latitude = s.latitude AND m.longitude = s.longitude
        JOIN air_staging.met_variable v ON LOWER(v.code) = LOWER(s.variable_code)
        WHERE s.dataset_code = %(code)s
        GROUP BY s.obs_time, m.city_id, v.met_var_id
        ON CONFLICT (obs_time, city_id, met_var_id, source_id) {conflict}
        """,
        {
            "source_id": source_id,
            "qc": load_cfg.get("qc_status", "processed"),
            "qc_nearest": load_cfg.get("qc_status_nearest", "processed_nearest"),
            "grid": ERA5.grid,
            "country_id": country_id,
            "level": level,
            "code": code,
        },
    )
    return cursor.rowcount


def load_month(settings: Settings, connection, country: CountryConfig, month: date, parquet_path,
               refresh: bool = False, target: Target = CAMS) -> dict[str, Any]:
    frame = pd.read_parquet(parquet_path)
    if frame.empty:
        return {"staged": 0, "facts": 0}
    if "value" not in frame.columns and "value_ugm3" in frame.columns:
        frame = frame.rename(columns={"value_ugm3": "value"})
    code = dataset_code(country, month, target)
    with connection, connection.cursor() as cursor:
        country_id = get_country_id(cursor, country)
        source_id = get_source_id(cursor, settings, target)
        next_month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
        for m in (month, next_month):  # UTC vs local-time partition bounds
            ensure_month_partition(cursor, target.fact_table, m)

        staged = stage_rows(cursor, frame, code)
        mapping = update_grid_map(cursor, settings, code, country_id, country.admin_level, target.grid)
        insert = insert_weather if target is ERA5 else insert_air_quality
        facts = insert(cursor, settings, code, country_id, country.admin_level, source_id, refresh)
        cursor.execute("DELETE FROM air_staging.stg_gridded_observations WHERE dataset_code = %s", (code,))

    LOGGER.info(
        "%s %s %s: staged %s rows -> %s fact rows; %s/%s admin units have data; %s cells outside country",
        country.iso3, target.grid, f"{month:%Y-%m}", staged, facts,
        mapping["admin_units_with_data"], mapping["admin_units"], mapping["cells_outside_country"],
    )
    if mapping["admin_units_with_data"] < mapping["admin_units"]:
        LOGGER.warning(
            "%s: %s admin units have no grid cell within %s km; check the download area.",
            country.name,
            mapping["admin_units"] - mapping["admin_units_with_data"],
            settings.load.get("nearest_cell_max_km", 100),
        )
    return {"staged": staged, "facts": facts, **mapping}


def last_loaded_month(connection, settings: Settings, country: CountryConfig, target: Target = CAMS) -> date | None:
    """Latest month with facts from this source for the country at its configured admin level."""
    with connection, connection.cursor() as cursor:
        source_id = get_source_id(cursor, settings, target)
        cursor.execute(
            f"""
            SELECT MAX(f.obs_time)
            FROM air_staging.{target.fact_table} f
            JOIN air_staging.admin_unit au ON au.admin_id = f.admin_id
            JOIN air_staging.country co ON co.country_id = au.country_id
            WHERE UPPER(co.iso2) = %s AND au.level = %s AND f.source_id = %s
            """,
            (country.iso2, country.admin_level, source_id),
        )
        value = cursor.fetchone()[0]
    if value is None:
        return None
    return date(value.year, value.month, 1)
