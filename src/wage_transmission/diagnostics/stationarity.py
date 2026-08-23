"""ADF and KPSS stationarity diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from statsmodels.tsa.stattools import adfuller, kpss


@dataclass(frozen=True)
class StationarityResult:
    """One stationarity-test result."""

    test: str
    statistic: float
    p_value: float
    lags: int
    nobs: int


def adf_test(values: np.ndarray, *, regression: str = "ct") -> StationarityResult:
    """Run an augmented Dickey–Fuller unit-root test."""
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    statistic, p_value, lags, nobs, *_ = adfuller(array, regression=regression, autolag="AIC")
    return StationarityResult("ADF", float(statistic), float(p_value), int(lags), int(nobs))


def kpss_test(values: np.ndarray, *, regression: str = "ct") -> StationarityResult:
    """Run a KPSS stationarity test."""
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    statistic, p_value, lags, _ = kpss(array, regression=regression, nlags="auto")
    return StationarityResult("KPSS", float(statistic), float(p_value), int(lags), len(array))
