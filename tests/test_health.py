import pandas as pd

from gaia_pipeline.health import parse_month_name, period_starts, to_number


def test_month_name_parsing_english_and_french():
    assert parse_month_name("January") == 1
    assert parse_month_name("sept") == 9
    assert parse_month_name("Décembre") == 12
    assert parse_month_name("7") == 7


def test_period_column_with_format():
    frame = pd.DataFrame({"PERIOD": ["January 2021", "September 2025"]})
    out = period_starts(frame, {"period": {"column": "PERIOD", "format": "%B %Y"}})
    assert list(out.dt.strftime("%Y-%m-%d")) == ["2021-01-01", "2025-09-01"]


def test_period_column_french_fallback():
    frame = pd.DataFrame({"PERIOD": ["Janvier 2021", "202403"]})
    out = period_starts(frame, {"period": {"column": "PERIOD"}})
    assert list(out.dt.strftime("%Y-%m-%d")) == ["2021-01-01", "2024-03-01"]


def test_month_and_year_columns():
    frame = pd.DataFrame({"Month": ["February", "december"], "Year": [2018, 2024]})
    out = period_starts(frame, {"period": {"month_column": "Month", "year_column": "Year"}})
    assert list(out.dt.strftime("%Y-%m-%d")) == ["2018-02-01", "2024-12-01"]


def test_to_number_blank_means_missing():
    out = to_number(pd.Series(["1,234", "", None, "-", "7"]))
    assert out.iloc[0] == 1234
    assert out.iloc[1:4].isna().all()
    assert out.iloc[4] == 7
