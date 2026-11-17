with district_daily as (

    select *
    from {{ ref('district_daily_pm25') }}

),

country_daily as (

    select
        observation_date,
        country_id,
        country_name,
        country_code,
        source_id,
        source_system,

        count(distinct admin_id) as districts_observed,
        sum(observation_count) as observation_count,

        round(avg(avg_pm25_ugm3)::numeric, 3) as avg_pm25_ugm3,
        round(min(min_pm25_ugm3)::numeric, 3) as min_pm25_ugm3,
        round(max(max_pm25_ugm3)::numeric, 3) as max_pm25_ugm3

    from district_daily

    group by
        observation_date,
        country_id,
        country_name,
        country_code,
        source_id,
        source_system

)

select *
from country_daily
