-- Bootstrap step 2: monthly range partitions for the partitioned fact tables.
--
-- CAMS EAC4 starts in 2003. The pipeline also creates any missing month
-- partition on demand before loading, so this range is only a starting point.

DO $$
DECLARE
    parent      text;
    month_start date;
BEGIN
    FOREACH parent IN ARRAY ARRAY[
        'fact_sat_air_quality_obs',
        'fact_meteorology_obs',
        'fact_sensor_air_quality_obs'
    ]
    LOOP
        month_start := DATE '2003-01-01';
        WHILE month_start < DATE '2031-01-01' LOOP
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS air_staging.%I '
                'PARTITION OF air_staging.%I '
                'FOR VALUES FROM (%L) TO (%L)',
                parent || '_' || to_char(month_start, 'YYYY_MM'),
                parent,
                month_start::timestamptz,
                (month_start + INTERVAL '1 month')::timestamptz
            );
            month_start := (month_start + INTERVAL '1 month')::date;
        END LOOP;
    END LOOP;
END
$$;
