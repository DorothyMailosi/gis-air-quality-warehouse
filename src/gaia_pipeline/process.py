"""Convert downloaded CAMS NetCDF into standardised long-format Parquet.

Output: data/processed/<ISO3>/<ISO3>_eac4_<YYYY-MM>.parquet with columns

    obs_time (UTC) | latitude | longitude | variable_code | value_ugm3

Units are converted to µg/m3 from each variable's NetCDF `units` attribute,
so a wrong manual factor cannot slip in:

    kg m**-3   -> * 1e9
    kg kg**-1  -> * rho * 1e9, rho = sp / (Rd * t2m)   (air density, kg/m3)
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr

from .config import CountryConfig, Settings
from .download import raw_path

LOGGER = logging.getLogger(__name__)

RD = 287.05            # specific gas constant for dry air, J kg-1 K-1
STANDARD_RHO = 1.1839  # kg m-3 at 25 °C and 1013.25 hPa, used only as a fallback


def processed_path(settings: Settings, country: CountryConfig, month: date) -> Path:
    return settings.path("processed_dir") / country.iso3 / f"{country.iso3}_eac4_{month:%Y-%m}.parquet"


def _normalise(ds: xr.Dataset) -> xr.Dataset:
    """Standard coordinate names (time, latitude, longitude) and no singleton dims."""
    rename = {}
    if "time" not in ds.coords:
        for candidate in ("valid_time", "date", "datetime"):
            if candidate in ds.dims or candidate in ds.coords:
                rename[candidate] = "time"
                break
    if "lat" in ds.coords:
        rename["lat"] = "latitude"
    if "lon" in ds.coords:
        rename["lon"] = "longitude"
    ds = ds.rename(rename)
    for dim in list(ds.dims):
        if dim not in ("time", "latitude", "longitude") and ds.sizes[dim] == 1:
            ds = ds.squeeze(dim, drop=True)
    for extra in ("model_level", "level", "expver", "number", "step"):
        if extra in ds.coords and extra not in ds.dims:
            ds = ds.drop_vars(extra)
    if float(ds["longitude"].max()) > 180:
        ds = ds.assign_coords(longitude=((ds["longitude"] + 180) % 360) - 180).sortby("longitude")
    return ds


def find_variable(ds: xr.Dataset, names: list[str]) -> str | None:
    lowered = {name.lower(): name for name in ds.data_vars}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _units(da: xr.DataArray) -> str:
    return str(da.attrs.get("units", da.attrs.get("GRIB_units", ""))).replace(" ", "").lower()


def to_ugm3(da: xr.DataArray, air_density: xr.DataArray | None) -> tuple[xr.DataArray, str]:
    units = _units(da)
    if units in ("kgm**-3", "kgm-3", "kg/m3", "kgm^-3"):
        return da * 1e9, "kg m-3 * 1e9"
    if units in ("kgkg**-1", "kgkg-1", "kg/kg", "kgkg^-1", "1"):
        if air_density is None:
            LOGGER.warning("No t2m/sp in the download: using standard air density %.4f", STANDARD_RHO)
            return da * STANDARD_RHO * 1e9, "kg kg-1 * standard rho * 1e9"
        return da * air_density * 1e9, "kg kg-1 * rho(sp, t2m) * 1e9"
    if units in ("µgm**-3", "ugm**-3", "ug/m3", "µg/m3"):
        return da, "already ug m-3"
    raise ValueError(f"Variable {da.name!r} has unsupported units {units!r}")


def open_month(settings: Settings, country: CountryConfig, month: date) -> xr.Dataset:
    datasets = []
    for level_type in ("single", "model"):
        path = raw_path(settings, country, level_type, month)
        if path.exists():
            datasets.append(_normalise(xr.load_dataset(path)))
    if not datasets:
        raise FileNotFoundError(
            f"No downloaded NetCDF for {country.iso3} {month:%Y-%m} in {raw_path(settings, country, 'single', month).parent}"
        )
    return xr.merge(datasets, compat="override", join="inner")


def standardise(ds: xr.Dataset, settings: Settings, pollutants: list[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    catalogue = settings.variables["pollutants"]
    met = settings.variables["meteorology"]

    air_density = None
    sp_name = find_variable(ds, met["sp"]["netcdf_names"])
    t2m_name = find_variable(ds, met["t2m"]["netcdf_names"])
    if sp_name and t2m_name:
        air_density = ds[sp_name] / (RD * ds[t2m_name])

    converted: dict[str, xr.DataArray] = {}
    report: dict[str, Any] = {"conversions": {}, "missing": []}

    def get(code: str) -> xr.DataArray | None:
        if code in converted:
            return converted[code]
        name = find_variable(ds, catalogue[code]["netcdf_names"])
        if name is None:
            return None
        da, method = to_ugm3(ds[name], air_density)
        converted[code] = da
        report["conversions"][code] = method
        return da

    frames = []
    for code in pollutants:
        spec = catalogue[code]
        if "derived_from" in spec:
            parts = [get(p) for p in spec["derived_from"]]
            if any(p is None for p in parts):
                report["missing"].append(code)
                continue
            da = sum(parts[1:], parts[0])
            report["conversions"][code] = "sum of " + " + ".join(spec["derived_from"])
        else:
            da = get(code)
            if da is None:
                report["missing"].append(code)
                continue
        frame = da.rename("value_ugm3").to_dataframe().reset_index()
        frame = frame[["time", "latitude", "longitude", "value_ugm3"]]
        frame["variable_code"] = code
        frames.append(frame)

    if report["missing"]:
        LOGGER.warning("Not found in NetCDF: %s (variables present: %s)", report["missing"], list(ds.data_vars))
    if not frames:
        raise ValueError(f"None of {pollutants} found in NetCDF variables {list(ds.data_vars)}")

    df = pd.concat(frames, ignore_index=True).rename(columns={"time": "obs_time"})
    df["obs_time"] = pd.to_datetime(df["obs_time"], utc=True)
    df["latitude"] = df["latitude"].astype(float).round(4)
    df["longitude"] = df["longitude"].astype(float).round(4)
    df["value_ugm3"] = df["value_ugm3"].astype(float)
    return df, report


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    initial = len(df)
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["obs_time", "latitude", "longitude", "value_ugm3"])
    missing = initial - len(df)
    negative = int((df["value_ugm3"] < 0).sum())
    # Tiny negative values are numerical noise in the reanalysis; clip at zero.
    df.loc[df["value_ugm3"] < 0, "value_ugm3"] = 0.0
    before = len(df)
    df = df.drop_duplicates(["obs_time", "latitude", "longitude", "variable_code"])
    stats = (
        df.groupby("variable_code")["value_ugm3"]
        .agg(["count", "min", "mean", "max"])
        .round(3)
        .to_dict(orient="index")
    )
    return df.reset_index(drop=True), {
        "initial_rows": initial,
        "dropped_missing": missing,
        "clipped_negative": negative,
        "dropped_duplicates": before - len(df),
        "final_rows": len(df),
        "grid_cells": int(df[["latitude", "longitude"]].drop_duplicates().shape[0]),
        "start": df["obs_time"].min().isoformat() if len(df) else None,
        "end": df["obs_time"].max().isoformat() if len(df) else None,
        "by_variable": stats,
    }


def process_month(settings: Settings, country: CountryConfig, month: date, overwrite: bool = False) -> tuple[Path, dict[str, Any]]:
    target = processed_path(settings, country, month)
    if target.exists() and not overwrite:
        LOGGER.info("%s %s: already processed", country.iso3, f"{month:%Y-%m}")
        return target, {"skipped": True}
    ds = open_month(settings, country, month)
    try:
        df, conversion = standardise(ds, settings, country.pollutants)
    finally:
        ds.close()
    df, report = validate(df)
    report.update(conversion)
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(target, index=False)
    LOGGER.info(
        "%s %s: %s rows, %s grid cells -> %s",
        country.iso3, f"{month:%Y-%m}", report["final_rows"], report["grid_cells"], target.name,
    )
    return target, report
