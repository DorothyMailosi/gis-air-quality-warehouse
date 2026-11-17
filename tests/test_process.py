import numpy as np
import pandas as pd
import pytest
import xarray as xr

from gaia_pipeline.config import load_settings
from gaia_pipeline.process import RD, _normalise, standardise, validate


def make_dataset(with_met: bool = True) -> xr.Dataset:
    times = pd.date_range("2024-01-01", periods=2, freq="3h")
    lat = [5.25, 4.5]
    lon = [9.0, 9.75]
    shape = (2, 2, 2)
    coords = {"valid_time": times, "latitude": lat, "longitude": lon}
    dims = ("valid_time", "latitude", "longitude")
    data = {
        "pm2p5": xr.DataArray(np.full(shape, 20e-9), coords, dims, attrs={"units": "kg m**-3"}),
        "no2": xr.DataArray(np.full(shape, 10e-9), coords, dims, attrs={"units": "kg kg**-1"}),
        "no": xr.DataArray(np.full(shape, 2e-9), coords, dims, attrs={"units": "kg kg**-1"}),
    }
    if with_met:
        data["t2m"] = xr.DataArray(np.full(shape, 300.0), coords, dims, attrs={"units": "K"})
        data["sp"] = xr.DataArray(np.full(shape, 100000.0), coords, dims, attrs={"units": "Pa"})
    return _normalise(xr.Dataset(data))


def test_aerosol_and_gas_conversion():
    settings = load_settings()
    df, report = standardise(make_dataset(), settings, ["pm25", "no2", "nox"])
    rho = 100000.0 / (RD * 300.0)
    by_var = df.groupby("variable_code")["value_ugm3"].first()
    assert by_var["pm25"] == pytest.approx(20.0)
    assert by_var["no2"] == pytest.approx(10.0 * rho)
    assert by_var["nox"] == pytest.approx(12.0 * rho)
    assert report["missing"] == []
    assert str(df["obs_time"].dt.tz) == "UTC"


def test_gas_without_meteorology_uses_standard_density():
    settings = load_settings()
    df, report = standardise(make_dataset(with_met=False), settings, ["no2"])
    assert df["value_ugm3"].iloc[0] == pytest.approx(10.0 * 1.1839)
    assert "standard" in report["conversions"]["no2"]


def test_missing_variable_is_reported_not_fatal():
    settings = load_settings()
    df, report = standardise(make_dataset(), settings, ["pm25", "so2"])
    assert report["missing"] == ["so2"]
    assert set(df["variable_code"]) == {"pm25"}


def test_validate_clips_negative_and_drops_duplicates():
    df = pd.DataFrame({
        "obs_time": pd.to_datetime(["2024-01-01"] * 3, utc=True),
        "latitude": [1.0, 1.0, 2.0],
        "longitude": [1.0, 1.0, 2.0],
        "variable_code": ["pm25"] * 3,
        "value_ugm3": [5.0, 5.0, -0.001],
    })
    out, report = validate(df)
    assert len(out) == 2
    assert report["clipped_negative"] == 1
    assert out["value_ugm3"].min() == 0.0


def test_longitudes_0_360_are_wrapped():
    ds = xr.Dataset(
        {"pm2p5": (("time", "latitude", "longitude"), np.zeros((1, 1, 2)), {"units": "kg m**-3"})},
        coords={"time": pd.date_range("2024-01-01", periods=1), "latitude": [0.0], "longitude": [350.0, 10.0]},
    )
    out = _normalise(ds)
    assert sorted(out["longitude"].values.tolist()) == [-10.0, 10.0]
