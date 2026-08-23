"""Distributed-lag wage-growth regression."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from wage_transmission.models._regression import coefficients, fit_ols_hac, lagged
from wage_transmission.types import ModelSummary
from wage_transmission.validation import add_log_growth_columns


@dataclass(frozen=True)
class DistributedLagResult:
    """Distributed-lag result and cumulative wage transmission."""

    summary: ModelSummary
    cumulative_transmission: float
    cumulative_std_error: float
    cumulative_p_value: float


def fit_distributed_lag(
    frame: pd.DataFrame,
    *,
    x_lags: int = 2,
    y_lags: int = 1,
    hac_lags: int = 2,
) -> DistributedLagResult:
    """Regress real-wage growth on current/lagged productivity growth and wage growth.

    The cumulative transmission is the sum of the current and lagged driver coefficients. Its
    uncertainty is computed from the full HAC covariance matrix, retaining covariance across lags.
    """
    data = add_log_growth_columns(frame)
    x = lagged(data["dlog_productivity"], "prod", x_lags, include_zero=True)
    if y_lags > 0:
        x = pd.concat(
            [x, lagged(data["dlog_wage"], "wage", y_lags, include_zero=False)],
            axis=1,
        )
    fitted = fit_ols_hac(data["dlog_wage"], x, hac_lags=hac_lags)
    prod_names = [f"prod_l{lag}" for lag in range(x_lags + 1)]
    cumulative = float(sum(fitted.params[name] for name in prod_names))
    covariance = fitted.cov_params().loc[prod_names, prod_names].to_numpy(dtype=float)
    ones = np.ones(len(prod_names), dtype=float)
    cumulative_variance = float(ones @ covariance @ ones)
    cumulative_se = float(np.sqrt(max(cumulative_variance, 0.0)))
    if cumulative_se > 0.0:
        z_score = cumulative / cumulative_se
        cumulative_p_value = float(2.0 * norm.sf(abs(z_score)))
    else:
        cumulative_p_value = 0.0 if cumulative != 0.0 else 1.0

    summary = ModelSummary(
        model="distributed_lag",
        nobs=int(fitted.nobs),
        coefficients=coefficients(fitted),
        diagnostics={
            "r_squared": float(fitted.rsquared),
            "aic": float(fitted.aic),
            "bic": float(fitted.bic),
            "x_lags": x_lags,
            "y_lags": y_lags,
            "hac_lags": hac_lags,
        },
    )
    return DistributedLagResult(
        summary=summary,
        cumulative_transmission=cumulative,
        cumulative_std_error=cumulative_se,
        cumulative_p_value=cumulative_p_value,
    )
