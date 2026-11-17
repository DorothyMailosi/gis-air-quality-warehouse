-- Core warehouse schema (air_staging), exported from the live warehouse with
-- pg_dump --schema-only. Monthly partitions are created in 02_partitions.sql.

--
-- PostgreSQL database dump
--

-- Dumped from database version 15.6
-- Dumped by pg_dump version 15.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET search_path = public, air_staging;  -- PostGIS may live in either schema
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: air_staging; Type: SCHEMA; Schema: -; Owner: -
--

-- schema is created in 00_extensions.sql

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: admin_unit; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.admin_unit (
    admin_id integer NOT NULL,
    parent_id integer,
    country_id integer NOT NULL,
    level integer NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    geom geometry(MultiPolygon,4326) NOT NULL,
    polygon_id integer,
    CONSTRAINT admin_unit_level_check CHECK (((level >= 1) AND (level <= 5)))
);

--
-- Name: admin_unit_admin_id_seq; Type: SEQUENCE; Schema: air_staging; Owner: -
--

CREATE SEQUENCE air_staging.admin_unit_admin_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: admin_unit_admin_id_seq; Type: SEQUENCE OWNED BY; Schema: air_staging; Owner: -
--

ALTER SEQUENCE air_staging.admin_unit_admin_id_seq OWNED BY air_staging.admin_unit.admin_id;

--
-- Name: city; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.city (
    city_id integer NOT NULL,
    country_id integer NOT NULL,
    name text NOT NULL,
    lat double precision,
    lon double precision
);

--
-- Name: city_city_id_seq; Type: SEQUENCE; Schema: air_staging; Owner: -
--

CREATE SEQUENCE air_staging.city_city_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: city_city_id_seq; Type: SEQUENCE OWNED BY; Schema: air_staging; Owner: -
--

ALTER SEQUENCE air_staging.city_city_id_seq OWNED BY air_staging.city.city_id;

--
-- Name: country; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.country (
    country_id integer NOT NULL,
    iso2 character(2) NOT NULL,
    name text NOT NULL
);

--
-- Name: country_country_id_seq; Type: SEQUENCE; Schema: air_staging; Owner: -
--

CREATE SEQUENCE air_staging.country_country_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: country_country_id_seq; Type: SEQUENCE OWNED BY; Schema: air_staging; Owner: -
--

ALTER SEQUENCE air_staging.country_country_id_seq OWNED BY air_staging.country.country_id;

--
-- Name: fact_health_district_aggregates; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.fact_health_district_aggregates (
    id bigint,
    admin_id integer,
    indicator_id integer,
    source_id integer,
    period_start date,
    period_end date,
    period_type text,
    age_group_id integer,
    value double precision,
    numerator double precision,
    denominator double precision,
    qc_status text,
    attrs jsonb
);

--
-- Name: fact_meteorology_obs; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.fact_meteorology_obs (
    id bigint NOT NULL,
    obs_time timestamp with time zone NOT NULL,
    city_id integer NOT NULL,
    admin_id integer,
    met_var_id integer NOT NULL,
    source_id integer NOT NULL,
    value_disp double precision,
    qc_status text,
    lat double precision,
    lon double precision,
    geom geometry(Point,4326) GENERATED ALWAYS AS (st_setsrid(st_makepoint(lon, lat), 4326)) STORED
)
PARTITION BY RANGE (obs_time);

--
-- Name: fact_meteorology_obs_id_seq; Type: SEQUENCE; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_meteorology_obs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME air_staging.fact_meteorology_obs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: fact_sat_air_quality_obs; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.fact_sat_air_quality_obs (
    id bigint NOT NULL,
    obs_time timestamp with time zone NOT NULL,
    city_id integer NOT NULL,
    admin_id integer NOT NULL,
    pollutant_id integer NOT NULL,
    source_id integer NOT NULL,
    value_ugm3 double precision,
    qc_status text,
    lat double precision,
    lon double precision,
    geom geometry(Point,4326) GENERATED ALWAYS AS (st_setsrid(st_makepoint(lon, lat), 4326)) STORED
)
PARTITION BY RANGE (obs_time);

--
-- Name: fact_sat_air_quality_obs_id_seq; Type: SEQUENCE; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_sat_air_quality_obs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME air_staging.fact_sat_air_quality_obs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: fact_sat_air_quality_obs_mart; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.fact_sat_air_quality_obs_mart (
    month date,
    city_id integer,
    admin_id integer,
    pollutant_id integer,
    source_id integer,
    monthly_avg_ugm3 double precision,
    monthly_min_ugm3 double precision,
    monthly_max_ugm3 double precision,
    n_obs bigint,
    n_ok bigint
);

