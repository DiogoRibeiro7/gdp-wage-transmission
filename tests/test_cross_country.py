from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wage_transmission.cross_country import (
    estimate_country_robustness,
    estimate_panel_fixed_effects,
)


def _panel_with_elasticities(betas: dict[str, float], *, seed: int = 99) -> pd.DataFrame:
    """Build a panel whose countries transmit productivity at known rates."""
    rng = np.random.default_rng(seed)
    years = np.arange(1980, 2025)
    frames = []
    for country, beta in betas.items():
        productivity_growth = rng.normal(0.017, 0.017, len(years))
        wage_growth = 0.001 + beta * productivity_growth + rng.normal(0, 0.006, len(years))
        frames.append(
            pd.DataFrame(
                {
                    "country": country,
                    "year": years,
                    "real_wage": 20000.0 * np.exp(np.cumsum(wage_growth)),
                    "productivity": 30.0 * np.exp(np.cumsum(productivity_growth)),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_cross_country_estimates_are_country_specific(synthetic_levels: pd.DataFrame) -> None:
    first = synthetic_levels.copy()
    first["country"] = "AAA"
    second = synthetic_levels.copy()
    second["country"] = "BBB"
    second["real_wage"] = second["real_wage"] * 1.15
    panel = pd.concat([first, second], ignore_index=True)

    result = estimate_country_robustness(panel, min_observations=20)

    assert set(result["country"]) == {"AAA", "BBB"}
    assert (result["nobs"] == len(synthetic_levels)).all()


def test_cross_country_summary_reports_heterogeneity(synthetic_levels: pd.DataFrame) -> None:
    from wage_transmission.cross_country import summarise_country_robustness

    countries = []
    for idx, scale in enumerate([0.6, 0.8, 1.0, 1.2]):
        frame = synthetic_levels.copy()
        frame["country"] = f"C{idx}"
        # Scaling levels alone leaves log growth unchanged; perturb growth transmission instead.
        log_prod = pd.Series(frame["productivity"]).map(np.log)
        prod_growth = log_prod.diff().fillna(0.0)
        log_wage = np.log(frame["real_wage"].iloc[0]) + (scale * prod_growth).cumsum()
        frame["real_wage"] = np.exp(log_wage)
        countries.append(frame)
    panel = pd.concat(countries, ignore_index=True)
    estimates = estimate_country_robustness(panel, min_observations=20)
    summary = summarise_country_robustness(estimates)
    assert summary.n_countries == 4
    assert np.isfinite(summary.random_effect_estimate)
    assert summary.random_effect_std_error > 0.0
    assert 0.0 <= summary.i_squared_percent <= 100.0


def test_panel_fixed_effects_recovers_a_common_elasticity() -> None:
    panel = _panel_with_elasticities({"AAA": 0.7, "BBB": 0.7, "CCC": 0.7, "DDD": 0.7})

    result = estimate_panel_fixed_effects(panel)

    assert result.n_countries == 4
    assert result.elasticity == pytest.approx(0.7, abs=0.1)
    assert result.lower_95 < result.elasticity < result.upper_95
    assert 0.0 < result.within_r_squared <= 1.0


def test_panel_fixed_effects_clusters_by_country() -> None:
    panel = _panel_with_elasticities({"AAA": 0.3, "BBB": 0.9, "CCC": 0.5, "DDD": 1.1})

    result = estimate_panel_fixed_effects(panel)

    assert result.std_error > 0.0
    assert np.isfinite(result.t_statistic)
    # Four clusters is far below the asymptotic regime, and the result must say so.
    assert result.interpretation == "pooled_estimate_few_clusters_standard_errors_optimistic"
    assert result.min_countries_for_clustering == 30


def test_panel_fixed_effects_absorb_common_year_shocks() -> None:
    panel = _panel_with_elasticities({"AAA": 0.6, "BBB": 0.6, "CCC": 0.6})

    without = estimate_panel_fixed_effects(panel, time_effects=False)
    with_time = estimate_panel_fixed_effects(panel, time_effects=True)

    assert without.time_effects is False
    assert with_time.time_effects is True
    assert np.isfinite(with_time.elasticity)
    assert with_time.nobs == without.nobs


def test_panel_fixed_effects_require_more_than_one_country() -> None:
    panel = _panel_with_elasticities({"AAA": 0.7})

    with pytest.raises(ValueError, match="at least two countries"):
        estimate_panel_fixed_effects(panel)


def test_panel_fixed_effects_reject_an_unknown_driver() -> None:
    panel = _panel_with_elasticities({"AAA": 0.7, "BBB": 0.7})

    with pytest.raises(ValueError, match="Driver column not found"):
        estimate_panel_fixed_effects(panel, driver_column="not_a_column")
