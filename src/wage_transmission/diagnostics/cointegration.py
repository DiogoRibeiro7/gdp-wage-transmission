"""Cointegration diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from statsmodels.tsa.stattools import coint


@dataclass(frozen=True)
class CointegrationResult:
    """Engle–Granger cointegration-test result."""

    statistic: float
    p_value: float
    critical_1pct: float
    critical_5pct: float
    critical_10pct: float


def engle_granger(log_wage: np.ndarray, log_productivity: np.ndarray) -> CointegrationResult:
    """Test whether log wages and log productivity are cointegrated."""
    y = np.asarray(log_wage, dtype=float)
    x = np.asarray(log_productivity, dtype=float)
    mask = np.isfinite(y) & np.isfinite(x)
    statistic, p_value, critical = coint(y[mask], x[mask], trend="c", autolag="aic")
    return CointegrationResult(
        statistic=float(statistic),
        p_value=float(p_value),
        critical_1pct=float(critical[0]),
        critical_5pct=float(critical[1]),
        critical_10pct=float(critical[2]),
    )
