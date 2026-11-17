-- Bootstrap step 0: schemas and PostGIS.
--
-- PostGIS lives in the air_staging schema (this matches the existing
-- warehouse, where geometry columns are typed air_staging.geometry).
-- The database search_path is extended so ST_* functions resolve without
-- a schema prefix in pipeline and dbt SQL.

CREATE SCHEMA IF NOT EXISTS air_staging;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE EXTENSION IF NOT EXISTS postgis SCHEMA air_staging;

DO $$
BEGIN
    EXECUTE format(
        'ALTER DATABASE %I SET search_path = public, air_staging',
        current_database()
    );
END
$$;

SET search_path = public, air_staging;
