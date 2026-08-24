from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wage_transmission.models.break_inference import single_break_test

# Kept small so the suite stays fast; the statistic itself is unaffected by the count.
REPLICATIONS = 199


def _constant_elasticity_levels(beta: float = 0.7, seed: int = 7) -> pd.DataFrame:
    """A series with one stable transmission elasticity and no break."""
    rng = np.random.default_rng(seed)
    years = np.arange(1965, 2025)
    productivity_growth = rng.normal(0.018, 0.018, len(years))
    wage_growth = 0.002 + beta * productivity_growth + rng.normal(0, 0.008, len(years))
    return pd.DataFrame(
        {
            "year": years,
            "real_wage": 18000.0 * np.exp(np.cumsum(wage_growth)),
            "productivity": 25.0 * np.exp(np.cumsum(productivity_growth)),
        }
    )


def test_detects_the_planted_break(synthetic_levels: pd.DataFrame) -> None:
    """The fixture switches its elasticity from 0.85 to 0.45 in 1995."""
    result = single_break_test(synthetic_levels, bootstrap_replications=REPLICATIONS)

    assert result.p_value < 0.10
    assert abs(result.break_year - 1995) <= 5
    assert result.pre_break_elasticity > result.post_break_elasticity
    assert result.break_year_lower <= result.break_year <= result.break_year_upper
    assert result.interpretation.startswith("break_detected")


def test_stable_series_is_not_flagged() -> None:
    result = single_break_test(_constant_elasticity_levels(), bootstrap_replications=REPLICATIONS)

    assert result.p_value > 0.10
    assert result.interpretation == "no_break_detected"


def test_p_value_is_bounded_away_from_zero() -> None:
    """A bootstrap p-value can never be exactly zero, which would overstate the evidence."""
    result = single_break_test(_constant_elasticity_levels(), bootstrap_replications=REPLICATIONS)

    assert result.p_value >= 1.0 / (REPLICATIONS + 1)
    assert result.p_value <= 1.0


def test_is_deterministic_under_a_fixed_seed(synthetic_levels: pd.DataFrame) -> None:
    first = single_break_test(synthetic_levels, bootstrap_replications=REPLICATIONS, seed=42)
    second = single_break_test(synthetic_levels, bootstrap_replications=REPLICATIONS, seed=42)

    assert first == second


def test_trimming_changes_the_candidate_set(synthetic_levels: pd.DataFrame) -> None:
    narrow = single_break_test(synthetic_levels, trim=0.10, bootstrap_replications=REPLICATIONS)
    wide = single_break_test(synthetic_levels, trim=0.30, bootstrap_replications=REPLICATIONS)

    assert narrow.n_candidates > wide.n_candidates


def test_rejects_an_out_of_range_trim(synthetic_levels: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="trim must lie strictly"):
        single_break_test(synthetic_levels, trim=0.6)


def test_rejects_too_few_replications(synthetic_levels: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="at least 99"):
        single_break_test(synthetic_levels, bootstrap_replications=10)


def test_rejects_a_sample_that_is_too_short() -> None:
    short = _constant_elasticity_levels().head(14)
    with pytest.raises(ValueError, match="at least 16 growth observations"):
        single_break_test(short, bootstrap_replications=REPLICATIONS)
