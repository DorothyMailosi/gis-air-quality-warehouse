"""Administrative boundaries: make sure each country has admin units + city rows.

Behaviour per country (config/countries/<country>.yml, `boundaries`):

* If the warehouse already has admin units for the country at `admin_level`,
  they are reused unchanged (existing IDs stay stable for health data and
  dashboards). Missing city rows are added.
* Otherwise boundaries are loaded from `source`:
    - gadm: GADM 4.1 is downloaded automatically for the country's ISO3 code
    - file: a local vector file (shapefile, GeoPackage, GeoJSON)
"""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path

import requests

from .config import CountryConfig, Settings

LOGGER = logging.getLogger(__name__)

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_{iso3}_{level}.json.zip"


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip().upper()).strip("_")


def get_or_create_country(cursor, country: CountryConfig) -> int:
    cursor.execute(
        "SELECT country_id FROM air_staging.country WHERE UPPER(TRIM(iso2)) = %s",
        (country.iso2,),
    )
    row = cursor.fetchone()
    if row:
        return int(row[0])
    cursor.execute(
        "INSERT INTO air_staging.country (iso2, name) VALUES (%s, %s) RETURNING country_id",
        (country.iso2, country.name),
    )
    LOGGER.info("Created country %s (%s)", country.name, country.iso2)
    return int(cursor.fetchone()[0])


def count_admin_units(cursor, country_id: int, level: int) -> int:
    cursor.execute(
        "SELECT COUNT(*) FROM air_staging.admin_unit WHERE country_id = %s AND level = %s",
        (country_id, level),
    )
    return int(cursor.fetchone()[0])


def download_gadm(settings: Settings, country: CountryConfig, level: int) -> Path:
    target_dir = settings.path("boundaries_dir") / country.key
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / f"gadm41_{country.iso3}_{level}.json"
    if json_path.exists():
        return json_path
    url = GADM_URL.format(iso3=country.iso3, level=level)
    LOGGER.info("Downloading GADM boundaries: %s", url)
    zip_path = json_path.with_suffix(".json.zip")
    with requests.get(url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with zip_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                handle.write(chunk)
    with zipfile.ZipFile(zip_path) as archive:
        members = [m for m in archive.namelist() if m.lower().endswith(".json")]
        if not members:
            raise RuntimeError(f"No GeoJSON inside {zip_path}")
        with archive.open(members[0]) as src, json_path.open("wb") as dst:
            dst.write(src.read())
    zip_path.unlink()
    return json_path


def boundary_file(settings: Settings, country: CountryConfig) -> Path:
    cfg = country.boundaries
    source = cfg.get("source", "gadm")
    if source == "gadm":
        return download_gadm(settings, country, int(cfg.get("gadm_level", 1)))
    if source == "file":
        path = Path(cfg["file"])
        path = path if path.is_absolute() else settings.root / path
        if not path.exists():
            raise FileNotFoundError(
                f"Boundary file for {country.name} not found: {path}. "
                "Place it there or switch boundaries.source to gadm."
            )
        return path
    raise ValueError(f"{country.key}: unknown boundaries.source '{source}' (use gadm or file)")


def prepare_units(path: Path, country: CountryConfig):
    """Read, clean and dissolve boundary polygons into one row per admin unit."""
    import geopandas as gpd  # heavy import, only needed here

    cfg = country.boundaries
    region_col = cfg.get("region_column", "NAME_1")
    name_col = cfg.get("name_column", "NAME_2")
    code_col = cfg.get("code_column", "GID_2")

    gdf = gpd.read_file(path)
    missing = {region_col, name_col, code_col} - set(gdf.columns)
    if missing:
        raise ValueError(
            f"{path.name}: missing columns {sorted(missing)}. Available: {list(gdf.columns)}"
        )
    if gdf.crs is None:
        raise ValueError(f"{path.name} has no coordinate reference system.")
    gdf = gdf.to_crs("EPSG:4326")
    for col in {region_col, name_col, code_col}:
        gdf[col] = gdf[col].astype(str).str.strip()
    gdf = gdf[
        gdf.geometry.notna()
        & ~gdf.geometry.is_empty
        & gdf[name_col].ne("")
        & gdf[name_col].str.lower().ne("nan")
    ].copy()
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        LOGGER.warning("Repairing %s invalid geometries", int(invalid.sum()))
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)

    keys = [region_col, name_col] if region_col != name_col else [name_col]
    units = gdf.dissolve(by=keys, as_index=False, aggfunc={code_col: "first"})

    # Same district name in two regions -> "Name (Region)" so names stay unique.
    duplicated = set(units.loc[units.duplicated(name_col, keep=False), name_col].str.lower())

    def display_name(row) -> str:
        name = row[name_col]
        if name.lower() in duplicated and region_col != name_col:
            return f"{name} ({row[region_col]})"
        return name

    units["warehouse_name"] = units.apply(display_name, axis=1)
    units["warehouse_code"] = units.apply(
        lambda row: f"{country.iso2}-{slug(row[code_col])}", axis=1
    )
    if units["warehouse_code"].duplicated().any():
        units["warehouse_code"] = units.apply(
            lambda row: f"{country.iso2}-{slug(row[region_col])}-{slug(row[name_col])}-{slug(row[code_col])}",
            axis=1,
        )
    return units


