-- Monthly weather per district (one row per district, month and source),
-- variables side by side. Precipitation is the monthly total of daily values.

select
    date_trunc('month', observation_date)::date                    as observation_month,
    country_id,
    country_name,
    country_code,
    admin_id,
    admin_name,
    admin_level,
    source_system,

    count(distinct observation_date)                               as days_observed,
    round(avg(value) filter (where variable_code = 't2m')::numeric, 2)  as avg_t2m_c,
    round(max(value) filter (where variable_code = 't2m')::numeric, 2)  as max_daily_t2m_c,
    round(min(value) filter (where variable_code = 't2m')::numeric, 2)  as min_daily_t2m_c,
    round(avg(value) filter (where variable_code = 'rh')::numeric, 1)   as avg_rh_pct,
    round(avg(value) filter (where variable_code = 'wspd')::numeric, 2) as avg_wspd_ms,
    round(sum(value) filter (where variable_code = 'tp')::numeric, 1)   as total_precip_mm

from {{ ref('stg_weather_observations') }}

where admin_id is not null

group by 1, 2, 3, 4, 5, 6, 7, 8
