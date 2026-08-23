from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from wage_transmission.data.common import write_snapshot
from wage_transmission.data.oecd import PRODUCTIVITY_FLOW, WAGE_FLOW
from wage_transmission.data.offline import (
    build_decomposition_from_snapshots,
    build_oecd_panel_from_snapshots,
)


def test_offline_oecd_panel_filters_constant_price_wages(tmp_path: Path) -> None:
    wages = pd.DataFrame(
        {
            "REF_AREA": ["PRT", "PRT", "PRT", "PRT"],
            "TIME_PERIOD": [2023, 2024, 2023, 2024],
            "OBS_VALUE": [40_000, 41_000, 50_000, 52_000],
            "Price base": [
                "Constant prices",
                "Constant prices",
                "Current prices",
                "Current prices",
            ],
        }
    )
    productivity = pd.DataFrame(
        {
            "REF_AREA": ["PRT", "PRT"],
            "TIME_PERIOD": [2023, 2024],
            "OBS_VALUE": [80_000, 81_000],
            "MEASURE": ["GDPEMP", "GDPEMP"],
            "Measure": ["GDP per person employed", "GDP per person employed"],
        }
    )
    wage_path = tmp_path / "wages.csv"
    productivity_path = tmp_path / "worker.csv"
    wage_bytes = wages.to_csv(index=False).encode()
    prod_bytes = productivity.to_csv(index=False).encode()
    write_snapshot(
        wage_bytes,
        wage_path,
        {"source": "OECD", "url": "https://example.test/wages", "flow": WAGE_FLOW},
    )
    write_snapshot(
        prod_bytes,
        productivity_path,
        {
            "source": "OECD",
            "url": "https://example.test/productivity",
            "measure": "GDPEMP",
            "flow": PRODUCTIVITY_FLOW,
        },
    )

    panel = build_oecd_panel_from_snapshots(
        wage_path,
        productivity_path,
        measure="GDPEMP",
    )
    assert panel["real_wage"].tolist() == [40_000, 41_000]
    assert panel["productivity_per_worker"].tolist() == [80_000, 81_000]


def test_offline_oecd_rejects_wrong_productivity_measure_metadata(tmp_path: Path) -> None:
    wages = pd.DataFrame(
        {
            "REF_AREA": ["PRT", "PRT"],
            "TIME_PERIOD": [2023, 2024],
            "OBS_VALUE": [40_000, 41_000],
            "Price base": ["Constant prices", "Constant prices"],
        }
    )
    productivity = pd.DataFrame(
        {
            "REF_AREA": ["PRT", "PRT"],
            "TIME_PERIOD": [2023, 2024],
            "OBS_VALUE": [50.0, 51.0],
            "MEASURE": ["GDPHRS", "GDPHRS"],
        }
    )
    wage_path = tmp_path / "wages.csv"
    productivity_path = tmp_path / "productivity.csv"
    write_snapshot(
        wages.to_csv(index=False).encode(),
        wage_path,
        {"source": "OECD", "url": "https://example.test/wages", "flow": WAGE_FLOW},
    )
    write_snapshot(
        productivity.to_csv(index=False).encode(),
        productivity_path,
        {
            "source": "OECD",
            "url": "https://example.test/productivity",
            "flow": PRODUCTIVITY_FLOW,
            "measure": "GDPHRS",
        },
    )

    with pytest.raises(ValueError, match="metadata expected measure GDPEMP"):
        build_oecd_panel_from_snapshots(
            wage_path,
            productivity_path,
            measure="GDPEMP",
        )


def _jsonstat_payload(
    value: float,
    *,
    unit: str,
    item_dimension: str,
    item_code: str,
    year: str = "2024",
) -> bytes:
    dimensions = ["freq", "unit", item_dimension, "geo", "time"]
    payload = {
        "id": dimensions,
        "size": [1, 1, 1, 1, 1],
        "dimension": {
            "freq": {"category": {"index": {"A": 0}}},
            "unit": {"category": {"index": {unit: 0}}},
            item_dimension: {"category": {"index": {item_code: 0}}},
            "geo": {"category": {"index": {"PT": 0}}},
            "time": {"category": {"index": {year: 0}}},
        },
        "value": {"0": value},
    }
    return json.dumps(payload).encode()


def test_offline_eurostat_decomposition_rebuilds_common_row(tmp_path: Path) -> None:
    specs = {
        "nominal_gdp": (300.0, "nama_10_gdp", "CP_MEUR", "na_item", "B1GQ"),
        "real_gdp": (250.0, "nama_10_gdp", "CLV20_MEUR", "na_item", "B1GQ"),
        "employee_compensation": (150.0, "nama_10_gdp", "CP_MEUR", "na_item", "D1"),
        "employees": (5.0, "nama_10_pe", "THS_PER", "na_item", "SAL_DC"),
        "consumer_price_index": (120.0, "prc_hicp_aind", "INX_A_AVG", "coicop", "CP00"),
    }
    for name, (value, dataset, unit, item_dimension, item_code) in specs.items():
        path = tmp_path / f"eurostat_{name}_PRT_2024_2024.json"
        write_snapshot(
            _jsonstat_payload(
                value,
                unit=unit,
                item_dimension=item_dimension,
                item_code=item_code,
            ),
            path,
            {"source": "Eurostat", "url": f"https://example.test/{name}", "dataset": dataset},
        )

    panel = build_decomposition_from_snapshots(
        tmp_path,
        countries=["PRT"],
        start_year=2024,
        end_year=2024,
    )
    assert len(panel) == 1
    assert panel.loc[0, "country"] == "PRT"
    assert panel.loc[0, "employee_compensation"] == 150.0


def test_offline_eurostat_rejects_wrong_semantic_series(tmp_path: Path) -> None:
    path = tmp_path / "eurostat_nominal_gdp_PRT_2024_2024.json"
    write_snapshot(
        _jsonstat_payload(
            150.0,
            unit="CP_MEUR",
            item_dimension="na_item",
            item_code="D1",
        ),
        path,
        {"source": "Eurostat", "url": "https://example.test/wrong", "dataset": "nama_10_gdp"},
    )

    with pytest.raises(ValueError, match="semantic contract failed"):
        build_decomposition_from_snapshots(
            tmp_path,
            countries=["PRT"],
            start_year=2024,
            end_year=2024,
        )
