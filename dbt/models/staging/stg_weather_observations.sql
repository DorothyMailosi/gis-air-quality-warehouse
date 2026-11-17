-- Weather observations with district, country, variable and source names.
-- Rows without an admin unit (legacy city area means) are kept; district
-- models filter them out.

select
    f.obs_time,
    f.obs_time::date   as observation_date,
    f.city_id,
    f.admin_id,
    f.source_id,
    f.value_disp       as value,
    f.qc_status,
    f.lat,
    f.lon,

    c.name             as city_name,
    co.country_id,
    co.name            as country_name,
    co.iso2            as country_code,
    au.name            as admin_name,
    au.level           as admin_level,

    lower(m.code)      as variable_code,
    m.unit,
    s.source_type      as source_system

from {{ source('air_staging', 'fact_meteorology_obs') }} f

inner join {{ source('air_staging', 'city') }} c
    on c.city_id = f.city_id

inner join {{ source('air_staging', 'country') }} co
    on co.country_id = c.country_id

left join {{ source('air_staging', 'admin_unit') }} au
    on au.admin_id = f.admin_id

inner join {{ source('air_staging', 'met_variable') }} m
    on m.met_var_id = f.met_var_id

inner join {{ source('air_staging', 'source_system') }} s
    on s.source_id = f.source_id

where f.value_disp is not null
