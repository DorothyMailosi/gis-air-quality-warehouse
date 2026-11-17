-- All satellite/reanalysis air-quality observations, every country and
-- pollutant, enriched with country, district, pollutant and source names.

select
    f.obs_time,
    f.city_id,
    f.admin_id,
    f.pollutant_id,
    f.source_id,
    f.value_ugm3,
    f.qc_status,
    f.lat,
    f.lon,
    f.geom,

    c.name        as district_name,
    c.country_id,

    co.name       as country_name,
    co.iso2       as country_code,

    au.name       as admin_name,
    au.level      as admin_level,

    lower(p.code) as pollutant_code,
    s.source_type as source_system

from {{ source('air_staging', 'fact_sat_air_quality_obs') }} f

inner join {{ source('air_staging', 'city') }} c
    on f.city_id = c.city_id

inner join {{ source('air_staging', 'country') }} co
    on c.country_id = co.country_id

inner join {{ source('air_staging', 'admin_unit') }} au
    on f.admin_id = au.admin_id

inner join {{ source('air_staging', 'pollutant') }} p
    on f.pollutant_id = p.pollutant_id

inner join {{ source('air_staging', 'source_system') }} s
    on f.source_id = s.source_id

where f.value_ugm3 is not null
