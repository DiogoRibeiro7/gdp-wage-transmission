"""Formal single-break inference for the wage-transmission regression.

This module is deliberately separate from :mod:`wage_transmission.models.structural_breaks`,
which *selects* a number of regimes by BIC. The question here is inferential rather than
selective: is there evidence of a break at all, and how precisely is its date located?

Two choices are worth stating explicitly.

The sup-F statistic is the largest Chow F over candidate break dates after trimming the sample
ends. Its null distribution is non-standard and depends on the trimming fraction, so this
module does not rely on tabulated asymptotic critical values. The p-value comes instead from a
wild bootstrap under the no-break null, which keeps the procedure honest about
heteroskedasticity in annual growth rates and about the search over candidate dates.

The break-date interval is the percentile interval of the bootstrap arg-max under the
*estimated* break model. It describes how stably the date is located under resampling. It is
not a causal statement: a well-located break says when the relationship changed, never why.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from wage_transmission.validation import add_log_growth_columns

_RESTRICTED_PARAMS = 2
_UNRESTRICTED_PARAMS = 4


@dataclass(frozen=True)
class BreakTestResult:
    """Evidence for, and location of, a single break in the transmission elasticity."""

    break_year: int
    sup_f: float
    p_value: float
    break_year_lower: int
    break_year_upper: int
    pre_break_elasticity: float
    post_break_elasticity: float
    elasticity_change: float
    nobs: int
    trim: float
    n_candidates: int
    bootstrap_replications: int
    seed: int
    interpretation: str


def _ols_rss(design: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, float]:
    """Least-squares coefficients and residual sum of squares."""
    beta, *_ = np.linalg.lstsq(design, target, rcond=None)
    residual = target - design @ beta
    return beta, float(residual @ residual)


def _restricted_design(x: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), x])


def _unrestricted_design(x: np.ndarray, split: int) -> np.ndarray:
    indicator = np.zeros(len(x), dtype=float)
    indicator[split:] = 1.0
    return np.column_stack([np.ones(len(x)), x, indicator, indicator * x])


def _chow_f(x: np.ndarray, y: np.ndarray, split: int, restricted_rss: float) -> float:
    """Chow F for a break in both the intercept and the slope at ``split``."""
    _, unrestricted_rss = _ols_rss(_unrestricted_design(x, split), y)
    denominator = unrestricted_rss / (len(y) - _UNRESTRICTED_PARAMS)
    if denominator <= 0.0:
        return 0.0
    numerator = (restricted_rss - unrestricted_rss) / _RESTRICTED_PARAMS
    return float(numerator / denominator)


def _candidate_splits(nobs: int, trim: float) -> tuple[int, ...]:
    """Interior break points leaving at least ``trim`` of the sample on each side."""
    margin = max(int(np.ceil(trim * nobs)), _UNRESTRICTED_PARAMS)
    if nobs - 2 * margin < 1:
        raise ValueError(
            f"A trim of {trim:.2f} leaves no candidate break dates for {nobs} observations."
        )
    return tuple(range(margin, nobs - margin + 1))


def _sup_f(x: np.ndarray, y: np.ndarray, candidates: tuple[int, ...]) -> tuple[int, float]:
    """Return the arg-max split and the sup-F statistic over the candidate dates."""
    _, restricted_rss = _ols_rss(_restricted_design(x), y)
    best_split = candidates[0]
    best_stat = -np.inf
    for split in candidates:
        stat = _chow_f(x, y, split, restricted_rss)
        if stat > best_stat:
            best_stat, best_split = stat, split
    return best_split, float(best_stat)


def _wild_resample(
    fitted: np.ndarray, residuals: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Rademacher wild bootstrap, which preserves heteroskedasticity in the residuals."""
    signs = rng.choice(np.array([-1.0, 1.0]), size=len(residuals))
    resampled: np.ndarray = fitted + residuals * signs
    return resampled


