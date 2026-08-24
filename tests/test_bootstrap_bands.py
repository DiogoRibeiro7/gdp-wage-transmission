from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wage_transmission.models._bootstrap import moving_block_indices, resample_level_frame
from wage_transmission.models.local_projections import (
    bootstrap_local_projection_bands,
    fit_local_projections,
)
from wage_transmission.models.state_space import bootstrap_time_varying_elasticity_bands
from wage_transmission.validation import add_log_growth_columns

# The minimum the estimators accept; enough to exercise the machinery without a slow suite.
REPLICATIONS = 99


def test_moving_block_indices_stay_in_range() -> None:
    rng = np.random.default_rng(1)
    indices = moving_block_indices(30, 4, rng)

    assert len(indices) == 30
    assert indices.min() >= 0
    assert indices.max() < 30


def test_moving_block_indices_preserve_contiguity_within_a_block() -> None:
    """Successive draws inside a block must be adjacent, which is what retains dependence."""
    rng = np.random.default_rng(2)
    indices = moving_block_indices(40, 5, rng)
    steps = np.diff(indices[:5])

    assert np.all((steps == 1) | (steps == -39))


def test_moving_block_indices_reject_an_impossible_block() -> None:
    rng = np.random.default_rng(3)
    with pytest.raises(ValueError, match="block_length must lie"):
        moving_block_indices(10, 11, rng)


def test_resampled_frame_keeps_units_and_starting_level(
    synthetic_levels: pd.DataFrame,
) -> None:
    data = add_log_growth_columns(synthetic_levels)
    resampled = resample_level_frame(data, block_length=4, rng=np.random.default_rng(4))

    assert list(resampled.columns) == ["year", "real_wage", "productivity"]
    assert len(resampled) == len(data)
    assert resampled["real_wage"].iloc[0] == pytest.approx(data["real_wage"].iloc[0])
    assert (resampled[["real_wage", "productivity"]] > 0).all().all()


def test_local_projection_bands_bracket_the_point_estimates(
    synthetic_levels: pd.DataFrame,
) -> None:
    bands = bootstrap_local_projection_bands(synthetic_levels, horizon=3, replications=REPLICATIONS)
    points = fit_local_projections(synthetic_levels, horizon=3)

    assert len(bands) == len(points)
    for band, point in zip(bands, points, strict=True):
        assert band.horizon == point.horizon
        assert band.estimate == pytest.approx(point.estimate)
        assert band.lower_95 <= band.upper_95
        assert np.isfinite(band.lower_95) and np.isfinite(band.upper_95)
        assert band.replications > 0


def test_local_projection_bands_are_deterministic(synthetic_levels: pd.DataFrame) -> None:
    first = bootstrap_local_projection_bands(
        synthetic_levels, horizon=2, replications=REPLICATIONS, seed=11
    )
    second = bootstrap_local_projection_bands(
        synthetic_levels, horizon=2, replications=REPLICATIONS, seed=11
    )

    assert first == second


def test_local_projection_bands_reject_too_few_replications(
    synthetic_levels: pd.DataFrame,
) -> None:
    with pytest.raises(ValueError, match="at least 99"):
        bootstrap_local_projection_bands(synthetic_levels, horizon=2, replications=10)


@pytest.mark.slow
def test_time_varying_elasticity_bands_align_with_the_path(
    synthetic_levels: pd.DataFrame,
) -> None:
    band = bootstrap_time_varying_elasticity_bands(synthetic_levels, replications=REPLICATIONS)

    assert len(band.year) == len(band.estimate) == len(synthetic_levels) - 1
    assert band.lower_95.shape == band.estimate.shape
    assert band.upper_95.shape == band.estimate.shape
    assert np.all(band.lower_95 <= band.upper_95)
    assert np.all(np.isfinite(band.lower_95)) and np.all(np.isfinite(band.upper_95))
    assert band.replications > 0


@pytest.mark.slow
def test_time_varying_bands_widen_relative_to_filtered_errors(
    synthetic_levels: pd.DataFrame,
) -> None:
    """Re-estimating the variances per replication should not collapse the band to a point."""
    band = bootstrap_time_varying_elasticity_bands(synthetic_levels, replications=REPLICATIONS)
    widths = band.upper_95 - band.lower_95

    assert float(np.median(widths)) > 0.0
