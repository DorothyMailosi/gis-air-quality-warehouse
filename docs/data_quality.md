# Known data-quality issues in the existing warehouse

These issues were found while testing the pipeline and dbt models against the
production warehouse in November 2026. None has been changed in the warehouse
yet; each needs a decision by the team.

## 1. Douala gas data is attached to the Dakar admin unit

* **What:** the legacy Douala gas series (NO, NO₂, NOx, O₃, SO₂; 5 × 5,479 daily
  rows, 2010–2024) is stored with `city_id = 1` (Douala) but
  `admin_id = 242` (Région de Dakar) instead of `admin_id = 327`
  ("Douala Area Mean"). Douala's PM2.5/PM10 rows use the correct admin unit.
* **Effect:** any view by admin unit mixes Douala's gas values into Dakar's,
  and Douala has no gas data at the admin level. The dbt uniqueness tests on
  `district_daily_air_quality` / `district_monthly_air_quality` flag this
  (set to *warn* until fixed).
* **Fix (one transaction, after review):**

  ```sql
  UPDATE air_staging.fact_sat_air_quality_obs
  SET admin_id = 327
  WHERE city_id = 1 AND admin_id = 242;
  ```

  Then set both tests back to `severity: error` in `dbt/models/marts/schema.yml`.

## 2. Senegal DHIS2 district → département mapping

`config/mappings/senegal_dhis2_districts.csv` reproduces the mapping currently
used in the warehouse (`analytics.senegal_dhis2_admin_map`). **27 of 83 health
districts** look mapped to the wrong département, e.g.

| Health district | Currently mapped to | Likely département |
|---|---|---|
| Joal-Fadiouth, Popenguine, Thiadiaye | Tambacounda | Mbour |
| Kidira | Kolda | Bakel |
| Richard Toll | Bounkiling | Dagana |
| Pété | Thiès | Podor |
| Médina Yoro Foulah | Salémata | Médina Yoro Foula |
| Pikine / Rufisque | level-4 commune / level-3 arrondissement | Pikine / Rufisque (level 2) |

The full list, with a suggested code and a reason for each, is in the
`suggested_admin_code`, `suggested_admin_name` and `review_note` columns.
**Please have someone who knows the Senegal health-district structure check
them.** To apply them: set `health.use_suggested_mapping: true` in
`config/countries/senegal.yml` (or edit `admin_code` directly) and run
`gaia health --country senegal --refresh`.

Two "Dakar" level-2 units exist (`SEN.1.1_1` and `SN-DEPT-12982139`); Dakar
Centre uses the second one, the other Dakar health districts the first.

## 3. Senegal DHIS2 extract is mostly empty

Of 4,503 district-months in `DHIS2_NCDs_Selected_variables.csv`, values are
present for 442 (severe acute asthma), 1,919 (asthma attacks) and 523 (stroke).
Empty cells mean "not reported", not zero. The old load stored them as rows with
`value = NULL`; the pipeline now skips them, and the health dbt models ignore
NULLs.

## 4. Malawi health data

* **Mzimba was missing:** the export splits it into Mzimba North and Mzimba South.
  The old fix-up script *averaged* the two halves, which is wrong for case counts,
  and the result was never loaded. The pipeline now **sums** both halves
  (counts and population) into Mzimba, adding 84 district-months.
* **Wrong source:** the existing Malawi health rows have `source_id = 4`
  ("ground sensor"). Reloading with the pipeline attaches them to
  "Malawi DHIS2" (`source_id = 11`).
* One Mwanza 2018 row in the export has no month and is skipped (hence 166
  instead of 168 months for Mwanza).

## 5. Ethiopia coverage

18 of 79 Ethiopian zones (including Addis Ababa) have no PM2.5 data, because
no CAMS grid-cell centre falls inside them. The pipeline fills such districts
from the nearest cell; reloading Ethiopia adds them.