--
-- Name: fact_sensor_air_quality_obs; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.fact_sensor_air_quality_obs (
    id bigint NOT NULL,
    obs_time timestamp with time zone NOT NULL,
    city_id integer NOT NULL,
    admin_id integer,
    pollutant_id integer NOT NULL,
    source_id integer NOT NULL,
    value_ugm3 double precision,
    qc_status text,
    lat double precision,
    lon double precision,
    geom geometry(Point,4326) GENERATED ALWAYS AS (st_setsrid(st_makepoint(lon, lat), 4326)) STORED
)
PARTITION BY RANGE (obs_time);

--
-- Name: fact_sensor_air_quality_obs_id_seq; Type: SEQUENCE; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_sensor_air_quality_obs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME air_staging.fact_sensor_air_quality_obs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: health_indicator; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.health_indicator (
    indicator_id integer NOT NULL,
    code text NOT NULL,
    display_name text NOT NULL,
    category text,
    unit text,
    description text,
    attrs jsonb
);

--
-- Name: health_indicator_indicator_id_seq; Type: SEQUENCE; Schema: air_staging; Owner: -
--

CREATE SEQUENCE air_staging.health_indicator_indicator_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: health_indicator_indicator_id_seq; Type: SEQUENCE OWNED BY; Schema: air_staging; Owner: -
--

ALTER SEQUENCE air_staging.health_indicator_indicator_id_seq OWNED BY air_staging.health_indicator.indicator_id;

--
-- Name: landing_cams_comp; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.landing_cams_comp (
    ingested_at timestamp with time zone DEFAULT now(),
    source_id integer,
    city_id integer,
    time_ts timestamp with time zone NOT NULL,
    lat double precision,
    lon double precision,
    pollutant_code text NOT NULL,
    value_si double precision,
    attrs jsonb
);

--
-- Name: landing_sensor_obs; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.landing_sensor_obs (
    ingested_at timestamp with time zone DEFAULT now(),
    source_id integer,
    city_id integer,
    site_code text,
    time_ts timestamp with time zone NOT NULL,
    pollutant_code text NOT NULL,
    value_ugm3 double precision,
    qc_flag text,
    lat double precision,
    lon double precision,
    attrs jsonb
);

--
-- Name: met_variable; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.met_variable (
    met_var_id integer NOT NULL,
    code text NOT NULL,
    display_name text NOT NULL,
    unit text NOT NULL
);

--
-- Name: met_variable_met_var_id_seq; Type: SEQUENCE; Schema: air_staging; Owner: -
--

CREATE SEQUENCE air_staging.met_variable_met_var_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: met_variable_met_var_id_seq; Type: SEQUENCE OWNED BY; Schema: air_staging; Owner: -
--

ALTER SEQUENCE air_staging.met_variable_met_var_id_seq OWNED BY air_staging.met_variable.met_var_id;

--
-- Name: pollutant; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.pollutant (
    pollutant_id integer NOT NULL,
    code text NOT NULL,
    description text,
    unit text DEFAULT 'µg/m3'::text NOT NULL
);

--
-- Name: pollutant_pollutant_id_seq; Type: SEQUENCE; Schema: air_staging; Owner: -
--

CREATE SEQUENCE air_staging.pollutant_pollutant_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: pollutant_pollutant_id_seq; Type: SEQUENCE OWNED BY; Schema: air_staging; Owner: -
--

ALTER SEQUENCE air_staging.pollutant_pollutant_id_seq OWNED BY air_staging.pollutant.pollutant_id;

--
-- Name: source_system; Type: TABLE; Schema: air_staging; Owner: -
--

CREATE TABLE air_staging.source_system (
    source_id integer NOT NULL,
    source_type text NOT NULL,
    name text NOT NULL,
    version text,
    url text
);

--
-- Name: source_system_source_id_seq; Type: SEQUENCE; Schema: air_staging; Owner: -
--

CREATE SEQUENCE air_staging.source_system_source_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: source_system_source_id_seq; Type: SEQUENCE OWNED BY; Schema: air_staging; Owner: -
--

ALTER SEQUENCE air_staging.source_system_source_id_seq OWNED BY air_staging.source_system.source_id;

--
-- Name: admin_unit admin_id; Type: DEFAULT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.admin_unit ALTER COLUMN admin_id SET DEFAULT nextval('air_staging.admin_unit_admin_id_seq'::regclass);

--
-- Name: city city_id; Type: DEFAULT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.city ALTER COLUMN city_id SET DEFAULT nextval('air_staging.city_city_id_seq'::regclass);

--
-- Name: country country_id; Type: DEFAULT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.country ALTER COLUMN country_id SET DEFAULT nextval('air_staging.country_country_id_seq'::regclass);

