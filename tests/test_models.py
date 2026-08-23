from __future__ import annotations

import numpy as np
import pandas as pd

from wage_transmission.models.asymmetry import fit_asymmetric_transmission
from wage_transmission.models.distributed_lag import fit_distributed_lag
from wage_transmission.models.ecm import select_ecm_lags
from wage_transmission.models.local_projections import fit_local_projections
from wage_transmission.models.state_space import fit_time_varying_elasticity
from wage_transmission.models.structural_breaks import fit_structural_breaks


def test_distributed_lag_runs(synthetic_levels: pd.DataFrame) -> None:
    result = fit_distributed_lag(synthetic_levels, x_lags=1, y_lags=1)
    assert result.summary.nobs > 40
    assert np.isfinite(result.cumulative_transmission)
    assert np.isfinite(result.cumulative_std_error)
    assert result.cumulative_std_error >= 0.0
    assert 0.0 <= result.cumulative_p_value <= 1.0


def test_ecm_lag_selection_runs(synthetic_levels: pd.DataFrame) -> None:
    result = select_ecm_lags(
        synthetic_levels,
        max_wage_growth_lags=1,
        max_productivity_growth_lags=1,
    )
    assert result.summary.nobs > 40
    assert np.isfinite(result.long_run_elasticity)
    assert np.isfinite(result.adjustment_speed)


def test_structural_breaks_find_piecewise_solution(synthetic_levels: pd.DataFrame) -> None:
    result = fit_structural_breaks(synthetic_levels, max_breaks=2, min_segment=10)
    assert 0 <= result.n_breaks <= 2
    assert sum(segment.nobs for segment in result.segments) == len(synthetic_levels) - 1
    assert all(np.isfinite(segment.elasticity) for segment in result.segments)


def test_state_space_runs(synthetic_levels: pd.DataFrame) -> None:
    result = fit_time_varying_elasticity(synthetic_levels)
    assert len(result.year) == len(synthetic_levels) - 1
    assert np.all(np.isfinite(result.elasticity))
    assert result.observation_variance > 0
    assert result.state_variance > 0


def test_local_projections_run(synthetic_levels: pd.DataFrame) -> None:
    points = fit_local_projections(synthetic_levels, horizon=4, control_lags=1)
    assert len(points) == 5
    assert all(np.isfinite(point.estimate) for point in points)


def test_asymmetry_runs(synthetic_levels: pd.DataFrame) -> None:
    result = fit_asymmetric_transmission(synthetic_levels, lags=1)
    assert np.isfinite(result.positive_cumulative)
    assert np.isfinite(result.negative_cumulative)


def test_pipeline_accepts_alternative_driver(tmp_path, synthetic_levels: pd.DataFrame) -> None:
    from wage_transmission.pipeline import analyse_country

    frame = synthetic_levels.copy()
    frame["real_gdp"] = frame["productivity"] * 1000.0
    outputs = analyse_country(frame, tmp_path / "gdp", driver_column="real_gdp")
    assert outputs["metadata"]["driver_column"] == "real_gdp"
    assert "ecm_long_run_interpretation_supported_5pct" in outputs["metadata"]
