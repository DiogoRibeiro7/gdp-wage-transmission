"""Tests for the exploratory Quadros de Pessoal wage-distribution reporting layer."""

from __future__ import annotations

import pandas as pd
import pytest
from tools.exploratory_wage_distribution import (
    build_distribution_panel,
    decile_growth_table,
    stitch_official_series,
    summarise_distribution,
)


def _source(start: int, end: int) -> pd.DataFrame:
    rows = []
    for year in range(start, end + 1):
        base = 100.0 + 2.0 * (year - 2014)
        deciles = [base * (0.5 + 0.1 * i) for i in range(10)]
        rows.append(
            {
                "year": year,
                "employees_tco": 1000 + year,
                "mean_gain_eur": sum(deciles) / 10.0,
                "median_gain_eur": base * 0.95,
                **{f"d{i + 1}_mean_gain_eur": value for i, value in enumerate(deciles)},
            }
        )
    return pd.DataFrame(rows)


def _hicp() -> pd.DataFrame:
    rows = []
    for year in range(2012, 2017):
        for month in range(1, 13):
            rows.append(
                {
                    "date": f"{year}-{month:02d}-01",
                    "hicp_index_2025_100": 80.0 + (year - 2012) + month / 100.0,
                }
            )
    return pd.DataFrame(rows)


def test_stitch_requires_exact_bridge_match() -> None:
    old = _source(2012, 2014)
    current = _source(2014, 2016)
    combined = stitch_official_series(old, current)
    assert combined["year"].tolist() == [2012, 2013, 2014, 2015, 2016]

    current.loc[current["year"] == 2014, "median_gain_eur"] += 1.0
    with pytest.raises(ValueError, match="Official source mismatch"):
        stitch_official_series(old, current)


def test_build_panel_uses_october_hicp_and_is_non_publication() -> None:
    panel = build_distribution_panel(_source(2012, 2014), _source(2014, 2016), _hicp())
    first = panel.iloc[0]
    expected = float(first["mean_gain_eur"]) * 100.0 / 80.10
    assert float(first["real_mean_gain_2025_eur"]) == pytest.approx(expected)
    assert not bool(panel["publication_eligible"].any())
    assert panel["population_definition"].nunique() == 1


def test_summary_tracks_inequality_ratio_compression() -> None:
    old = _source(2012, 2014)
    current = _source(2014, 2016)
    # Compress the top and raise the bottom in the post-bridge years, preserving bridge equality.
    for year in (2015, 2016):
        mask = current["year"] == year
        current.loc[mask, "d1_mean_gain_eur"] *= 1.2
        current.loc[mask, "d10_mean_gain_eur"] *= 0.9
        current.loc[mask, "mean_gain_eur"] = current.loc[
            mask, [f"d{i}_mean_gain_eur" for i in range(1, 11)]
        ].mean(axis=1)
    panel = build_distribution_panel(old, current, _hicp())
    summary = summarise_distribution(panel)
    assert summary.d10_d1_ratio_end < summary.d10_d1_ratio_start
    assert summary.publication_eligible is False
    assert summary.maximum_decile_mean_reconstruction_error_eur < 2.0


def test_growth_table_contains_mean_median_and_all_deciles() -> None:
    panel = build_distribution_panel(_source(2012, 2014), _source(2014, 2016), _hicp())
    growth = decile_growth_table(panel)
    assert growth["measure"].tolist() == ["mean", "median", *[f"d{i}" for i in range(1, 11)]]
    assert (growth["publication_eligible"] == False).all()  # noqa: E712


def test_decile_reconstruction_guard_rejects_transcription_error() -> None:
    old = _source(2012, 2014)
    old.loc[0, "d10_mean_gain_eur"] *= 3.0
    with pytest.raises(ValueError, match="fail to reconstruct"):
        stitch_official_series(old, _source(2014, 2016))


def test_productivity_endpoint_comparison_uses_common_years_only() -> None:
    from tools.exploratory_wage_distribution import compare_productivity_endpoints

    panel = build_distribution_panel(_source(2012, 2014), _source(2014, 2016), _hicp())
    productivity = pd.DataFrame(
        {
            "year": [2013, 2014, 2015],
            "productivity_per_worker": [100.0, 105.0, 110.0],
        }
    )
    comparison = compare_productivity_endpoints(panel, productivity)
    assert comparison.start_year == 2013
    assert comparison.end_year == 2015
    assert comparison.productivity_per_worker_growth_pct == pytest.approx(10.0)
    assert comparison.publication_eligible is False
