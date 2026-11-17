with observations as (

    select *
    from {{ ref('stg_pm25_observations') }}

),

monthly as (

    select
        date_trunc('month', obs_time)::date as observation_month,
        country_id,
        country_name,
        country_code,
        admin_id,
        admin_name,
        district_name,
        source_id,
        source_system,

        count(*) as observation_count,
        count(distinct date_trunc('day', obs_time)::date) as days_observed,

        round(avg(value_ugm3)::numeric, 3) as avg_pm25_ugm3,
        round(min(value_ugm3)::numeric, 3) as min_pm25_ugm3,
        round(max(value_ugm3)::numeric, 3) as max_pm25_ugm3,

        round(avg(lat)::numeric, 6) as representative_lat,
        round(avg(lon)::numeric, 6) as representative_lon

    from observations

    group by
        date_trunc('month', obs_time)::date,
        country_id,
        country_name,
        country_code,
        admin_id,
        admin_name,
        district_name,
        source_id,
        source_system

)

select *
from monthly
