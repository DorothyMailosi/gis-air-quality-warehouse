-- What is in the warehouse: one row per country, admin level, pollutant and
-- source, plus how many districts have data. Useful as a dashboard card and
-- to check that scheduled pipeline runs keep data current.

with obs as (

    select * from {{ ref('district_monthly_air_quality') }}

),

admin_units as (

    select country_id, level as admin_level, count(*) as admin_units_total
    from {{ source('air_staging', 'admin_unit') }}
    group by 1, 2

)

select
    o.country_id,
    o.country_name,
    o.country_code,
    o.admin_level,
    o.pollutant_code,
    o.source_system,

    min(o.observation_month)                         as first_month,
    max(o.observation_month)                         as last_month,
    count(distinct o.observation_month)              as months_with_data,
    count(distinct o.admin_id)                       as districts_with_data,
    max(a.admin_units_total)                         as admin_units_total,
    sum(o.observation_count)                         as observation_count

from obs o

left join admin_units a
    on a.country_id = o.country_id
   and a.admin_level = o.admin_level

group by 1, 2, 3, 4, 5, 6
