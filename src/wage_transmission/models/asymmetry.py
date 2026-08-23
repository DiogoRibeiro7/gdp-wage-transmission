"""Asymmetric wage response to productivity expansions and contractions."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from wage_transmission.models._regression import coefficients, fit_ols_hac
from wage_transmission.types import ModelSummary
from wage_transmission.validation import add_log_growth_columns


@dataclass(frozen=True)
class AsymmetryResult:
    """Positive and negative cumulative transmission estimates."""

    summary: ModelSummary
    positive_cumulative: float
    negative_cumulative: float
    difference: float


def fit_asymmetric_transmission(
    frame: pd.DataFrame,
    *,
    lags: int = 2,
    hac_lags: int = 2,
) -> AsymmetryResult:
    """Estimate separate distributed responses to positive and negative productivity growth."""
    if lags < 0:
        raise ValueError("lags must be non-negative")
    data = add_log_growth_columns(frame)
    positive = data["dlog_productivity"].clip(lower=0.0)
    negative = data["dlog_productivity"].clip(upper=0.0)
    regressors = pd.DataFrame(index=data.index)
    for lag in range(lags + 1):
        regressors[f"pos_l{lag}"] = positive.shift(lag)
        regressors[f"neg_l{lag}"] = negative.shift(lag)
    regressors["dwage_l1"] = data["dlog_wage"].shift(1)
    fitted = fit_ols_hac(data["dlog_wage"], regressors, hac_lags=hac_lags)
    positive_sum = float(sum(fitted.params[f"pos_l{lag}"] for lag in range(lags + 1)))
    negative_sum = float(sum(fitted.params[f"neg_l{lag}"] for lag in range(lags + 1)))
    summary = ModelSummary(
        model="asymmetric_transmission",
        nobs=int(fitted.nobs),
        coefficients=coefficients(fitted),
        diagnostics={
            "r_squared": float(fitted.rsquared),
            "aic": float(fitted.aic),
            "bic": float(fitted.bic),
            "lags": lags,
            "hac_lags": hac_lags,
        },
    )
    return AsymmetryResult(
        summary=summary,
        positive_cumulative=positive_sum,
        negative_cumulative=negative_sum,
        difference=positive_sum - negative_sum,
    )
