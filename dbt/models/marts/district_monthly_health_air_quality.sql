-- One row per district, month and health indicator, with monthly exposure
-- to each pollutant side by side, for exposure-health analysis.

with health as (

    select
        period_start::date as observation_month,
        admin_id,
        indicator_id,
        sum(value)         as health_value,
        sum(numerator)     as numerator,
        max(denominator)   as denominator
    from {{ source('air_staging', 'fact_health_district_aggregates') }}
    where period_type = 'monthly'
      and period_start is not null
      and admin_id is not null
      and indicator_id is not null
      -- empty DHIS2 values mean "not reported", not zero
      and value is not null
    group by 1, 2, 3

),

exposure as (

    select
        observation_month,
        admin_id,
        max(country_id)    as country_id,
        max(country_name)  as country_name,
        max(country_code)  as country_code,
        max(admin_name)    as admin_name,
        max(district_name) as district_name,
        {% for p in ['pm25', 'pm10', 'no2', 'o3', 'so2', 'no', 'nox'] %}
        round(
            sum(avg_ugm3 * observation_count) filter (where pollutant_code = '{{ p }}')
            / nullif(sum(observation_count) filter (where pollutant_code = '{{ p }}'), 0),
            3
        ) as avg_{{ p }}_ugm3{{ "," if not loop.last }}
        {% endfor %}
    from {{ ref('district_monthly_air_quality') }}
    group by 1, 2

),

weather as (

    select
        observation_month,
        admin_id,
        avg(avg_t2m_c)       as avg_t2m_c,
        avg(avg_rh_pct)      as avg_rh_pct,
        avg(total_precip_mm) as total_precip_mm
    from {{ ref('district_monthly_weather') }}
    where source_system = 'ERA5'
    group by 1, 2

)

select
    e.observation_month,
    e.country_id,
    e.country_name,
    e.country_code,
    e.admin_id,
    e.admin_name,
    e.district_name,
    h.indicator_id,
    hi.code         as indicator_code,
    hi.display_name as indicator_name,
    hi.category     as indicator_category,
    h.health_value,
    h.numerator,
    h.denominator,
    e.avg_pm25_ugm3,
    e.avg_pm10_ugm3,
    e.avg_no2_ugm3,
    e.avg_o3_ugm3,
    e.avg_so2_ugm3,
    e.avg_no_ugm3,
    e.avg_nox_ugm3,
    w.avg_t2m_c,
    w.avg_rh_pct,
    w.total_precip_mm

from health h

inner join exposure e
    on e.admin_id = h.admin_id
   and e.observation_month = h.observation_month

left join weather w
    on w.admin_id = h.admin_id
   and w.observation_month = h.observation_month

left join {{ source('air_staging', 'health_indicator') }} hi
    on hi.indicator_id = h.indicator_id
