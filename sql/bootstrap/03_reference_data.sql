-- Bootstrap step 3: reference (dimension) rows.
--
-- IDs match the existing warehouse so that dashboards and saved queries keep
-- working on a rebuilt database. Re-running this file is safe.

INSERT INTO air_staging.country (country_id, iso2, name) VALUES
    (1, 'CM', 'Cameroon'),
    (2, 'SN', 'Senegal'),
    (3, 'MW', 'Malawi'),
    (4, 'UG', 'Uganda'),
    (5, 'ET', 'Ethiopia')
ON CONFLICT DO NOTHING;

INSERT INTO air_staging.pollutant (pollutant_id, code, description, unit) VALUES
    (1, 'o3',   'Ozone',                     'µg/m3'),
    (2, 'no2',  'Nitrogen dioxide',          'µg/m3'),
    (3, 'no',   'Nitrogen monoxide',         'µg/m3'),
    (4, 'so2',  'Sulfur dioxide',            'µg/m3'),
    (5, 'nox',  'NO + NO2',                  'µg/m3'),
    (6, 'pm25', 'Particulate matter 2.5 µm', 'µg/m3'),
    (7, 'pm10', 'Particulate matter 10 µm',  'µg/m3')
ON CONFLICT DO NOTHING;

INSERT INTO air_staging.source_system (source_id, source_type, name, version, url) VALUES
    (1,  'CAMS',   'copernicus-converted', 'eac4', 'https://ads.atmosphere.copernicus.eu'),
    (4,  'SENSOR', 'ground sensor',        NULL,   NULL),
    (11, 'DHIS2',  'Malawi DHIS2',         NULL,   'https://dhis2.moh.gov.mw'),
    (12, 'DHIS2',  'Senegal DHIS2',        NULL,   NULL)
ON CONFLICT DO NOTHING;

INSERT INTO air_staging.health_indicator (indicator_id, code, display_name, category, unit) VALUES
    (1, 'ari_cases',           'Acute Respiratory Infection Cases', 'Morbidity',   'cases'),
    (2, 'malaria_cases',       'Malaria Cases',                     'Morbidity',   'cases'),
    (3, 'diarrhea_cases',      'Diarrheal Disease Cases',           'Morbidity',   'cases'),
    (4, 'opd_attendance',      'OPD Attendance',                    'Utilization', 'count'),
    (5, 'severe_acute_asthma', 'Severe Acute Asthma Cases',         'Morbidity',   'cases'),
    (6, 'asthma_attack',       'Asthma Attack Cases',               'Morbidity',   'cases'),
    (7, 'confirmed_stroke',    'Confirmed Stroke Cases',            'Morbidity',   'cases')
ON CONFLICT DO NOTHING;

INSERT INTO air_staging.met_variable (met_var_id, code, display_name, unit) VALUES
    (1, 't2m',  '2 m temperature',   '°C'),
    (2, 'rh',   'Relative humidity', '%'),
    (3, 'wspd', 'Wind speed',        'm/s'),
    (4, 'wdir', 'Wind direction',    'deg')
ON CONFLICT DO NOTHING;

SELECT setval('air_staging.country_country_id_seq',
              (SELECT max(country_id) FROM air_staging.country));
SELECT setval('air_staging.pollutant_pollutant_id_seq',
              (SELECT max(pollutant_id) FROM air_staging.pollutant));
SELECT setval('air_staging.source_system_source_id_seq',
              (SELECT max(source_id) FROM air_staging.source_system));
SELECT setval('air_staging.health_indicator_indicator_id_seq',
              (SELECT max(indicator_id) FROM air_staging.health_indicator));
SELECT setval('air_staging.met_variable_met_var_id_seq',
              (SELECT max(met_var_id) FROM air_staging.met_variable));
