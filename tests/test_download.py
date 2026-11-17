from datetime import date

from gaia_pipeline.config import load_settings
from gaia_pipeline.download import build_request, month_end, month_starts, request_groups


def test_month_starts_spans_year_boundary():
    months = list(month_starts(date(2023, 11, 15), date(2024, 2, 1)))
    assert months == [date(2023, 11, 1), date(2023, 12, 1), date(2024, 1, 1), date(2024, 2, 1)]
    assert month_end(date(2024, 2, 1)) == date(2024, 2, 29)


def test_pm_only_needs_single_level_without_meteorology():
    settings = load_settings()
    assert request_groups(settings, ["pm25"]) == {"single": ["particulate_matter_2.5um"]}


def test_gases_add_model_level_and_density_variables():
    settings = load_settings()
    groups = request_groups(settings, ["pm25", "nox"])
    assert set(groups["model"]) == {"nitrogen_monoxide", "nitrogen_dioxide"}
    assert {"2m_temperature", "surface_pressure"} <= set(groups["single"])


def test_build_request_model_level():
    settings = load_settings()
    country = settings.countries["cameroon"]
    request = build_request(settings, country, "model", ["ozone"], date(2024, 2, 1))
    assert request["date"] == ["2024-02-01/2024-02-29"]
    assert request["model_level"] == ["60"]
    assert request["area"] == country.area
