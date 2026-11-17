# Data sources and methods

## CAMS global reanalysis (EAC4)

* Dataset: `cams-global-reanalysis-eac4`, Copernicus Atmosphere Data Store.
* Resolution: 0.75° × 0.75° (≈ 80 km), 3-hourly (00, 03, …, 21 UTC), 2003 onwards.
  ECMWF extends it about once a year; set `copernicus.available_until` accordingly.
* Variables requested:

  | Warehouse code | ADS variable | Level | NetCDF units |
  |---|---|---|---|
  | pm25 | particulate_matter_2.5um | surface | kg m⁻³ |
  | pm10 | particulate_matter_10um | surface | kg m⁻³ |
  | o3 | ozone | model level 60 (lowest) | kg kg⁻¹ |
  | no2 | nitrogen_dioxide | model level 60 | kg kg⁻¹ |
  | no | nitrogen_monoxide | model level 60 | kg kg⁻¹ |
  | so2 | sulphur_dioxide | model level 60 | kg kg⁻¹ |
  | (density) | 2m_temperature, surface_pressure | surface | K, Pa |

* Acknowledgement for publications: *"Generated using Copernicus Atmosphere
  Monitoring Service information [year]"* plus the EAC4 reference
  (Inness et al., 2019, *Atmos. Chem. Phys.*, 19, 3515–3556).

### Unit conversion

* Aerosols: `µg/m³ = kg/m³ × 10⁹`.
* Gases (mass mixing ratio): `µg/m³ = kg/kg × ρ × 10⁹`, with
  `ρ = p_surface / (R_d × T_2m)`, `R_d = 287.05 J kg⁻¹ K⁻¹`, for each grid
  cell and time step. Without temperature or pressure, standard air density
  (1.1839 kg/m³, 25 °C, 1013.25 hPa) is used and the processing report says so.
* NOx = NO + NO₂ (µg/m³).
* Small negative values (numerical noise) are set to 0.

## From grid cells to districts

Each grid cell centre is matched to the district polygon that contains it
(`ST_Covers`). A district's value at each time step is the mean of its cells.
A district with no cell centre inside it (smaller than a grid cell, or stored
as a small polygon) takes the value of the cell nearest to its interior point,
if within `load.nearest_cell_max_km` (100 km). Those rows have
`qc_status = 'processed_nearest'`; the mapping and its distances are in
`air_staging.grid_cell_admin_map`.

At 0.75° resolution, neighbouring small districts often share a cell and so
show the same values. The data describe regional exposure, not
neighbourhood-level differences.

## ERA5 daily weather

* Dataset: `derived-era5-single-levels-daily-statistics` (Climate Data Store),
  daily mean of hourly values, UTC days, 0.25° × 0.25° (≈ 28 km).
* Variables and derivations (per grid cell and day):

  | Code | Unit | From |
  |---|---|---|
  | t2m | °C | 2 m temperature − 273.15 |
  | rh | % | 2 m temperature and 2 m dew point, Magnus formula (a = 17.625, b = 243.04 °C) |
  | wspd | m/s | magnitude of the daily-mean (u10, v10) vector |
  | wdir | deg | direction the wind blows from |
  | tp | mm/day | daily mean hourly precipitation × 24 × 1000 |

  Humidity and wind come from daily means, so humidity is the humidity of
  the mean temperature and dew point, and wind speed is the speed of the
  mean wind vector. That is lower than the mean hourly speed on days when
  the wind changes direction.
* Acknowledgement: Hersbach et al. (2020), *Q. J. R. Meteorol. Soc.*, 146, 1999–2049;
  ERA5 post-processed daily statistics, Copernicus Climate Change Service.

## Administrative boundaries

* Existing warehouse districts are reused as they are, because they are linked to DHIS2 data.
* New countries: GADM 4.1 (https://gadm.org), downloaded at run time. Free for
  academic and other non-commercial use; redistribution not allowed.
* Ethiopia: `eth_adm2` shapefile (79 zones), kept locally in `data/boundaries/ethiopia/`.

## Health data (DHIS2)

District-level monthly indicators from national DHIS2 instances, loaded into
`air_staging.fact_health_district_aggregates` by the `health` stage. This
data is confidential: exports stay in `GAIA_HEALTH_DATA_DIR`, the data stays
inside the warehouse, and none of it is committed to this repository.

| Country | Export | Indicators | Mapping |
|---|---|---|---|
| Malawi | `MALAWI/malawi OPD and ARI data.csv` (2018–2024) | OPD attendance, ARI new cases (under 5); population as denominator | `config/mappings/malawi_dhis2_districts.csv` (Mzimba North + South → Mzimba) |
| Senegal | `SENEGAL/DHIS2_NCDs_Selected_variables.csv` (2021–2025) | Severe acute asthma, asthma attacks, confirmed stroke | `config/mappings/senegal_dhis2_districts.csv` (79 health districts → départements; see data_quality.md #2) |

When several health districts map to one admin unit, their values (and
denominators) are summed.

## Data loaded before this pipeline

The warehouse also holds data loaded by earlier one-off scripts. It is kept unchanged:

| Country | Level | Method |
|---|---|---|
| Cameroon | 1 – "Douala Area Mean" | Area-mean series around Douala, 2010–2024 |
| Senegal | 1 – Région de Dakar; 2 – départements | Dakar area mean; department series, 2010–2024 |
| Malawi | 2 – districts | 2018–2024 |
| Uganda | 3 – districts | PM2.5, 2020–2023 |
| Ethiopia | 2 – zones | PM2.5, January 2022 |

The pipeline adds to this data and never overwrites it unless run with `--refresh`.
