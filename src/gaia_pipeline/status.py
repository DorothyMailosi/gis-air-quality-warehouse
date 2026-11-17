"""Warehouse coverage report: what is loaded for each country and pollutant."""

from __future__ import annotations

from .config import Settings
from .db import connection_scope

COVERAGE_SQL = """
SELECT co.iso2,
       co.name                                    AS country,
       au.level                                   AS admin_level,
       p.code                                     AS pollutant,
       s.source_type                              AS source,
       COUNT(DISTINCT f.admin_id)                 AS districts,
       to_char(MIN(f.obs_time), 'YYYY-MM-DD')     AS first_obs,
       to_char(MAX(f.obs_time), 'YYYY-MM-DD')     AS last_obs,
       COUNT(*)                                   AS rows
FROM air_staging.fact_sat_air_quality_obs f
JOIN air_staging.admin_unit au   ON au.admin_id = f.admin_id
JOIN air_staging.country co      ON co.country_id = au.country_id
JOIN air_staging.pollutant p     ON p.pollutant_id = f.pollutant_id
JOIN air_staging.source_system s ON s.source_id = f.source_id
GROUP BY 1, 2, 3, 4, 5
ORDER BY 2, 3, 4
"""


def coverage(settings: Settings) -> list[dict]:
    with connection_scope(settings) as connection, connection.cursor() as cursor:
        cursor.execute(COVERAGE_SQL)
        columns = [d.name for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def format_table(rows: list[dict]) -> str:
    if not rows:
        return "(no data)"
    columns = list(rows[0])
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in columns}
    line = "  ".join(c.ljust(widths[c]) for c in columns)
    out = [line, "  ".join("-" * widths[c] for c in columns)]
    for row in rows:
        out.append("  ".join(str(row[c]).ljust(widths[c]) for c in columns))
    return "\n".join(out)
