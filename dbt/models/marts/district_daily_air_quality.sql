-- Daily statistics per district and pollutant, all countries.

select
    date_trunc('day', obs_time)::date  as observation_date,
    country_id,
    country_name,
    country_code,
    admin_id,
    admin_name,
    admin_level,
    district_name,
    pollutant_code,
    source_id,
    source_system,

    count(*)                                as observation_count,
    round(avg(value_ugm3)::numeric, 3)      as avg_ugm3,
    round(min(value_ugm3)::numeric, 3)      as min_ugm3,
    round(max(value_ugm3)::numeric, 3)      as max_ugm3,
    round(avg(lat)::numeric, 6)             as representative_lat,
    round(avg(lon)::numeric, 6)             as representative_lon

from {{ ref('stg_air_quality_observations') }}

group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