def insert_units(cursor, units, country_id: int, level: int) -> int:
    inserted = 0
    for _, row in units.iterrows():
        cursor.execute(
            """
            INSERT INTO air_staging.admin_unit (parent_id, country_id, level, code, name, geom)
            VALUES (NULL, %s, %s, %s, %s,
                    ST_Multi(ST_SetSRID(ST_GeomFromWKB(decode(%s, 'hex')), 4326)))
            ON CONFLICT (country_id, level, code) DO NOTHING
            """,
            (country_id, level, row["warehouse_code"], row["warehouse_name"], row.geometry.wkb_hex),
        )
        inserted += cursor.rowcount
    return inserted


def ensure_city_rows(cursor, country_id: int, level: int) -> int:
    """Facts need a city_id; each admin unit has a city row of the same name."""
    cursor.execute(
        """
        INSERT INTO air_staging.city (country_id, name, lat, lon)
        SELECT DISTINCT ON (LOWER(TRIM(au.name)))
               au.country_id, au.name,
               ST_Y(ST_PointOnSurface(au.geom)), ST_X(ST_PointOnSurface(au.geom))
        FROM air_staging.admin_unit au
        WHERE au.country_id = %s
          AND au.level = %s
          AND NOT EXISTS (
              SELECT 1 FROM air_staging.city c
              WHERE c.country_id = au.country_id
                AND LOWER(TRIM(c.name)) = LOWER(TRIM(au.name))
          )
        ORDER BY LOWER(TRIM(au.name)), au.admin_id
        ON CONFLICT (country_id, name) DO NOTHING
        """,
        (country_id, level),
    )
    return cursor.rowcount


def ensure_boundaries(settings: Settings, connection, country: CountryConfig) -> dict:
    level = country.admin_level
    with connection, connection.cursor() as cursor:
        country_id = get_or_create_country(cursor, country)
        existing = count_admin_units(cursor, country_id, level)

    inserted = 0
    if existing:
        LOGGER.info(
            "%s: reusing %s existing admin units at level %s", country.name, existing, level
        )
    else:
        path = boundary_file(settings, country)
        LOGGER.info("%s: loading admin units from %s", country.name, path)
        units = prepare_units(path, country)
        with connection, connection.cursor() as cursor:
            inserted = insert_units(cursor, units, country_id, level)
        LOGGER.info("%s: inserted %s admin units at level %s", country.name, inserted, level)

    with connection, connection.cursor() as cursor:
        cities = ensure_city_rows(cursor, country_id, level)
        total = count_admin_units(cursor, country_id, level)
    if cities:
        LOGGER.info("%s: added %s city rows", country.name, cities)
    return {
        "country_id": country_id,
        "admin_units": total,
        "admin_units_inserted": inserted,
        "city_rows_inserted": cities,
    }
