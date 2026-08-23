from __future__ import annotations

import pytest

from wage_transmission.data.eurostat import jsonstat_to_frame


def test_jsonstat_decoder() -> None:
    payload = {
        "id": ["geo", "time"],
        "size": [2, 2],
        "dimension": {
            "geo": {"category": {"index": {"PT": 0, "ES": 1}}},
            "time": {"category": {"index": {"2020": 0, "2021": 1}}},
        },
        "value": {"0": 1.0, "1": 2.0, "2": 3.0, "3": 4.0},
    }
    frame = jsonstat_to_frame(payload)
    assert len(frame) == 4
    assert frame.loc[(frame["geo"] == "ES") & (frame["time"] == "2021"), "OBS_VALUE"].iloc[0] == 4.0


def test_employee_download_uses_employee_domestic_concept(monkeypatch) -> None:
    import pandas as pd

    import wage_transmission.data.eurostat as eurostat

    captured: dict[str, object] = {}

    def fake_fetch(dataset, *, filters, raw_path=None, timeout=60.0):
        captured["dataset"] = dataset
        captured["filters"] = dict(filters)
        return pd.DataFrame({"time": ["2020", "2021"], "OBS_VALUE": [4100.0, 4150.0]})

    monkeypatch.setattr(eurostat, "fetch_eurostat", fake_fetch)
    result = eurostat.download_employees(["PRT"], start_year=2020, end_year=2021)
    assert captured["dataset"] == "nama_10_pe"
    assert captured["filters"] == {
        "freq": "A",
        "unit": "THS_PER",
        "na_item": "SAL_DC",
        "geo": "PT",
        "sinceTimePeriod": 2020,
        "untilTimePeriod": 2021,
    }
    assert result["employees"].tolist() == [4100.0, 4150.0]


def test_hicp_download_uses_all_items_annual_average_index(monkeypatch) -> None:
    import pandas as pd

    import wage_transmission.data.eurostat as eurostat

    captured: dict[str, object] = {}

    def fake_fetch(dataset, *, filters, raw_path=None, timeout=60.0):
        captured["dataset"] = dataset
        captured["filters"] = dict(filters)
        return pd.DataFrame({"time": ["2020", "2021"], "OBS_VALUE": [100.0, 101.3]})

    monkeypatch.setattr(eurostat, "fetch_eurostat", fake_fetch)
    result = eurostat.download_hicp_index(["PRT"], start_year=2020, end_year=2021)
    assert captured["dataset"] == "prc_hicp_aind"
    assert captured["filters"] == {
        "freq": "A",
        "unit": "INX_A_AVG",
        "coicop": "CP00",
        "geo": "PT",
        "sinceTimePeriod": 2020,
        "untilTimePeriod": 2021,
    }
    assert result["consumer_price_index"].tolist() == [100.0, 101.3]


def test_decomposition_coverage_preserves_missing_source_information() -> None:
    import pandas as pd

    from wage_transmission.data.eurostat import summarise_decomposition_coverage

    nominal = pd.DataFrame(
        {
            "country": ["PRT", "PRT", "PRT"],
            "year": [2020, 2021, 2022],
            "nominal_gdp": [100.0, 102.0, 104.0],
        }
    )
    hicp = pd.DataFrame(
        {
            "country": ["PRT", "PRT"],
            "year": [2020, 2022],
            "consumer_price_index": [100.0, 104.0],
        }
    )
    coverage = summarise_decomposition_coverage(
        {"nominal_gdp": nominal, "consumer_price_index": hicp},
        countries=["PRT"],
        start_year=2020,
        end_year=2022,
    )
    hicp_row = coverage.loc[coverage["series"] == "consumer_price_index"].iloc[0]
    assert hicp_row["n_observations"] == 2
    assert hicp_row["first_year"] == 2020
    assert hicp_row["last_year"] == 2022
    assert hicp_row["coverage_ratio"] == pytest.approx(2 / 3)
