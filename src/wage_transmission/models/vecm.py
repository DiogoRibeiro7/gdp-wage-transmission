"""Optional VECM wrapper for joint wage-productivity dynamics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.tsa.vector_ar.vecm import VECM, select_coint_rank

from wage_transmission.validation import add_log_growth_columns


@dataclass(frozen=True)
class VECMResult:
    """VECM rank and orthogonalised/non-structural impulse responses."""

    cointegration_rank: int
    alpha: np.ndarray
    beta: np.ndarray
    impulse_responses: np.ndarray


def fit_vecm(
    frame: pd.DataFrame,
    *,
    k_ar_diff: int = 1,
    irf_periods: int = 8,
) -> VECMResult:
    """Fit a bivariate VECM in log wage and log productivity levels.

    The returned impulse responses are reduced-form dynamics, not causal structural shocks.
    """
    data = add_log_growth_columns(frame)
    levels = data[["log_wage", "log_productivity"]].dropna().to_numpy(dtype=float)
    if len(levels) < 20:
        raise ValueError("At least 20 observations are recommended for VECM estimation.")
    rank_result = select_coint_rank(
        levels, det_order=0, k_ar_diff=k_ar_diff, method="trace", signif=0.05
    )
    rank = int(rank_result.rank)
    if rank < 1:
        raise ValueError(
            "No cointegrating relation selected; a VECM with rank >= 1 is not justified."
        )
    fitted = VECM(levels, k_ar_diff=k_ar_diff, coint_rank=rank, deterministic="co").fit()
    irfs = fitted.irf(periods=irf_periods).irfs
    return VECMResult(
        cointegration_rank=rank,
        alpha=np.asarray(fitted.alpha, dtype=float),
        beta=np.asarray(fitted.beta, dtype=float),
        impulse_responses=np.asarray(irfs, dtype=float),
    )
