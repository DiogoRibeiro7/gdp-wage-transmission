"""Jordà-style local projections for dynamic wage responses."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from wage_transmission.models._bootstrap import (
    DEFAULT_BLOCK_LENGTH,
    percentile_band,
    resample_level_frame,
)
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


@dataclass(frozen=True)
class LocalProjectionBand:
    """Bootstrap band around the local-projection response at one horizon."""

    horizon: int
    estimate: float
    lower_95: float
    upper_95: float
    replications: int
    block_length: int
    seed: int


def bootstrap_local_projection_bands(
    frame: pd.DataFrame,
    *,
    horizon: int = 8,
    control_lags: int = 2,
    hac_lags: int = 2,
    replications: int = 499,
    block_length: int = DEFAULT_BLOCK_LENGTH,
    seed: int = 20260824,
) -> tuple[LocalProjectionBand, ...]:
    """Block-bootstrap percentile bands for the local-projection responses.

    The HAC standard errors returned by :func:`fit_local_projections` are asymptotic and are
    known to be optimistic at longer horizons in short annual samples, where the overlapping
    windows leave few effective observations. These bands resample the joint growth pairs in
    blocks instead, so serial dependence is preserved and the horizon-specific uncertainty is
    not understated.

    Replications that fail to estimate -- a resample can leave too few complete observations at
    the longest horizons -- are dropped, and the surviving count is reported per horizon.
    """
    if replications < 99:
        raise ValueError("replications must be at least 99 for a usable percentile band")

    point_estimates = fit_local_projections(
        frame, horizon=horizon, control_lags=control_lags, hac_lags=hac_lags
    )
    data = add_log_growth_columns(frame)
    rng = np.random.default_rng(seed)

    draws: list[list[float]] = []
    for _ in range(replications):
        resampled = resample_level_frame(data, block_length=block_length, rng=rng)
        try:
            fitted = fit_local_projections(
                resampled, horizon=horizon, control_lags=control_lags, hac_lags=hac_lags
            )
        except (ValueError, np.linalg.LinAlgError):
            continue
        draws.append([point.estimate for point in fitted])

    if not draws:
        raise ValueError("Every bootstrap replication failed; the sample is too short.")

    matrix = np.asarray(draws, dtype=float)
    lower, upper = percentile_band(matrix)
    return tuple(
        LocalProjectionBand(
            horizon=point.horizon,
            estimate=point.estimate,
            lower_95=float(lower[index]),
            upper_95=float(upper[index]),
            replications=len(draws),
            block_length=int(block_length),
            seed=int(seed),
        )
        for index, point in enumerate(point_estimates)
    )
