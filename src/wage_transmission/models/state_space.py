"""State-space model for a time-varying wage-transmission elasticity."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from wage_transmission.models._bootstrap import (
    DEFAULT_BLOCK_LENGTH,
    percentile_band,
    resample_level_frame,
)
from wage_transmission.validation import add_log_growth_columns


@dataclass(frozen=True)
class TimeVaryingElasticityResult:
    """Filtered time-varying intercept and productivity elasticity."""

    year: np.ndarray
    intercept: np.ndarray
    elasticity: np.ndarray
    elasticity_std_error: np.ndarray
    observation_variance: float
    state_variance: float
    log_likelihood: float
    converged: bool


def _kalman_filter(
    y: np.ndarray,
    x: np.ndarray,
    *,
    observation_variance: float,
    state_variance: float,
    initial_state_variance: float,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Filter a local-level intercept plus random-walk slope model."""
    state = np.array([float(np.mean(y)), 0.5], dtype=float)
    covariance = np.eye(2, dtype=float) * initial_state_variance
    transition_noise = np.diag([1e-12, state_variance])
    states = np.zeros((len(y), 2), dtype=float)
    covariances = np.zeros((len(y), 2, 2), dtype=float)
    log_likelihood = 0.0

    for idx, (target, regressor) in enumerate(zip(y, x, strict=True)):
        predicted_state = state
        predicted_covariance = covariance + transition_noise
        design = np.array([1.0, regressor], dtype=float)
        innovation = target - float(design @ predicted_state)
        innovation_variance = float(design @ predicted_covariance @ design + observation_variance)
        innovation_variance = max(innovation_variance, 1e-12)
        gain = predicted_covariance @ design / innovation_variance
        state = predicted_state + gain * innovation
        covariance = predicted_covariance - np.outer(gain, design) @ predicted_covariance
        covariance = (covariance + covariance.T) / 2.0

        log_likelihood += -0.5 * (
            np.log(2.0 * np.pi) + np.log(innovation_variance) + innovation**2 / innovation_variance
        )
        states[idx] = state
        covariances[idx] = covariance

    return float(log_likelihood), states, covariances


def fit_time_varying_elasticity(
    frame: pd.DataFrame,
    *,
    initial_state_variance: float = 100.0,
) -> TimeVaryingElasticityResult:
    """Estimate a random-walk productivity elasticity by maximum likelihood.

    The observation equation is

    dlog(wage)_t = alpha_t + beta_t dlog(productivity)_t + epsilon_t,

    with an effectively fixed intercept and random-walk beta_t.
    """
    if initial_state_variance <= 0:
        raise ValueError("initial_state_variance must be positive")
    data = add_log_growth_columns(frame).dropna(subset=["dlog_wage", "dlog_productivity"])
    y = data["dlog_wage"].to_numpy(dtype=float)
    x = data["dlog_productivity"].to_numpy(dtype=float)

    scale = max(float(np.var(y)), 1e-6)

    def objective(log_variances: np.ndarray) -> float:
        obs_var = float(np.exp(log_variances[0]))
        state_var = float(np.exp(log_variances[1]))
        llf, _, _ = _kalman_filter(
            y,
            x,
            observation_variance=obs_var,
            state_variance=state_var,
            initial_state_variance=initial_state_variance,
        )
        return -llf

    initial = np.log(np.array([scale, scale * 0.01], dtype=float))
    optimum = minimize(objective, initial, method="L-BFGS-B", bounds=[(-20, 5), (-20, 2)])
    obs_var = float(np.exp(optimum.x[0]))
    state_var = float(np.exp(optimum.x[1]))
    llf, states, covariances = _kalman_filter(
        y,
        x,
        observation_variance=obs_var,
        state_variance=state_var,
        initial_state_variance=initial_state_variance,
    )
    slope_var = np.maximum(covariances[:, 1, 1], 0.0)
    return TimeVaryingElasticityResult(
        year=data["year"].to_numpy(dtype=int),
        intercept=states[:, 0],
        elasticity=states[:, 1],
        elasticity_std_error=np.sqrt(slope_var),
        observation_variance=obs_var,
        state_variance=state_var,
        log_likelihood=llf,
        converged=bool(optimum.success),
    )


@dataclass(frozen=True)
class TimeVaryingElasticityBand:
    """Bootstrap band around the filtered elasticity path."""

    year: np.ndarray
    estimate: np.ndarray
    lower_95: np.ndarray
    upper_95: np.ndarray
    replications: int
    block_length: int
    seed: int


def bootstrap_time_varying_elasticity_bands(
    frame: pd.DataFrame,
    *,
    initial_state_variance: float = 100.0,
    replications: int = 199,
    block_length: int = DEFAULT_BLOCK_LENGTH,
    seed: int = 20260824,
) -> TimeVaryingElasticityBand:
    """Block-bootstrap percentile bands for the time-varying elasticity path.

    The filtered standard errors from the Kalman recursion condition on the estimated variance
    parameters and therefore ignore the uncertainty in estimating them. Re-estimating the whole
    model on each block resample propagates that uncertainty into the band, which matters here
    because the state variance is what governs how much the elasticity is allowed to move.

    Bands are pointwise, not simultaneous: they do not license a statement about the path as a
    whole, such as a claimed decline between two particular years.
    """
    if replications < 99:
        raise ValueError("replications must be at least 99 for a usable percentile band")

    point = fit_time_varying_elasticity(frame, initial_state_variance=initial_state_variance)
    data = add_log_growth_columns(frame)
    horizon = len(point.elasticity)
    rng = np.random.default_rng(seed)

    draws: list[np.ndarray] = []
    for _ in range(replications):
        resampled = resample_level_frame(data, block_length=block_length, rng=rng)
        try:
            fitted = fit_time_varying_elasticity(
                resampled, initial_state_variance=initial_state_variance
            )
        except (ValueError, np.linalg.LinAlgError):
            continue
        if len(fitted.elasticity) == horizon:
            draws.append(fitted.elasticity)

    if not draws:
        raise ValueError("Every bootstrap replication failed; the sample is too short.")

    matrix = np.vstack(draws)
    lower, upper = percentile_band(matrix)
    return TimeVaryingElasticityBand(
        year=point.year,
        estimate=point.elasticity,
        lower_95=lower,
        upper_95=upper,
        replications=len(draws),
        block_length=int(block_length),
        seed=int(seed),
    )
