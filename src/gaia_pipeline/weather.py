"""ERA5 daily weather: download from the Climate Data Store and convert.

Dataset: derived-era5-single-levels-daily-statistics (daily means, 0.25°).

    data/raw/<ISO3>/<ISO3>_era5_daily_<YYYY-MM>.nc
    data/processed/<ISO3>/<ISO3>_era5_<YYYY-MM>.parquet   (long format, display units)

Derived variables:
    t2m  °C       = 2 m temperature - 273.15
    rh   %        = from daily-mean temperature and dew point (Magnus formula)
    wspd m/s      = |(u10, v10)|  (speed of the daily-mean wind vector)
    wdir deg      = direction the wind blows FROM (meteorological convention)
    tp   mm/day   = daily mean of hourly precipitation (m) * 24 * 1000
"""

from __future__ import annotations

import calendar
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
import yaml

from .config import CountryConfig, Settings
from .download import _finalise, month_starts
from .process import _normalise, find_variable

LOGGER = logging.getLogger(__name__)

NETCDF_NAMES = {
    "2m_temperature": ["t2m"],
    "2m_dewpoint_temperature": ["d2m"],
    "10m_u_component_of_wind": ["u10"],
    "10m_v_component_of_wind": ["v10"],
    "total_precipitation": ["tp"],
}


def raw_path(settings: Settings, country: CountryConfig, month: date) -> Path:
    return settings.path("raw_dir") / country.iso3 / f"{country.iso3}_era5_daily_{month:%Y-%m}.nc"


def processed_path(settings: Settings, country: CountryConfig, month: date) -> Path:
    return settings.path("processed_dir") / country.iso3 / f"{country.iso3}_era5_{month:%Y-%m}.parquet"


def weather_codes(settings: Settings, country: CountryConfig) -> list[str]:
    catalogue = settings.variables["weather"]
    return [str(v) for v in country.weather.get("variables", list(catalogue))]


def request_variables(settings: Settings, codes: list[str]) -> list[str]:
    names: list[str] = []
    for code in codes:
        for name in settings.variables["weather"][code]["request_names"]:
            if name not in names:
                names.append(name)
    return names


def build_request(settings: Settings, country: CountryConfig, month: date) -> dict[str, Any]:
    cfg = settings.raw["era5"]
    # plan_months only yields complete months, so the whole month is requested.
    days = calendar.monthrange(month.year, month.month)[1]
    return {
        "product_type": "reanalysis",
        "variable": request_variables(settings, weather_codes(settings, country)),
        "year": f"{month.year}",
        "month": [f"{month.month:02d}"],
        "day": [f"{d:02d}" for d in range(1, days + 1)],
        "daily_statistic": cfg.get("daily_statistic", "daily_mean"),
        "time_zone": cfg.get("time_zone", "utc+00:00"),
        "frequency": cfg.get("frequency", "1_hourly"),
        "area": country.area,
    }


def make_client(settings: Settings):
    import cdsapi

    from .download import read_api_key

    cfg = settings.raw["era5"]
    key = cfg.get("api_key") or read_api_key(settings)
    return cdsapi.Client(url=cfg["url"], key=key, quiet=True, timeout=int(cfg.get("timeout_seconds", 3600)))


def download_month(settings: Settings, country: CountryConfig, month: date, client=None, overwrite: bool = False) -> Path:
    target = raw_path(settings, country, month)
    if target.exists() and not overwrite:
        LOGGER.info("%s %s era5: already downloaded", country.iso3, f"{month:%Y-%m}")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    cfg = settings.raw["era5"]
    request = build_request(settings, country, month)
    client = client or make_client(settings)
    attempts = int(cfg.get("retries", 3))
    for attempt in range(1, attempts + 1):
        partial = target.with_suffix(".part")
        try:
            LOGGER.info("%s %s era5: requesting %s (attempt %s/%s)", country.iso3, f"{month:%Y-%m}",
                        ", ".join(request["variable"]), attempt, attempts)
            client.retrieve(cfg["dataset"], request, str(partial))
            _finalise(partial, target)
            target.with_suffix(".nc.request.yml").write_text(
                yaml.safe_dump({"dataset": cfg["dataset"], "request": request}, sort_keys=False), encoding="utf-8"
            )
            return target
        except Exception as exc:
            if partial.exists():
                partial.unlink()
            if attempt == attempts:
                raise RuntimeError(f"{country.iso3} {month:%Y-%m} era5: download failed: {exc}") from exc
            wait = int(cfg.get("retry_wait_seconds", 60)) * attempt
            LOGGER.warning("ERA5 download failed (%s); retrying in %ss", exc, wait)
            time.sleep(wait)
    return target


