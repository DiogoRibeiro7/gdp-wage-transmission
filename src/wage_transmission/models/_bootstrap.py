"""Shared block-bootstrap machinery for dynamic-model uncertainty bands.

Annual wage and productivity growth are serially dependent, so an i.i.d. resample would
understate uncertainty in dynamic models. These helpers implement a circular moving-block
bootstrap over the *joint* growth pairs, which preserves both the contemporaneous
wage-productivity relationship and short-run persistence within a block.

Resampled growth is re-integrated into a level frame so that the resample flows back through
the same validated entry points the point estimates use. Nothing here identifies a shock: the
bands describe sampling uncertainty, not causal uncertainty.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_BLOCK_LENGTH = 4


def moving_block_indices(nobs: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    """Indices for one circular moving-block resample of length ``nobs``."""
    if nobs < 1:
        raise ValueError("nobs must be positive")
    if not 1 <= block_length <= nobs:
        raise ValueError(f"block_length must lie in [1, {nobs}]; got {block_length}")
    n_blocks = int(np.ceil(nobs / block_length))
    starts = rng.integers(0, nobs, size=n_blocks)
    offsets = np.arange(block_length)
    indices = ((starts[:, None] + offsets[None, :]) % nobs).ravel()
    return indices[:nobs].astype(int)


def resample_level_frame(
    data: pd.DataFrame,
    *,
    block_length: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Resample joint growth pairs and re-integrate them into a level frame.

    ``data`` must already carry the log-growth columns. The first observed levels anchor the
    reconstruction, so the resampled series has the same units and starting point as the
    original and can be fed straight back into an estimator.
    """
    required = {"year", "real_wage", "productivity", "dlog_wage", "dlog_productivity"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Resampling requires log-growth columns; missing: {sorted(missing)}")

    growth = data.dropna(subset=["dlog_wage", "dlog_productivity"])
    wage_growth = growth["dlog_wage"].to_numpy(dtype=float)
    productivity_growth = growth["dlog_productivity"].to_numpy(dtype=float)
    indices = moving_block_indices(len(wage_growth), block_length, rng)

    cumulative_wage = np.concatenate([[0.0], np.cumsum(wage_growth[indices])])
    cumulative_productivity = np.concatenate([[0.0], np.cumsum(productivity_growth[indices])])
    base_wage = float(data["real_wage"].iloc[0])
    base_productivity = float(data["productivity"].iloc[0])
    years = data["year"].to_numpy(dtype=int)[: len(cumulative_wage)]

    return pd.DataFrame(
        {
            "year": years,
            "real_wage": base_wage * np.exp(cumulative_wage),
            "productivity": base_productivity * np.exp(cumulative_productivity),
        }
    )


def percentile_band(draws: np.ndarray, *, alpha: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """Lower and upper percentile bands across bootstrap replications (axis 0)."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie strictly between 0 and 1")
    if draws.size == 0:
        raise ValueError("No bootstrap replications survived; cannot form a band.")
    lower = np.quantile(draws, alpha / 2.0, axis=0)
    upper = np.quantile(draws, 1.0 - alpha / 2.0, axis=0)
    return np.atleast_1d(lower), np.atleast_1d(upper)
