"""Download CAMS EAC4 data from the Copernicus Atmosphere Data Store.

Requests are split by country, month and level type:

    data/raw/<ISO3>/<ISO3>_eac4_single_<YYYY-MM>.nc   aerosols (+ t2m, sp)
    data/raw/<ISO3>/<ISO3>_eac4_model_<YYYY-MM>.nc    gases at model level 60

Files that already exist are skipped, so a run can be interrupted and resumed,
and scheduled runs only fetch new months.
"""

from __future__ import annotations

import calendar
import logging
import shutil
import tempfile
import time
import zipfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .config import CountryConfig, Settings

LOGGER = logging.getLogger(__name__)


def month_starts(start: date, end: date) -> Iterator[date]:
    current = date(start.year, start.month, 1)
    while current <= end:
        yield current
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)


def month_end(month: date) -> date:
    return date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])


def raw_path(settings: Settings, country: CountryConfig, level_type: str, month: date) -> Path:
    return settings.path("raw_dir") / country.iso3 / f"{country.iso3}_eac4_{level_type}_{month:%Y-%m}.nc"


def needs_meteorology(settings: Settings, pollutants: list[str]) -> bool:
    catalogue = settings.variables["pollutants"]
    for code in pollutants:
        spec = catalogue[code]
        sources = spec.get("derived_from", [code])
        if any(catalogue[s].get("level_type") == "model" for s in sources):
            return True
    return False


def request_groups(settings: Settings, pollutants: list[str]) -> dict[str, list[str]]:
    """Map level type ('single' / 'model') -> ADS variable names to request."""
    catalogue = settings.variables["pollutants"]
    wanted: list[str] = []
    for code in pollutants:
        for source in catalogue[code].get("derived_from", [code]):
            if source not in wanted:
                wanted.append(source)

    groups: dict[str, list[str]] = {}
    for code in wanted:
        spec = catalogue[code]
        groups.setdefault(spec["level_type"], []).append(spec["request_name"])

    if needs_meteorology(settings, pollutants):
        for spec in settings.variables["meteorology"].values():
            groups.setdefault(spec["level_type"], []).append(spec["request_name"])
    return groups


def build_request(
    settings: Settings, country: CountryConfig, level_type: str, variables: list[str], month: date
) -> dict[str, Any]:
    cop = settings.copernicus
    request: dict[str, Any] = {
        "variable": variables,
        "date": [f"{month:%Y-%m-%d}/{month_end(month):%Y-%m-%d}"],
        "time": list(cop["times"]),
        "area": country.area,
        "data_format": "netcdf",
    }
    if level_type == "model":
        request["model_level"] = [str(cop.get("model_level", "60"))]
    return request


def read_api_key(settings: Settings) -> str:
    key = settings.copernicus.get("api_key") or ""
    if key:
        return key.strip()
    rc = Path.home() / ".cdsapirc"
    if rc.exists():
        data = yaml.safe_load(rc.read_text(encoding="utf-8")) or {}
        if data.get("key"):
            return str(data["key"]).strip()
    raise RuntimeError(
        "No Copernicus ADS API key. Set ADS_API_KEY (or add `key:` to ~/.cdsapirc). "
        "Get one at https://ads.atmosphere.copernicus.eu/how-to-api and accept the "
        "CAMS EAC4 licence on the dataset page."
    )


def make_client(settings: Settings):
    import cdsapi  # imported lazily so tests run without it

    cop = settings.copernicus
    return cdsapi.Client(
        url=cop["url"],
        key=read_api_key(settings),
        quiet=True,
        timeout=int(cop.get("timeout_seconds", 3600)),
    )


def _finalise(download: Path, target: Path) -> None:
    """ADS returns a ZIP when a request spans several files; merge to one NetCDF."""
    if zipfile.is_zipfile(download):
        import xarray as xr

        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(download) as archive:
                members = [m for m in archive.namelist() if m.lower().endswith(".nc")]
                archive.extractall(tmp, members)
            paths = [Path(tmp) / m for m in members]
            if len(paths) == 1:
                shutil.move(str(paths[0]), target)
            else:
                datasets = [xr.open_dataset(p) for p in paths]
                try:
                    merged = xr.merge(datasets, compat="override", join="outer")
                    merged.to_netcdf(target)
                finally:
                    for ds in datasets:
                        ds.close()
        download.unlink()
    else:
        shutil.move(str(download), target)


def download_month(
    settings: Settings,
    country: CountryConfig,
    month: date,
    client=None,
    overwrite: bool = False,
) -> list[Path]:
    """Download every level group for one country-month. Returns the file paths."""
    cop = settings.copernicus
    outputs = []
    for level_type, variables in request_groups(settings, country.pollutants).items():
        target = raw_path(settings, country, level_type, month)
        outputs.append(target)
        if target.exists() and not overwrite:
            LOGGER.info("%s %s %s: already downloaded", country.iso3, f"{month:%Y-%m}", level_type)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        request = build_request(settings, country, level_type, variables, month)
        client = client or make_client(settings)
        attempts = int(cop.get("retries", 3))
        for attempt in range(1, attempts + 1):
            partial = target.with_suffix(".part")
            try:
                LOGGER.info(
                    "%s %s %s: requesting %s (attempt %s/%s)",
                    country.iso3, f"{month:%Y-%m}", level_type, ", ".join(variables), attempt, attempts,
                )
                client.retrieve(cop["dataset"], request, str(partial))
                _finalise(partial, target)
                manifest = target.with_suffix(".nc.request.yml")
                manifest.write_text(
                    yaml.safe_dump(
                        {"dataset": cop["dataset"], "request": request, "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                break
            except Exception as exc:  # network / queue / API errors
                if partial.exists():
                    partial.unlink()
                if attempt == attempts:
                    raise RuntimeError(
                        f"{country.iso3} {month:%Y-%m} {level_type}: download failed after "
                        f"{attempts} attempts: {exc}"
                    ) from exc
                wait = int(cop.get("retry_wait_seconds", 60)) * attempt
                LOGGER.warning("Download failed (%s); retrying in %ss", exc, wait)
                time.sleep(wait)
    return outputs
