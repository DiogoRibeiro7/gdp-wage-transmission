"""Endogenous least-squares structural-break search for wage transmission."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
import pandas as pd

from wage_transmission.validation import add_log_growth_columns


@dataclass(frozen=True)
class BreakSegment:
    """One estimated transmission regime."""

    start_year: int
    end_year: int
    intercept: float
    elasticity: float
    rss: float
    nobs: int


@dataclass(frozen=True)
class StructuralBreakResult:
    """BIC-selected piecewise linear transmission regimes."""

    break_years: tuple[int, ...]
    segments: tuple[BreakSegment, ...]
    bic: float
    n_breaks: int


def _segment_fit(x: np.ndarray, y: np.ndarray, start: int, stop: int) -> tuple[float, float, float]:
    design = np.column_stack([np.ones(stop - start), x[start:stop]])
    target = y[start:stop]
    beta, *_ = np.linalg.lstsq(design, target, rcond=None)
    residual = target - design @ beta
    rss = float(residual @ residual)
    return float(beta[0]), float(beta[1]), rss


def fit_structural_breaks(
    frame: pd.DataFrame,
    *,
    max_breaks: int = 3,
    min_segment: int = 8,
) -> StructuralBreakResult:
    """Estimate unknown break dates in the wage-growth/productivity-growth relation.

    Dynamic programming minimises total segment RSS. The number of segments is chosen by BIC.
    This is a transparent least-squares change-point estimator; it is not labelled Bai–Perron.
    """
    if max_breaks < 0:
        raise ValueError("max_breaks must be non-negative")
    if min_segment < 4:
        raise ValueError("min_segment must be at least 4")

    data = add_log_growth_columns(frame).dropna(subset=["dlog_wage", "dlog_productivity"])
    years = data["year"].to_numpy(dtype=int)
    x = data["dlog_productivity"].to_numpy(dtype=float)
    y = data["dlog_wage"].to_numpy(dtype=float)
    n = len(data)
    max_segments = min(max_breaks + 1, n // min_segment)
    if max_segments < 1:
        raise ValueError("Too few observations for structural-break estimation.")

    rss_cache = np.full((n + 1, n + 1), np.inf)
    params: dict[tuple[int, int], tuple[float, float, float]] = {}
    for start in range(n):
        for stop in range(start + min_segment, n + 1):
            fit = _segment_fit(x, y, start, stop)
            params[(start, stop)] = fit
            rss_cache[start, stop] = fit[2]

    # dp[s, j] = minimum RSS for s segments covering observations [0, j).
    dp = np.full((max_segments + 1, n + 1), np.inf)
    prev = np.full((max_segments + 1, n + 1), -1, dtype=int)
    dp[0, 0] = 0.0
    for segments in range(1, max_segments + 1):
        min_stop = segments * min_segment
        for stop in range(min_stop, n + 1):
            start_min = (segments - 1) * min_segment
            start_max = stop - min_segment
            for start in range(start_min, start_max + 1):
                candidate = dp[segments - 1, start] + rss_cache[start, stop]
                if candidate < dp[segments, stop]:
                    dp[segments, stop] = candidate
                    prev[segments, stop] = start

    best: tuple[float, int] | None = None
    for segments in range(1, max_segments + 1):
        rss = float(dp[segments, n])
        if not np.isfinite(rss) or rss <= 0:
            continue
        parameter_count = 2 * segments
        bic = n * np.log(rss / n) + parameter_count * np.log(n)
        if best is None or bic < best[0]:
            best = (float(bic), segments)
    if best is None:
        raise ValueError("Structural-break optimisation failed.")

    bic, segments = best
    boundaries = [n]
    stop = n
    for s in range(segments, 0, -1):
        start = int(prev[s, stop])
        if start < 0:
            if s == 1 and stop == n:
                start = 0
            else:
                raise RuntimeError("Invalid dynamic-programming backtrack state.")
        boundaries.append(start)
        stop = start
    boundaries = sorted(boundaries)

    output_segments: list[BreakSegment] = []
    for start, stop in pairwise(boundaries):
        intercept, elasticity, rss = params[(start, stop)]
        output_segments.append(
            BreakSegment(
                start_year=int(years[start]),
                end_year=int(years[stop - 1]),
                intercept=intercept,
                elasticity=elasticity,
                rss=rss,
                nobs=stop - start,
            )
        )
    break_years = tuple(segment.start_year for segment in output_segments[1:])
    return StructuralBreakResult(
        break_years=break_years,
        segments=tuple(output_segments),
        bic=bic,
        n_breaks=max(0, segments - 1),
    )
