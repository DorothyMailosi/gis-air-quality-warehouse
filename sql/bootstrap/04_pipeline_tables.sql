-- Bootstrap step 4: tables owned by the automated pipeline.
-- The pipeline also creates these on first use; they are listed here so the
-- full warehouse layout is visible in one place.

-- Long-format staging area for processed gridded observations
-- (CAMS air quality in µg/m3, ERA5 weather in display units).
CREATE TABLE IF NOT EXISTS air_staging.stg_gridded_observations (
    dataset_code   text             NOT NULL,
    obs_time       timestamptz      NOT NULL,
    latitude       double precision NOT NULL,
    longitude      double precision NOT NULL,
    variable_code  text             NOT NULL,
    value          double precision NOT NULL,
    loaded_at      timestamptz      NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS stg_gridded_observations_dataset_idx
    ON air_staging.stg_gridded_observations (dataset_code);

-- Grid cell -> administrative unit mapping, one row per (grid, country, level, cell, admin).
-- grid is the source grid ('cams_eac4' 0.75°, 'era5' 0.25°).
-- match_method is 'covers' (cell centre inside polygon) or 'nearest'
-- (polygon contains no cell centre, so the closest cell represents it).
CREATE TABLE IF NOT EXISTS air_staging.grid_cell_admin_map (
    grid          text             NOT NULL,
    country_id    integer          NOT NULL REFERENCES air_staging.country (country_id),
    admin_level   integer          NOT NULL,
    latitude      double precision NOT NULL,
    longitude     double precision NOT NULL,
    admin_id      integer          NOT NULL REFERENCES air_staging.admin_unit (admin_id),
    city_id       integer          NOT NULL REFERENCES air_staging.city (city_id),
    match_method  text             NOT NULL,
    distance_km   double precision,
    created_at    timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (grid, country_id, admin_level, latitude, longitude, admin_id)
);

-- One row per pipeline stage per country-month: the audit trail used for
-- incremental runs and for the data-coverage dashboard.
CREATE TABLE IF NOT EXISTS air_staging.pipeline_run_log (
    run_log_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id         text        NOT NULL,
    country_iso2   text        NOT NULL,
    period_month   date,
    stage          text        NOT NULL,
    status         text        NOT NULL,
    rows_affected  bigint,
    details        jsonb,
    started_at     timestamptz NOT NULL,
    finished_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS pipeline_run_log_lookup_idx
    ON air_staging.pipeline_run_log (country_iso2, stage, period_month);