--
-- Name: health_indicator indicator_id; Type: DEFAULT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.health_indicator ALTER COLUMN indicator_id SET DEFAULT nextval('air_staging.health_indicator_indicator_id_seq'::regclass);

--
-- Name: met_variable met_var_id; Type: DEFAULT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.met_variable ALTER COLUMN met_var_id SET DEFAULT nextval('air_staging.met_variable_met_var_id_seq'::regclass);

--
-- Name: pollutant pollutant_id; Type: DEFAULT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.pollutant ALTER COLUMN pollutant_id SET DEFAULT nextval('air_staging.pollutant_pollutant_id_seq'::regclass);

--
-- Name: source_system source_id; Type: DEFAULT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.source_system ALTER COLUMN source_id SET DEFAULT nextval('air_staging.source_system_source_id_seq'::regclass);

--
-- Name: admin_unit admin_unit_country_id_level_code_key; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.admin_unit
    ADD CONSTRAINT admin_unit_country_id_level_code_key UNIQUE (country_id, level, code);

--
-- Name: admin_unit admin_unit_pkey; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.admin_unit
    ADD CONSTRAINT admin_unit_pkey PRIMARY KEY (admin_id);

--
-- Name: city city_country_id_name_key; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.city
    ADD CONSTRAINT city_country_id_name_key UNIQUE (country_id, name);

--
-- Name: city city_pkey; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.city
    ADD CONSTRAINT city_pkey PRIMARY KEY (city_id);

--
-- Name: country country_iso2_key; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.country
    ADD CONSTRAINT country_iso2_key UNIQUE (iso2);

--
-- Name: country country_pkey; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.country
    ADD CONSTRAINT country_pkey PRIMARY KEY (country_id);

--
-- Name: fact_meteorology_obs fact_met_pk; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.fact_meteorology_obs
    ADD CONSTRAINT fact_met_pk PRIMARY KEY (obs_time, city_id, met_var_id, source_id);

--
-- Name: fact_sat_air_quality_obs fact_sat_aq_pk; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.fact_sat_air_quality_obs
    ADD CONSTRAINT fact_sat_aq_pk PRIMARY KEY (obs_time, city_id, admin_id, pollutant_id, source_id);

--
-- Name: fact_sensor_air_quality_obs fact_sensor_aq_pk; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.fact_sensor_air_quality_obs
    ADD CONSTRAINT fact_sensor_aq_pk PRIMARY KEY (obs_time, city_id, pollutant_id, source_id);

--
-- Name: health_indicator health_indicator_code_key; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.health_indicator
    ADD CONSTRAINT health_indicator_code_key UNIQUE (code);

--
-- Name: health_indicator health_indicator_pkey; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.health_indicator
    ADD CONSTRAINT health_indicator_pkey PRIMARY KEY (indicator_id);

--
-- Name: met_variable met_variable_code_key; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.met_variable
    ADD CONSTRAINT met_variable_code_key UNIQUE (code);

--
-- Name: met_variable met_variable_pkey; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.met_variable
    ADD CONSTRAINT met_variable_pkey PRIMARY KEY (met_var_id);

--
-- Name: pollutant pollutant_code_key; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.pollutant
    ADD CONSTRAINT pollutant_code_key UNIQUE (code);

--
-- Name: pollutant pollutant_pkey; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.pollutant
    ADD CONSTRAINT pollutant_pkey PRIMARY KEY (pollutant_id);

--
-- Name: source_system source_system_pkey; Type: CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.source_system
    ADD CONSTRAINT source_system_pkey PRIMARY KEY (source_id);

--
-- Name: idx_fact_met_geom; Type: INDEX; Schema: air_staging; Owner: -
--

CREATE INDEX idx_fact_met_geom ON ONLY air_staging.fact_meteorology_obs USING gist (geom);

--
-- Name: idx_fact_sat_geom; Type: INDEX; Schema: air_staging; Owner: -
--

CREATE INDEX idx_fact_sat_geom ON ONLY air_staging.fact_sat_air_quality_obs USING gist (geom);

--
-- Name: idx_fact_sensor_geom; Type: INDEX; Schema: air_staging; Owner: -
--

CREATE INDEX idx_fact_sensor_geom ON ONLY air_staging.fact_sensor_air_quality_obs USING gist (geom);

--
-- Name: idx_admin_unit_geom; Type: INDEX; Schema: air_staging; Owner: -
--

CREATE INDEX idx_admin_unit_geom ON air_staging.admin_unit USING gist (geom);

--
-- Name: admin_unit admin_unit_country_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.admin_unit
    ADD CONSTRAINT admin_unit_country_id_fkey FOREIGN KEY (country_id) REFERENCES air_staging.country(country_id);

--
-- Name: admin_unit admin_unit_parent_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.admin_unit
    ADD CONSTRAINT admin_unit_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES air_staging.admin_unit(admin_id);

