-- PM2.5 subset of stg_air_quality_observations.
-- Columns are unchanged from the original model so existing Metabase
-- questions keep working.

select
    obs_time,
    city_id,
    admin_id,
    pollutant_id,
    source_id,
    value_ugm3,
    qc_status,
    lat,
    lon,
    geom,
    district_name,
    country_id,
    country_name,
    country_code,
    admin_name,
    admin_level,
    pollutant_code,
    source_system

from {{ ref('stg_air_quality_observations') }}

where pollutant_code = 'pm25'
