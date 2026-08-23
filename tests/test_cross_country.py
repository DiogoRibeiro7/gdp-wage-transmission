from __future__ import annotations

import numpy as np
import pandas as pd

from wage_transmission.cross_country import estimate_country_robustness


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
