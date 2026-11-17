with observations as (

    select *
    from {{ ref('stg_pm25_observations') }}

),

country_stats as (

    select
        country_id,
        country_name,
        country_code,
        source_id,
        source_system,

        count(*) as observation_count,

        round(avg(value_ugm3)::numeric, 3) as avg_pm25_ugm3,
        round(min(value_ugm3)::numeric, 3) as min_pm25_ugm3,
        round(max(value_ugm3)::numeric, 3) as max_pm25_ugm3,

        round(
            percentile_cont(0.95)
            within group (order by value_ugm3)::numeric,
            3
        ) as p95_pm25_ugm3

    from observations

    group by
        country_id,
        country_name,
        country_code,
        source_id,
        source_system

),

ranked as (

    select
        *,
        rank() over (
            order by avg_pm25_ugm3 desc
        ) as average_pm25_rank,

        rank() over (
            order by p95_pm25_ugm3 desc
        ) as p95_pm25_rank,

        rank() over (
            order by max_pm25_ugm3 desc
        ) as maximum_pm25_rank

    from country_stats

)

select *
from ranked