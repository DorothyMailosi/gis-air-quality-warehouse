-- Country-level monthly summary per pollutant, with the share of
-- district-days above the WHO short-term guideline.

with monthly as (

    select * from {{ ref('district_monthly_air_quality') }}

),

exceedance as (

    select
        date_trunc('month', observation_date)::date as observation_month,
        country_id,
        pollutant_code,
        count(*)                as district_days,
        sum(exceeds_guideline)  as district_days_exceeding
    from {{ ref('district_daily_who_exceedance') }}
    group by 1, 2, 3

),

country as (

    select
        observation_month,
        country_id,
        country_name,
        country_code,
        admin_level,
        pollutant_code,
        source_system,

        count(distinct admin_id)                                           as districts_observed,
        sum(observation_count)                                             as observation_count,
        round(sum(avg_ugm3 * observation_count) / nullif(sum(observation_count), 0), 3)
                                                                           as avg_ugm3,
        min(min_ugm3)                                                      as min_ugm3,
        max(max_ugm3)                                                      as max_ugm3,
        max(who_annual_guideline_ugm3)                                     as who_annual_guideline_ugm3

    from monthly

    group by 1, 2, 3, 4, 5, 6, 7

)

select
    c.*,
    e.district_days,
    e.district_days_exceeding,
    round(100.0 * e.district_days_exceeding / nullif(e.district_days, 0), 1)
        as pct_district_days_exceeding

from country c

left join exceedance e
    on e.observation_month = c.observation_month
   and e.country_id = c.country_id
   and e.pollutant_code = c.pollutant_code
