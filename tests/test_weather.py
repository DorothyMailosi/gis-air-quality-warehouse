from datetime import date

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from gaia_pipeline.config import load_settings
from gaia_pipeline.weather import build_request, derive, relative_humidity


def era5_dataset(u: float, v: float) -> xr.Dataset:
    coords = {"time": pd.date_range("2024-01-01", periods=1), "latitude": [0.0], "longitude": [0.0]}
    dims = ("time", "latitude", "longitude")

    def arr(value):
        return xr.DataArray(np.full((1, 1, 1), value), coords, dims)

    return xr.Dataset({
        "t2m": arr(300.15), "d2m": arr(290.15), "u10": arr(u), "v10": arr(v), "tp": arr(0.0005),
    })


def test_units_and_derivations():
    out = derive(era5_dataset(u=0.0, v=-5.0), ["t2m", "rh", "wspd", "wdir", "tp"])
    assert float(out["t2m"]) == pytest.approx(27.0)
    assert float(out["wspd"]) == pytest.approx(5.0)
    # v < 0 means air moving south, i.e. a northerly wind: direction 0/360°
    assert float(out["wdir"]) % 360 == pytest.approx(0.0)
    assert float(out["tp"]) == pytest.approx(12.0)  # 0.5 mm/h * 24
    assert 50 < float(out["rh"]) < 60


def test_westerly_wind_direction():
    out = derive(era5_dataset(u=3.0, v=0.0), ["wdir"])
    assert float(out["wdir"]) == pytest.approx(270.0)


def test_relative_humidity_saturation():
    t = xr.DataArray([20.0])
    assert float(relative_humidity(t, t)) == pytest.approx(100.0)


def test_era5_request_whole_month():
    settings = load_settings()
    country = settings.countries["malawi"]
    request = build_request(settings, country, date(2024, 2, 1))
    assert request["day"][-1] == "29"
    assert "2m_dewpoint_temperature" in request["variable"]
    assert request["daily_statistic"] == "daily_mean"
