"""Shared regression utilities."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.linear_model import RegressionResultsWrapper

from wage_transmission.types import RegressionCoefficient


def fit_ols_hac(
    y: pd.Series,
    x: pd.DataFrame,
    *,
    hac_lags: int,
) -> RegressionResultsWrapper:
    """Fit OLS with an intercept and Newey–West/HAC covariance."""
    design = sm.add_constant(x, has_constant="add")
    joined = pd.concat([y.rename("__y__"), design], axis=1).dropna()
    if len(joined) <= design.shape[1] + 2:
        raise ValueError("Insufficient complete observations for the requested regression.")
    fitted = sm.OLS(joined["__y__"], joined.drop(columns="__y__")).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": int(hac_lags)},
    )
    return fitted


def coefficients(result: RegressionResultsWrapper, names: Iterable[str] | None = None) -> tuple[RegressionCoefficient, ...]:
    """Convert statsmodels coefficients to typed result objects."""
    selected = list(result.params.index if names is None else names)
    output: list[RegressionCoefficient] = []
    for name in selected:
        output.append(
            RegressionCoefficient(
                name=str(name),
                estimate=float(result.params[name]),
                std_error=float(result.bse[name]),
                p_value=float(result.pvalues[name]),
            )
        )
    return tuple(output)


def lagged(series: pd.Series, prefix: str, max_lag: int, *, include_zero: bool) -> pd.DataFrame:
    """Build named current/lagged regressors."""
    if max_lag < 0:
        raise ValueError("max_lag must be non-negative")
    start = 0 if include_zero else 1
    data: dict[str, pd.Series] = {}
    for lag in range(start, max_lag + 1):
        name = f"{prefix}_l{lag}"
        data[name] = series.shift(lag)
    return pd.DataFrame(data, index=series.index)
