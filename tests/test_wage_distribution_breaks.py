"""Tests for the wage-distribution breakpoint analysis.

Two layers. The synthetic tests run everywhere and pin the estimator's behaviour against a
planted kink. The regression tests below them pin exact break years against the real exploratory
panel, which lives under `results/` and is deliberately not tracked; they skip on a clean
checkout rather than failing, because their input is a working artefact rather than repository
content.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from tools.wage_distribution_breaks import METRICS, endogenous_break, historical_break

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "results/exploratory_live/wage_distribution/portugal_wage_distribution_2002_2024.csv"

requires_exploratory_panel = pytest.mark.skipif(
    not PANEL.is_file(),
    reason="The exploratory wage-distribution panel is untracked and absent from this checkout.",
)


def _panel() -> pd.DataFrame:
    return pd.read_csv(PANEL)


def _synthetic_panel(
    *,
    break_year: int = 2012,
    pre_slope: float = 0.004,
    post_slope: float = -0.02,
    start: int = 2002,
    end: int = 2024,
) -> pd.DataFrame:
    """An annual ratio panel with one continuous kink at a known year."""
    years = np.arange(start, end + 1)
    since_break = np.maximum(years - break_year, 0)
    log_ratio = pre_slope * (years - start) + (post_slope - pre_slope) * since_break
    frame = pd.DataFrame({"year": years})
    for index, metric in enumerate(METRICS):
        # A small per-metric offset keeps the columns distinguishable without moving the kink.
        frame[metric] = np.exp(log_ratio + 0.01 * index) * (2.0 + index)
    return frame


def test_endogenous_break_recovers_a_planted_kink() -> None:
    panel = _synthetic_panel(break_year=2012)

    result = endogenous_break(panel, "d10_d1_ratio", bootstrap_repetitions=19, seed=1)

    assert abs(result.selected_break_year - 2012) <= 1
    assert result.post_break_slope_pct_approx < result.pre_break_slope_pct_approx
    assert result.publication_eligible is False


def test_endogenous_break_rejects_an_unknown_metric() -> None:
    with pytest.raises(ValueError, match="Unknown metric"):
        endogenous_break(_synthetic_panel(), "not_a_metric", bootstrap_repetitions=19)


def test_historical_break_reports_the_forced_year() -> None:
    panel = _synthetic_panel(break_year=2012)

    result = historical_break(panel, "d10_d1_ratio", 2009)

    assert result.break_year == 2009
    # A forced date is a hypothesis, never an endogenous finding.
    assert result.publication_eligible is False


def test_historical_break_rejects_a_year_outside_the_sample() -> None:
    with pytest.raises(ValueError, match="outside the sample"):
        historical_break(_synthetic_panel(), "d10_d1_ratio", 1990)


@requires_exploratory_panel
def test_endogenous_break_dates_match_current_exploratory_panel() -> None:
    panel = _panel()
    d10d1 = endogenous_break(panel, "d10_d1_ratio", bootstrap_repetitions=19, seed=100)
    d10d5 = endogenous_break(panel, "d10_d5_ratio", bootstrap_repetitions=19, seed=200)
    meanmed = endogenous_break(panel, "mean_median_ratio", bootstrap_repetitions=19, seed=300)

    assert d10d1.selected_break_year == 2006
    assert d10d5.selected_break_year == 2013
    assert meanmed.selected_break_year == 2014
    assert d10d1.post_break_slope_pct_approx < -1.5


@requires_exploratory_panel
def test_forced_2008_break_shows_post_break_compression() -> None:
    result = historical_break(_panel(), "d10_d1_ratio", 2008)

    assert abs(result.pre_break_slope_pct_approx) < 0.5
    assert result.post_break_slope_pct_approx < -2.0
    assert result.slope_change_log_points < 0.0
    assert result.publication_eligible is False


@requires_exploratory_panel
def test_forced_2009_break_is_not_labelled_endogenous() -> None:
    result = historical_break(_panel(), "mean_median_ratio", 2009)

    assert result.break_year == 2009
    assert result.post_break_slope_pct_approx < 0.0
    assert result.publication_eligible is False