--
-- Name: city city_country_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.city
    ADD CONSTRAINT city_country_id_fkey FOREIGN KEY (country_id) REFERENCES air_staging.country(country_id);

--
-- Name: fact_meteorology_obs fact_meteorology_obs_admin_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_meteorology_obs
    ADD CONSTRAINT fact_meteorology_obs_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES air_staging.admin_unit(admin_id);

--
-- Name: fact_meteorology_obs fact_meteorology_obs_city_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_meteorology_obs
    ADD CONSTRAINT fact_meteorology_obs_city_id_fkey FOREIGN KEY (city_id) REFERENCES air_staging.city(city_id);

--
-- Name: fact_meteorology_obs fact_meteorology_obs_met_var_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_meteorology_obs
    ADD CONSTRAINT fact_meteorology_obs_met_var_id_fkey FOREIGN KEY (met_var_id) REFERENCES air_staging.met_variable(met_var_id);

--
-- Name: fact_meteorology_obs fact_meteorology_obs_source_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_meteorology_obs
    ADD CONSTRAINT fact_meteorology_obs_source_id_fkey FOREIGN KEY (source_id) REFERENCES air_staging.source_system(source_id);

--
-- Name: fact_sat_air_quality_obs fact_sat_air_quality_obs_admin_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_sat_air_quality_obs
    ADD CONSTRAINT fact_sat_air_quality_obs_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES air_staging.admin_unit(admin_id);

--
-- Name: fact_sat_air_quality_obs fact_sat_air_quality_obs_city_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_sat_air_quality_obs
    ADD CONSTRAINT fact_sat_air_quality_obs_city_id_fkey FOREIGN KEY (city_id) REFERENCES air_staging.city(city_id);

--
-- Name: fact_sat_air_quality_obs fact_sat_air_quality_obs_pollutant_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_sat_air_quality_obs
    ADD CONSTRAINT fact_sat_air_quality_obs_pollutant_id_fkey FOREIGN KEY (pollutant_id) REFERENCES air_staging.pollutant(pollutant_id);

--
-- Name: fact_sat_air_quality_obs fact_sat_air_quality_obs_source_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_sat_air_quality_obs
    ADD CONSTRAINT fact_sat_air_quality_obs_source_id_fkey FOREIGN KEY (source_id) REFERENCES air_staging.source_system(source_id);

--
-- Name: fact_sensor_air_quality_obs fact_sensor_air_quality_obs_admin_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_sensor_air_quality_obs
    ADD CONSTRAINT fact_sensor_air_quality_obs_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES air_staging.admin_unit(admin_id);

--
-- Name: fact_sensor_air_quality_obs fact_sensor_air_quality_obs_city_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_sensor_air_quality_obs
    ADD CONSTRAINT fact_sensor_air_quality_obs_city_id_fkey FOREIGN KEY (city_id) REFERENCES air_staging.city(city_id);

--
-- Name: fact_sensor_air_quality_obs fact_sensor_air_quality_obs_pollutant_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_sensor_air_quality_obs
    ADD CONSTRAINT fact_sensor_air_quality_obs_pollutant_id_fkey FOREIGN KEY (pollutant_id) REFERENCES air_staging.pollutant(pollutant_id);

--
-- Name: fact_sensor_air_quality_obs fact_sensor_air_quality_obs_source_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE air_staging.fact_sensor_air_quality_obs
    ADD CONSTRAINT fact_sensor_air_quality_obs_source_id_fkey FOREIGN KEY (source_id) REFERENCES air_staging.source_system(source_id);

--
-- Name: landing_cams_comp landing_cams_comp_city_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.landing_cams_comp
    ADD CONSTRAINT landing_cams_comp_city_id_fkey FOREIGN KEY (city_id) REFERENCES air_staging.city(city_id);

--
-- Name: landing_cams_comp landing_cams_comp_source_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.landing_cams_comp
    ADD CONSTRAINT landing_cams_comp_source_id_fkey FOREIGN KEY (source_id) REFERENCES air_staging.source_system(source_id);

--
-- Name: landing_sensor_obs landing_sensor_obs_city_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.landing_sensor_obs
    ADD CONSTRAINT landing_sensor_obs_city_id_fkey FOREIGN KEY (city_id) REFERENCES air_staging.city(city_id);

--
-- Name: landing_sensor_obs landing_sensor_obs_source_id_fkey; Type: FK CONSTRAINT; Schema: air_staging; Owner: -
--

ALTER TABLE ONLY air_staging.landing_sensor_obs
    ADD CONSTRAINT landing_sensor_obs_source_id_fkey FOREIGN KEY (source_id) REFERENCES air_staging.source_system(source_id);

--
-- PostgreSQL database dump complete
--
