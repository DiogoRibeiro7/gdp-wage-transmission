"""Country-by-country robustness estimates without imposing pooled homogeneity."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from wage_transmission.config import ModelsConfig
from wage_transmission.diagnostics.cointegration import engle_granger
from wage_transmission.models.distributed_lag import fit_distributed_lag
from wage_transmission.models.ecm import select_ecm_lags
from wage_transmission.models.state_space import fit_time_varying_elasticity
from wage_transmission.validation import add_log_growth_columns, validate_level_frame


@dataclass(frozen=True)
class CrossCountrySummary:
    """Descriptive and meta-analytic summary of country-specific transmission estimates."""

    driver: str
    n_countries: int
    median_cumulative_transmission: float
    q25_cumulative_transmission: float
    q75_cumulative_transmission: float
    positive_country_share: float
    fixed_effect_estimate: float
    fixed_effect_std_error: float
    random_effect_estimate: float
    random_effect_std_error: float
    tau_squared: float
    cochran_q: float
    i_squared_percent: float
    interpretation: str


def estimate_country_robustness(
    panel: pd.DataFrame,
    *,
    driver_column: str = "productivity",
    config: ModelsConfig | None = None,
    min_observations: int = 20,
) -> pd.DataFrame:
    """Estimate the same transparent specifications separately for each country.

    This function intentionally avoids a pooled panel coefficient as the default because pooling
    imposes cross-country homogeneity that is stronger than the primary research design requires.
    """
    if "country" not in panel.columns:
        raise ValueError("Cross-country input must contain a `country` column.")
    if driver_column not in panel.columns:
        raise ValueError(f"Driver column not found: {driver_column}")
    if min_observations < 12:
        raise ValueError("min_observations must be at least 12.")

    cfg = config or ModelsConfig()
    records: list[dict[str, float | int | str | bool]] = []
    for country, raw in panel.groupby("country", sort=True):
        prepared = raw.copy()
        prepared["productivity"] = pd.to_numeric(prepared[driver_column], errors="coerce")
        try:
            levels = validate_level_frame(prepared)
        except ValueError:
            continue
        if len(levels) < min_observations:
            continue

        transformed = add_log_growth_columns(levels)
        coint = engle_granger(
            transformed["log_wage"].to_numpy(),
            transformed["log_productivity"].to_numpy(),
        )
        distributed = fit_distributed_lag(
            levels,
            x_lags=cfg.distributed_lag.x_lags,
            y_lags=cfg.distributed_lag.y_lags,
            hac_lags=cfg.distributed_lag.hac_lags,
        )
        state = fit_time_varying_elasticity(
            levels,
            initial_state_variance=cfg.state_space.initial_state_variance,
        )

        ecm_theta = np.nan
        ecm_adjustment = np.nan
        if coint.p_value < 0.10:
            ecm = select_ecm_lags(
                levels,
                max_wage_growth_lags=cfg.ecm.max_wage_growth_lags,
                max_productivity_growth_lags=cfg.ecm.max_productivity_growth_lags,
                hac_lags=cfg.ecm.hac_lags,
            )
            ecm_theta = ecm.long_run_elasticity
            ecm_adjustment = ecm.adjustment_speed

        records.append(
            {
                "country": str(country),
                "driver": driver_column,
                "first_year": int(levels["year"].min()),
                "last_year": int(levels["year"].max()),
                "nobs": len(levels),
                "cointegration_p_value": float(coint.p_value),
                "cointegration_5pct": bool(coint.p_value < 0.05),
                "distributed_lag_cumulative": float(distributed.cumulative_transmission),
                "distributed_lag_cumulative_se": float(distributed.cumulative_std_error),
                "distributed_lag_cumulative_p_value": float(distributed.cumulative_p_value),
                "ecm_long_run_elasticity": float(ecm_theta),
                "ecm_adjustment_speed": float(ecm_adjustment),
                "tv_elasticity_latest": float(state.elasticity[-1]),
                "tv_elasticity_mean": float(np.mean(state.elasticity)),
                "tv_state_variance": float(state.state_variance),
                "tv_converged": bool(state.converged),
            }
        )
    return pd.DataFrame.from_records(records)


def summarise_country_robustness(
    frame: pd.DataFrame,
    *,
    driver: str | None = None,
) -> CrossCountrySummary:
    """Summarise country-specific cumulative transmission without hiding heterogeneity.

    The random-effects calculation uses the DerSimonian-Laird moment estimator. It is reported as
    a compact robustness summary, not as a replacement for the country-specific estimates.
    """
    required = {"distributed_lag_cumulative", "distributed_lag_cumulative_se"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Cross-country estimates are missing columns: {sorted(missing)}")

    data = frame.loc[:, list(required)].apply(pd.to_numeric, errors="coerce").dropna()
    data = data.loc[data["distributed_lag_cumulative_se"] > 0.0]
    if len(data) < 2:
        raise ValueError(
            "At least two country estimates with positive standard errors are required."
        )

    estimates = data["distributed_lag_cumulative"].to_numpy(dtype=float)
    variances = np.square(data["distributed_lag_cumulative_se"].to_numpy(dtype=float))
    weights = 1.0 / variances
    fixed = float(np.sum(weights * estimates) / np.sum(weights))
    fixed_se = float(np.sqrt(1.0 / np.sum(weights)))
    q_stat = float(np.sum(weights * np.square(estimates - fixed)))
    degrees_freedom = len(estimates) - 1
    c_term = float(np.sum(weights) - np.sum(np.square(weights)) / np.sum(weights))
    tau_squared = float(max(0.0, (q_stat - degrees_freedom) / c_term)) if c_term > 0 else 0.0
    random_weights = 1.0 / (variances + tau_squared)
    random = float(np.sum(random_weights * estimates) / np.sum(random_weights))
    random_se = float(np.sqrt(1.0 / np.sum(random_weights)))
    i_squared = (
        float(max(0.0, (q_stat - degrees_freedom) / q_stat) * 100.0) if q_stat > 0.0 else 0.0
    )
    if i_squared >= 75.0:
        interpretation = "substantial_cross_country_heterogeneity"
    elif i_squared >= 50.0:
        interpretation = "moderate_cross_country_heterogeneity"
    else:
        interpretation = "limited_cross_country_heterogeneity"

    if driver is None:
        driver_values = frame.get("driver")
        if driver_values is not None and len(pd.unique(driver_values.dropna())) == 1:
            driver = str(driver_values.dropna().iloc[0])
        else:
            driver = "unspecified"

    return CrossCountrySummary(
        driver=driver,
        n_countries=len(estimates),
        median_cumulative_transmission=float(np.median(estimates)),
        q25_cumulative_transmission=float(np.quantile(estimates, 0.25)),
        q75_cumulative_transmission=float(np.quantile(estimates, 0.75)),
        positive_country_share=float(np.mean(estimates > 0.0)),
        fixed_effect_estimate=fixed,
        fixed_effect_std_error=fixed_se,
        random_effect_estimate=random,
        random_effect_std_error=random_se,
        tau_squared=tau_squared,
        cochran_q=q_stat,
        i_squared_percent=i_squared,
        interpretation=interpretation,
    )


def write_country_robustness(frame: pd.DataFrame, output: Path) -> Path:
    """Persist country-level robustness estimates to CSV."""
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return output