def single_break_test(
    frame: pd.DataFrame,
    *,
    trim: float = 0.15,
    bootstrap_replications: int = 999,
    seed: int = 20260824,
) -> BreakTestResult:
    """Test for a single break in the growth-rate transmission regression.

    The regression is ``dlog_wage ~ dlog_productivity`` and the break is allowed in both the
    intercept and the slope. The p-value is a wild-bootstrap tail probability under the
    no-break null; it already accounts for the search over candidate dates, so it needs no
    further multiplicity correction.

    A rejection identifies a date at which the wage-productivity relationship changed. It does
    not identify a cause, and the estimated date must not be replaced by a historically
    convenient one.
    """
    if not 0.0 < trim < 0.5:
        raise ValueError("trim must lie strictly between 0 and 0.5")
    if bootstrap_replications < 99:
        raise ValueError("bootstrap_replications must be at least 99 for a usable p-value")

    data = add_log_growth_columns(frame).dropna(subset=["dlog_wage", "dlog_productivity"])
    y = data["dlog_wage"].to_numpy(dtype=float)
    x = data["dlog_productivity"].to_numpy(dtype=float)
    years = data["year"].to_numpy(dtype=int)
    nobs = len(y)
    if nobs < 4 * _UNRESTRICTED_PARAMS:
        raise ValueError(
            f"Break inference needs at least {4 * _UNRESTRICTED_PARAMS} growth observations; "
            f"got {nobs}."
        )

    candidates = _candidate_splits(nobs, trim)
    split, sup_f = _sup_f(x, y, candidates)

    # Null distribution: resample around the no-break fit and re-run the entire search.
    restricted_design = _restricted_design(x)
    restricted_beta, _ = _ols_rss(restricted_design, y)
    restricted_fitted = restricted_design @ restricted_beta
    restricted_residuals = y - restricted_fitted
    rng = np.random.default_rng(seed)
    exceedances = 0
    for _ in range(bootstrap_replications):
        y_star = _wild_resample(restricted_fitted, restricted_residuals, rng)
        _, stat = _sup_f(x, y_star, candidates)
        if stat >= sup_f:
            exceedances += 1
    p_value = (exceedances + 1) / (bootstrap_replications + 1)

    # Date interval: resample around the fitted break model and re-locate the date.
    unrestricted_design = _unrestricted_design(x, split)
    unrestricted_beta, _ = _ols_rss(unrestricted_design, y)
    unrestricted_fitted = unrestricted_design @ unrestricted_beta
    unrestricted_residuals = y - unrestricted_fitted
    rng_ci = np.random.default_rng(seed + 1)
    located = np.empty(bootstrap_replications, dtype=int)
    for index in range(bootstrap_replications):
        y_star = _wild_resample(unrestricted_fitted, unrestricted_residuals, rng_ci)
        candidate, _ = _sup_f(x, y_star, candidates)
        located[index] = years[candidate]
    lower, upper = np.quantile(located.astype(float), [0.025, 0.975])

    pre_elasticity = float(unrestricted_beta[1])
    post_elasticity = float(unrestricted_beta[1] + unrestricted_beta[3])

    if p_value > 0.10:
        interpretation = "no_break_detected"
    elif int(np.rint(upper)) - int(np.rint(lower)) > max(4, nobs // 4):
        interpretation = "break_detected_date_poorly_located"
    else:
        interpretation = "break_detected"

    return BreakTestResult(
        break_year=int(years[split]),
        sup_f=sup_f,
        p_value=float(p_value),
        break_year_lower=int(np.rint(lower)),
        break_year_upper=int(np.rint(upper)),
        pre_break_elasticity=pre_elasticity,
        post_break_elasticity=post_elasticity,
        elasticity_change=post_elasticity - pre_elasticity,
        nobs=nobs,
        trim=float(trim),
        n_candidates=len(candidates),
        bootstrap_replications=int(bootstrap_replications),
        seed=int(seed),
        interpretation=interpretation,
    )
