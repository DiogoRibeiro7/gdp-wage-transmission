from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wage_transmission.config import DynamicPanelConfig
from wage_transmission.models.dynamic_panel import (
    BiasCorrector,
    WithinProjector,
    build_growth_panel,
    build_panel_design,
    circular_block_columns,
    driscoll_kraay_covariance,
    estimate_dynamic_panel,
    estimate_dynamic_panel_suite,
    fit_lsdv,
)

COUNTRIES = tuple(f"C{index:02d}" for index in range(13))
FIRST_YEAR = 1995
YEARS = 31


def _synthetic_panel(
    *,
    seed: int = 11,
    gamma: float = 0.5,
    beta: tuple[float, float, float] = (0.4, 0.1, 0.0),
    short_country: str | None = "C12",
) -> pd.DataFrame:
    """A 13-country annual panel generated from the model the estimator assumes.

    One country stops a year early, which reproduces the unbalanced endpoint of the real
    sample without depending on it.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict[str, float | int | str]] = []
    for country in COUNTRIES:
        n_years = YEARS - 1 if country == short_country else YEARS
        driver_growth = rng.normal(0.015, 0.02, size=n_years)
        shocks = rng.normal(0.0, 0.01, size=n_years)
        level_effect = float(rng.normal(0.005, 0.002))
        wage_growth = np.zeros(n_years, dtype=float)
        for step in range(1, n_years):
            driven = sum(
                beta[lag] * driver_growth[step - lag] for lag in range(3) if step - lag >= 0
            )
            wage_growth[step] = level_effect + driven + gamma * wage_growth[step - 1] + shocks[step]
        wage = 30_000.0 * np.exp(np.cumsum(wage_growth))
        driver = 60_000.0 * np.exp(np.cumsum(driver_growth))
        for offset in range(n_years):
            rows.append(
                {
                    "country": country,
                    "year": FIRST_YEAR + offset,
                    "real_wage": float(wage[offset]),
                    "productivity": float(driver[offset]),
                }
            )
    return pd.DataFrame(rows)


def _design(panel: pd.DataFrame):
    growth = build_growth_panel(panel, driver_column="productivity")
    return growth, build_panel_design(
        growth.wage_growth, growth.driver_growth, growth.countries, driver_lags=2
    )


def test_design_reproduces_the_unbalanced_regression_sample() -> None:
    """Twelve countries contribute 28 rows and the short one 27, as 12(28) + 27 = 363."""
    _, design = _design(_synthetic_panel())

    assert design.nobs == 12 * 28 + 27
    assert design.n_countries == 13
    assert design.n_periods == 28
    counts = np.bincount(design.country_index)
    assert sorted(counts.tolist()) == [27] + [28] * 12


def test_the_lagged_regressor_is_the_previous_period_of_the_same_country() -> None:
    growth, design = _design(_synthetic_panel())

    for row in range(design.nobs):
        country = int(design.country_index[row])
        period = int(design.period_index[row])
        column = period + 2
        assert design.outcome[row] == pytest.approx(growth.wage_growth[country, column])
        assert design.lagged_outcome[row] == pytest.approx(growth.wage_growth[country, column - 1])
        assert design.driver[row, 2] == pytest.approx(growth.driver_growth[country, column - 2])


def test_an_interior_gap_is_rejected_rather_than_spliced() -> None:
    """Reconstructing a lag across a hole would silently pair non-adjacent years."""
    growth, _ = _design(_synthetic_panel())
    wage = growth.wage_growth.copy()
    wage[3, 10] = np.nan

    with pytest.raises(ValueError, match="interior gap"):
        build_panel_design(wage, growth.driver_growth, growth.countries, driver_lags=2)


def test_the_multiplier_is_the_cumulative_definition() -> None:
    _, design = _design(_synthetic_panel())
    fit = fit_lsdv(design, WithinProjector(design, fixed_effects="country_and_year"))

    expected = fit.driver_sum / (1.0 - fit.persistence)
    assert fit.multiplier == pytest.approx(expected)
    assert fit.driver_sum == pytest.approx(float(np.sum(fit.coefficients[:3])))


def test_year_effects_change_the_estimate_but_not_the_sample() -> None:
    _, design = _design(_synthetic_panel())

    country_only = fit_lsdv(design, WithinProjector(design, fixed_effects="country"))
    two_way = fit_lsdv(design, WithinProjector(design, fixed_effects="country_and_year"))

    assert country_only.nobs == two_way.nobs == design.nobs
    assert not country_only.rank_deficient
    assert not two_way.rank_deficient
    assert country_only.multiplier != pytest.approx(two_way.multiplier)


def test_bias_correction_removes_most_of_the_dynamic_fixed_effects_bias() -> None:
    """LSDV understates persistence by about (1 + gamma) / T; the correction should not.

    This is the property the correction exists for, so it is checked against a panel whose
    true parameters are known rather than against a stored number.
    """
    gamma = 0.5
    lsdv: list[float] = []
    corrected: list[float] = []
    for replication in range(40):
        panel = _synthetic_panel(seed=200 + replication, gamma=gamma)
        _, design = _design(panel)
        projector = WithinProjector(design, fixed_effects="country")
        fit = fit_lsdv(design, projector, check_rank=False)
        correction = BiasCorrector(
            design,
            projector,
            draws=100,
            iterations=12,
            rng=np.random.default_rng(replication),
        ).correct(fit)
        lsdv.append(fit.persistence)
        corrected.append(correction.persistence)

    lsdv_bias = float(np.mean(lsdv)) - gamma
    corrected_bias = float(np.mean(corrected)) - gamma
    assert lsdv_bias < -0.02, "the uncorrected estimator should show the downward Nickell bias"
    # Measured removal is 88-97% across gamma in [0.3, 0.7]; the floor here sits below that so
    # the test guards the manuscript's claim without tripping on simulation noise.
    assert abs(corrected_bias) < abs(lsdv_bias) / 5.0


def test_circular_blocks_wrap_and_return_the_requested_length() -> None:
    universe = np.arange(29)
    drawn = circular_block_columns(universe, 30, 4, np.random.default_rng(3))

    assert drawn.size == 30
    assert set(drawn.tolist()).issubset(set(universe.tolist()))
    with pytest.raises(ValueError, match="block_length"):
        circular_block_columns(universe, 30, 40, np.random.default_rng(3))


def test_driscoll_kraay_covariance_is_a_positive_definite_matrix() -> None:
    _, design = _design(_synthetic_panel())
    projector = WithinProjector(design, fixed_effects="country_and_year")
    fit = fit_lsdv(design, projector)

    covariance = driscoll_kraay_covariance(design, projector, fit, lags=3)

    assert covariance.shape == (4, 4)
    assert np.allclose(covariance, covariance.T)
    assert float(np.min(np.linalg.eigvalsh(covariance))) > 0.0


def test_every_bootstrap_replication_reproduces_the_observed_panel_shape() -> None:
    """A replication whose design differs from the observed one is discarded, not reshaped."""
    result = estimate_dynamic_panel(
        _synthetic_panel(),
        fixed_effects="country_and_year",
        replications=60,
        bias_correction_draws=40,
        seed=5,
    )

    assert result.nobs == 12 * 28 + 27
    assert result.replications_completed == result.replications_requested == 60
    assert result.convergence_share == 1.0
    assert result.finite_multiplier_share == 1.0
    low, high = result.corrected_multiplier_ci
    assert low < result.corrected_multiplier_bootstrap_median < high


def test_the_bootstrap_displacement_is_reported_not_hidden() -> None:
    """Gluing blocks breaks the dynamic relation at boundaries, so the draws are displaced.

    The point estimate and the median replication are both reported, which is the only way a
    reader can tell how far apart they are.
    """
    result = estimate_dynamic_panel(
        _synthetic_panel(gamma=0.6),
        replications=80,
        bias_correction_draws=60,
        seed=5,
    )

    assert result.corrected_persistence_bootstrap_median < result.corrected_persistence
    assert result.corrected_multiplier_bootstrap_median < result.corrected_multiplier


def test_a_failed_gate_is_recorded_rather_than_hiding_the_estimate() -> None:
    from wage_transmission.models.dynamic_panel import DynamicPanelGates

    result = estimate_dynamic_panel(
        _synthetic_panel(),
        replications=60,
        bias_correction_draws=40,
        seed=5,
        gates=DynamicPanelGates(min_effective_years=99),
    )

    assert not result.claim_eligible
    assert "insufficient_effective_years" in result.gate_failures
    assert np.isfinite(result.corrected_multiplier)


def test_the_suite_runs_the_frozen_hierarchy_in_order() -> None:
    suite = estimate_dynamic_panel_suite(
        _synthetic_panel(),
        driver_column="productivity",
        config=DynamicPanelConfig(
            replications=99,
            bias_correction_draws=30,
            sensitivity_block_lengths=(3, 5),
        ),
    )

    roles = [item.role for item in suite.specifications]
    assert roles == [
        "primary",
        "sensitivity_fixed_effects",
        "sensitivity_block_length",
        "sensitivity_block_length",
    ]
    assert suite.primary.fixed_effects == "country_and_year"
    assert suite.primary.block_length == 4
    assert [item.block_length for item in suite.specifications[2:]] == [3, 5]
    assert suite.specifications[1].fixed_effects == "country"


def test_the_estimator_refuses_a_panel_with_one_country() -> None:
    single = _synthetic_panel().loc[lambda frame: frame["country"] == "C00"]

    with pytest.raises(ValueError, match="at least two countries"):
        build_growth_panel(single, driver_column="productivity")
