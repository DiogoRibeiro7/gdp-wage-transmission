"""Transparent two-step Engle–Granger error-correction model."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import statsmodels.api as sm

from wage_transmission.models._regression import coefficients, fit_ols_hac, lagged
from wage_transmission.types import ModelSummary
from wage_transmission.validation import add_log_growth_columns


@dataclass(frozen=True)
class ECMResult:
    """Long-run and short-run ECM estimates."""

    summary: ModelSummary
    long_run_intercept: float
    long_run_elasticity: float
    adjustment_speed: float
    wage_growth_lags: int
    productivity_growth_lags: int


def _fit_candidate(data: pd.DataFrame, p: int, q: int, hac_lags: int) -> tuple[ECMResult, float]:
    levels = data[["log_wage", "log_productivity"]].dropna()
    level_x = sm.add_constant(levels[["log_productivity"]], has_constant="add")
    long_run = sm.OLS(levels["log_wage"], level_x).fit()
    intercept = float(long_run.params["const"])
    theta = float(long_run.params["log_productivity"])

    data = data.copy()
    data["ect"] = data["log_wage"] - intercept - theta * data["log_productivity"]
    regressors = pd.DataFrame({"ect_l1": data["ect"].shift(1)}, index=data.index)
    if p > 0:
        regressors = pd.concat(
            [regressors, lagged(data["dlog_wage"], "dwage", p, include_zero=False)],
            axis=1,
        )
    regressors = pd.concat(
        [regressors, lagged(data["dlog_productivity"], "dprod", q, include_zero=True)],
        axis=1,
    )
    fitted = fit_ols_hac(data["dlog_wage"], regressors, hac_lags=hac_lags)
    summary = ModelSummary(
        model="ecm",
        nobs=int(fitted.nobs),
        coefficients=coefficients(fitted),
        diagnostics={
            "r_squared": float(fitted.rsquared),
            "aic": float(fitted.aic),
            "bic": float(fitted.bic),
            "long_run_r_squared": float(long_run.rsquared),
            "hac_lags": hac_lags,
        },
    )
    result = ECMResult(
        summary=summary,
        long_run_intercept=intercept,
        long_run_elasticity=theta,
        adjustment_speed=float(fitted.params["ect_l1"]),
        wage_growth_lags=p,
        productivity_growth_lags=q,
    )
    return result, float(fitted.aic)


def fit_ecm(
    frame: pd.DataFrame,
    *,
    wage_growth_lags: int = 1,
    productivity_growth_lags: int = 1,
    hac_lags: int = 2,
) -> ECMResult:
    """Estimate a two-step ECM with user-specified short-run lags."""
    if wage_growth_lags < 0 or productivity_growth_lags < 0:
        raise ValueError("ECM lags must be non-negative.")
    data = add_log_growth_columns(frame)
    result, _ = _fit_candidate(data, wage_growth_lags, productivity_growth_lags, hac_lags)
    return result


def select_ecm_lags(
    frame: pd.DataFrame,
    *,
    max_wage_growth_lags: int = 2,
    max_productivity_growth_lags: int = 2,
    hac_lags: int = 2,
) -> ECMResult:
    """Select ECM short-run lags by minimum AIC over a small transparent grid."""
    data = add_log_growth_columns(frame)
    candidates: list[tuple[float, ECMResult]] = []
    for p in range(max_wage_growth_lags + 1):
        for q in range(max_productivity_growth_lags + 1):
            try:
                result, aic = _fit_candidate(data, p, q, hac_lags)
            except ValueError:
                continue
            candidates.append((aic, result))
    if not candidates:
        raise ValueError("No feasible ECM lag specification was estimable.")
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]
