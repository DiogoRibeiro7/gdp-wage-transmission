"""Jordà-style local projections for dynamic wage responses."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from wage_transmission.models._regression import fit_ols_hac
from wage_transmission.validation import add_log_growth_columns


@dataclass(frozen=True)
class LocalProjectionPoint:
    """Estimated response at one horizon."""

    horizon: int
    estimate: float
    std_error: float
    lower_95: float
    upper_95: float
    nobs: int


def fit_local_projections(
    frame: pd.DataFrame,
    *,
    horizon: int = 8,
    control_lags: int = 2,
    hac_lags: int = 2,
) -> tuple[LocalProjectionPoint, ...]:
    """Estimate cumulative log-wage responses to current productivity growth.

    These are dynamic associations unless the productivity innovation is separately identified
    as an exogenous structural shock.
    """
    if horizon < 0 or control_lags < 0:
        raise ValueError("horizon and control_lags must be non-negative")
    data = add_log_growth_columns(frame)
    output: list[LocalProjectionPoint] = []
    for h in range(horizon + 1):
        # Cumulative wage change from t-1 through t+h.
        target = data["log_wage"].shift(-h) - data["log_wage"].shift(1)
        regressors = pd.DataFrame({"shock": data["dlog_productivity"]}, index=data.index)
        for lag in range(1, control_lags + 1):
            regressors[f"dprod_l{lag}"] = data["dlog_productivity"].shift(lag)
            regressors[f"dwage_l{lag}"] = data["dlog_wage"].shift(lag)
        fitted = fit_ols_hac(target, regressors, hac_lags=max(hac_lags, h))
        estimate = float(fitted.params["shock"])
        std_error = float(fitted.bse["shock"])
        output.append(
            LocalProjectionPoint(
                horizon=h,
                estimate=estimate,
                std_error=std_error,
                lower_95=estimate - 1.96 * std_error,
                upper_95=estimate + 1.96 * std_error,
                nobs=int(fitted.nobs),
            )
        )
    return tuple(output)