def relative_humidity(t_c: xr.DataArray, td_c: xr.DataArray) -> xr.DataArray:
    """Magnus formula (Alduchov & Eskridge 1996 coefficients), result clipped to 0-100 %."""
    a, b = 17.625, 243.04
    rh = 100 * np.exp(a * td_c / (b + td_c)) / np.exp(a * t_c / (b + t_c))
    return rh.clip(0, 100)


def derive(ds: xr.Dataset, codes: list[str]) -> dict[str, xr.DataArray]:
    def get(request_name: str) -> xr.DataArray | None:
        name = find_variable(ds, NETCDF_NAMES[request_name])
        return ds[name] if name else None

    t2m, d2m = get("2m_temperature"), get("2m_dewpoint_temperature")
    u10, v10 = get("10m_u_component_of_wind"), get("10m_v_component_of_wind")
    tp = get("total_precipitation")

    out: dict[str, xr.DataArray] = {}
    if "t2m" in codes and t2m is not None:
        out["t2m"] = t2m - 273.15
    if "rh" in codes and t2m is not None and d2m is not None:
        out["rh"] = relative_humidity(t2m - 273.15, d2m - 273.15)
    if u10 is not None and v10 is not None:
        if "wspd" in codes:
            out["wspd"] = np.hypot(u10, v10)
        if "wdir" in codes:
            out["wdir"] = (270 - np.degrees(np.arctan2(v10, u10))) % 360
    if "tp" in codes and tp is not None:
        out["tp"] = (tp * 24 * 1000).clip(min=0)
    return out


def process_month(settings: Settings, country: CountryConfig, month: date, overwrite: bool = False) -> tuple[Path, dict[str, Any]]:
    target = processed_path(settings, country, month)
    if target.exists() and not overwrite:
        LOGGER.info("%s %s era5: already processed", country.iso3, f"{month:%Y-%m}")
        return target, {"skipped": True}
    source = raw_path(settings, country, month)
    if not source.exists():
        raise FileNotFoundError(f"No ERA5 download for {country.iso3} {month:%Y-%m}: {source}")
    ds = _normalise(xr.load_dataset(source))
    codes = weather_codes(settings, country)
    derived = derive(ds, codes)
    missing = [c for c in codes if c not in derived]
    if missing:
        LOGGER.warning("ERA5 variables missing for %s: %s (present: %s)", country.iso3, missing, list(ds.data_vars))
    frames = []
    for code, da in derived.items():
        frame = da.rename("value").to_dataframe().reset_index()[["time", "latitude", "longitude", "value"]]
        frame["variable_code"] = code
        frames.append(frame)
    if not frames:
        raise ValueError(f"No usable ERA5 variables in {source.name}: {list(ds.data_vars)}")
    df = pd.concat(frames, ignore_index=True).rename(columns={"time": "obs_time"})
    df["obs_time"] = pd.to_datetime(df["obs_time"], utc=True)
    df["latitude"] = df["latitude"].astype(float).round(4)
    df["longitude"] = df["longitude"].astype(float).round(4)
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["value"])
    df = df.drop_duplicates(["obs_time", "latitude", "longitude", "variable_code"]).reset_index(drop=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(target, index=False)
    report = {
        "final_rows": len(df),
        "grid_cells": int(df[["latitude", "longitude"]].drop_duplicates().shape[0]),
        "missing": missing,
        "by_variable": df.groupby("variable_code")["value"].agg(["min", "mean", "max"]).round(2).to_dict(orient="index"),
    }
    LOGGER.info("%s %s era5: %s rows, %s grid cells -> %s", country.iso3, f"{month:%Y-%m}",
                report["final_rows"], report["grid_cells"], target.name)
    return target, report


def plan_months(settings: Settings, country: CountryConfig, start: date | None, end: date | None) -> list[date]:
    first = start or _parse(country.weather.get("start")) or country.start
    last = min(end or settings.era5_available_until, settings.era5_available_until)
    return list(month_starts(first, last)) if first <= last else []


def _parse(value) -> date | None:
    if value is None:
        return None
    from .config import parse_date

    return parse_date(value, date.today())
