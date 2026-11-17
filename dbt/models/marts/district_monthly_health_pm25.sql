-- Monthly district health indicators linked to monthly PM2.5 exposure.
-- Covers every country that has district health data (Malawi and Senegal
-- today); previously this model was restricted to Malawi.
-- The original columns come first, in the original order.

with monthly_health as (

    select
        period_start::date as observation_month,
        admin_id,
        indicator_id,

        sum(value)       as health_value,
        sum(numerator)   as numerator,
        max(denominator) as denominator,
        count(*)         as health_record_count

    from {{ source('air_staging', 'fact_health_district_aggregates') }}

    where period_type = 'monthly'
      and period_start is not null
      and admin_id is not null
      and indicator_id is not null
      -- empty DHIS2 values mean "not reported", not zero (common in the Senegal extract)
      and value is not null

    group by 1, 2, 3

),

monthly_pm25 as (

    select
        observation_month,
        admin_id,
        country_id,
        country_name,
        country_code,
        admin_name,
        district_name,

        sum(observation_count) as pm25_observation_count,

        round(
            (sum(avg_pm25_ugm3 * observation_count) / nullif(sum(observation_count), 0))::numeric,
            3
        ) as avg_pm25_ugm3,

        min(min_pm25_ugm3) as min_pm25_ugm3,
        max(max_pm25_ugm3) as max_pm25_ugm3

    from {{ ref('district_monthly_pm25') }}

    group by 1, 2, 3, 4, 5, 6, 7

)

select
    p.observation_month,

    p.country_id,
    p.country_name,
    p.country_code,

    p.admin_id,
    p.admin_name,
    p.district_name,

    h.indicator_id,
    h.health_value,
    h.numerator,
    h.denominator,
    h.health_record_count,

    p.avg_pm25_ugm3,
    p.min_pm25_ugm3,
    p.max_pm25_ugm3,
    p.pm25_observation_count,

    hi.code         as indicator_code,
    hi.display_name as indicator_name,
    hi.category     as indicator_category

from monthly_health h

inner join monthly_pm25 p
    on h.admin_id = p.admin_id
   and h.observation_month = p.observation_month

left join {{ source('air_staging', 'health_indicator') }} hi
    on hi.indicator_id = h.indicator_id
