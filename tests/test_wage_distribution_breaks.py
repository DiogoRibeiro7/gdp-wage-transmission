"""Tests for Paper 2 wage-distribution breakpoint analysis."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tools.wage_distribution_breaks import endogenous_break, historical_break

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "results/exploratory_live/wage_distribution/portugal_wage_distribution_2002_2024.csv"


def _panel() -> pd.DataFrame:
    return pd.read_csv(PANEL)


def test_endogenous_break_dates_match_current_exploratory_panel() -> None:
    panel = _panel()
    d10d1 = endogenous_break(panel, "d10_d1_ratio", bootstrap_repetitions=19, seed=100)
    d10d5 = endogenous_break(panel, "d10_d5_ratio", bootstrap_repetitions=19, seed=200)
    meanmed = endogenous_break(panel, "mean_median_ratio", bootstrap_repetitions=19, seed=300)

    assert d10d1.selected_break_year == 2006
    assert d10d5.selected_break_year == 2013
    assert meanmed.selected_break_year == 2014
    assert d10d1.post_break_slope_pct_approx < -1.5


def test_forced_2008_break_shows_post_break_compression() -> None:
    result = historical_break(_panel(), "d10_d1_ratio", 2008)

    assert abs(result.pre_break_slope_pct_approx) < 0.5
    assert result.post_break_slope_pct_approx < -2.0
    assert result.slope_change_log_points < 0.0
    assert result.publication_eligible is False


def test_forced_2009_break_is_not_labelled_endogenous() -> None:
    result = historical_break(_panel(), "mean_median_ratio", 2009)

    assert result.break_year == 2009
    assert result.post_break_slope_pct_approx < 0.0
    assert result.publication_eligible is False
