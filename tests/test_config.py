from datetime import date

import pytest

from gaia_pipeline.config import expand_env, load_settings, parse_date, select_countries


def test_expand_env_default_and_value(monkeypatch):
    monkeypatch.setenv("GAIA_TEST_VAR", "abc")
    monkeypatch.delenv("GAIA_MISSING", raising=False)
    data = {"a": "${GAIA_TEST_VAR}", "b": ["${GAIA_MISSING:-fallback}"], "c": 5}
    assert expand_env(data) == {"a": "abc", "b": ["fallback"], "c": 5}


def test_parse_date_forms():
    latest = date(2024, 12, 31)
    assert parse_date("2024-03", latest) == date(2024, 3, 1)
    assert parse_date("2024-03-15", latest) == date(2024, 3, 15)
    assert parse_date("latest", latest) == latest


def test_all_country_configs_are_valid():
    settings = load_settings()
    assert {"cameroon", "senegal", "malawi", "uganda", "ethiopia"} <= set(settings.countries)
    for country in settings.countries.values():
        north, west, south, east = country.area
        assert north > south and east > west
        assert len(country.iso2) == 2 and len(country.iso3) == 3
        # "no" must stay a string (YAML 1.1 would read it as False)
        assert all(isinstance(p, str) for p in country.pollutants)


def test_select_countries_by_alias():
    settings = load_settings()
    chosen = select_countries(settings, ["CM", "senegal", "UGA"], all_enabled=False)
    assert [c.key for c in chosen] == ["cameroon", "senegal", "uganda"]
    with pytest.raises(ValueError):
        select_countries(settings, ["atlantis"], all_enabled=False)
