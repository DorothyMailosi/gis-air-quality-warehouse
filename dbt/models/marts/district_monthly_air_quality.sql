-- Monthly statistics per district and pollutant, all countries, compared
-- with the WHO 2021 annual guideline (where one exists).

with daily as (

    select * from {{ ref('district_daily_air_quality') }}

),

monthly as (

    select
        date_trunc('month', observation_date)::date as observation_month,
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

        sum(observation_count)                                   as observation_count,
        count(*)                                                 as days_observed,
        round(sum(avg_ugm3 * observation_count) / nullif(sum(observation_count), 0), 3)
                                                                 as avg_ugm3,
        min(min_ugm3)                                            as min_ugm3,
        max(max_ugm3)                                            as max_ugm3,
        round(avg(representative_lat), 6)                        as representative_lat,
        round(avg(representative_lon), 6)                        as representative_lon

    from daily

    group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11

),

annual_guideline as (

    select pollutant_code, guideline_ugm3
    from {{ ref('who_air_quality_guidelines') }}
    where averaging_period = 'annual'

)

select
    m.*,
    g.guideline_ugm3                                 as who_annual_guideline_ugm3,
    round(m.avg_ugm3 / nullif(g.guideline_ugm3, 0), 2) as who_annual_guideline_ratio

from monthly m

left join annual_guideline g
    on g.pollutant_code = m.pollutant_code
