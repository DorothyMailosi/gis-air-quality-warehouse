# Adding a country

1. Copy `config/countries/_template.yml` to `config/countries/<country>.yml`
   (lower-case file name, e.g. `kenya.yml`).

2. Fill in:
   * `country`: name, ISO2 (`KE`), ISO3 (`KEN`).
   * `area`: download box `[North, West, South, East]`. Take the national
     extent and pad by ~0.75° (one CAMS grid cell) on each side so border
     districts get cells.
   * `boundaries`:
     * `admin_level`: the warehouse level that facts attach to (districts are
       usually 2).
     * `source: gadm` and `gadm_level`: the GADM level holding the districts.
       Check on https://gadm.org/maps.html (level 1 = regions/provinces,
       level 2 = districts/departments, varies by country).
     * `region_column`, `name_column`, `code_column`: for GADM level *n*:
       `NAME_{n-1}` (or `NAME_1`), `NAME_{n}`, `GID_{n}`.
     * Use `source: file` and `file: data/boundaries/<country>/<file>.shp` for
       national boundaries (e.g. the ministry of health's district file,
       which matches DHIS2 org units better than GADM).
   * `pollutants`: any of `pm25, pm10, o3, no2, "no", so2, nox`. Keep the
     quotes around `"no"`.
   * `period`: `start`, and `end` (a date or `latest`).
   * `enabled: true` to include it in `--all`.

3. Check and preview:

   ```powershell
   gaia countries
   gaia run --country kenya --dry-run
   ```

4. Load a short period first and look at the log line
   `N/M admin units have data`:

   ```powershell
   gaia run --country kenya --start 2024-01 --end 2024-01
   ```

   If some districts have no data, the `area` box is too small.

5. Load the full period (`gaia run --country kenya`). From then on
   `gaia run --all --incremental` keeps it up to date. The dbt models and
   the dashboard pick up the new country automatically.

## Weather

Add `weather: {enabled: true}` to get ERA5 daily weather for the same area and
districts. It is downloaded from the Climate Data Store with the same token.

## Health data

1. Export the monthly district indicators from DHIS2 as CSV or Excel, one
   column per indicator. Put the file under `GAIA_HEALTH_DATA_DIR`, never in
   the repository.
2. Make sure each indicator exists in `air_staging.health_indicator` (add new
   ones there and in `sql/bootstrap/03_reference_data.sql`).
3. Create `config/mappings/<country>_dhis2_districts.csv` with columns
   `dhis2_district_name, admin_code, admin_level, admin_name, mapping_note`.
   Names that exactly match an admin unit at `admin_level` do not need a row.
4. Add a `health:` block to the country file. See `malawi.yml` (month and year
   columns, denominator) or `senegal.yml` (single "January 2021" period column).
5. Run `gaia health --country <country> --dry-run`. Any DHIS2 district that
   cannot be mapped is listed by name. Then run without `--dry-run`.

The exposure–health dbt models join on `admin_id` + month, so the new country
appears in the dashboard tables automatically.
