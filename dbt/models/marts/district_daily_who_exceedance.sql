-- Daily district means compared with the WHO 2021 short-term guidelines.
-- Ozone's guideline is an 8-hour mean; the daily mean used here is lower
-- than the peak 8-hour mean, so ozone exceedances are under-counted.

with daily as (

    select * from {{ ref('district_daily_air_quality') }}

),

guideline as (

    select pollutant_code, averaging_period, guideline_ugm3
    from {{ ref('who_air_quality_guidelines') }}
    where averaging_period in ('24h', '8h')

)

select
    d.observation_date,
    d.country_id,
    d.country_name,
    d.country_code,
    d.admin_id,
    d.admin_name,
    d.admin_level,
    d.district_name,
    d.pollutant_code,
    d.source_system,
    d.avg_ugm3,

    g.averaging_period                               as guideline_period,
    g.guideline_ugm3,
    round(d.avg_ugm3 / nullif(g.guideline_ugm3, 0), 2) as guideline_ratio,
    (d.avg_ugm3 > g.guideline_ugm3)::int             as exceeds_guideline

from daily d

inner join guideline g
    on g.pollutant_code = d.pollutant_code
