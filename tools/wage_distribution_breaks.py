"""Structural-break analysis for Portugal wage-distribution ratios.

This module supports the repository's second paper. It deliberately lives outside the
pre-registered ``src/wage_transmission`` package so Paper 1's specification lock is unchanged.

The analysis is descriptive and post-hoc: the wage-distribution data were inspected before this
protocol was frozen. The code therefore distinguishes data-selected break dates from historically
specified 2008/2009 candidate breaks and does not make causal claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

METRICS: dict[str, str] = {
    "d10_d1_ratio": "D10 / D1",
    "d9_d1_ratio": "D9 / D1",
    "d10_d5_ratio": "D10 / D5",
    "mean_median_ratio": "Mean / median",
}
HISTORICAL_BREAKS: tuple[int, ...] = (2008, 2009)
PUBLICATION_ELIGIBLE = False


@dataclass(frozen=True)
class BreakSearchResult:
    """Result of a one-kink endogenous break search for one log-ratio series."""

    metric: str
    label: str
    start_year: int
    end_year: int
    n: int
    selected_break_year: int
    break_ci_low: int
    break_ci_median: int
    break_ci_high: int
    pre_break_slope_log_points: float
    post_break_slope_log_points: float
    slope_change_log_points: float
    pre_break_slope_pct_approx: float
    post_break_slope_pct_approx: float
    sup_f: float
    bootstrap_p_value: float
    bic_linear: float
    bic_segmented: float
    delta_bic_segmented_minus_linear: float
    bootstrap_repetitions: int
    bootstrap_block_length: int
    publication_eligible: bool


@dataclass(frozen=True)
class HistoricalBreakResult:
    """Continuous segmented-trend fit at a historically specified break year."""

    metric: str
    label: str
    break_year: int
    pre_break_slope_log_points: float
    post_break_slope_log_points: float
    slope_change_log_points: float
    pre_break_slope_pct_approx: float
    post_break_slope_pct_approx: float
    slope_change_hac_se: float
    slope_change_hac_p_value: float
    f_vs_linear: float
    bic_segmented: float
    publication_eligible: bool


def sha256_file(path: Path) -> str:
    """Return SHA-256 for *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Validate the annual ratio panel used by Paper 2."""
    required = {"year", *METRICS}
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"Wage-distribution panel is missing columns: {sorted(missing)}")
    data = panel.loc[:, ["year", *METRICS]].copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    if data["year"].isna().any() or not np.all(np.equal(np.mod(data["year"], 1), 0)):
        raise ValueError("Years must be finite integers.")
    data["year"] = data["year"].astype(int)
    data = data.sort_values("year").reset_index(drop=True)
    if data["year"].duplicated().any():
        raise ValueError("Years must be unique.")
    expected = np.arange(int(data["year"].min()), int(data["year"].max()) + 1)
    if not np.array_equal(data["year"].to_numpy(), expected):
        raise ValueError("Paper 2 requires a contiguous annual panel.")
    for metric in METRICS:
        data[metric] = pd.to_numeric(data[metric], errors="coerce")
    values = data[list(METRICS)].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError("Distribution ratios must be finite and strictly positive.")
    return data


def _design(years: np.ndarray, break_year: int | None = None) -> np.ndarray:
    """Return linear or continuous segmented-trend design matrix."""
    t = years.astype(float) - float(years[0])
    columns: list[np.ndarray] = [np.ones(len(years), dtype=float), t]
    if break_year is not None:
        columns.append(np.maximum(0.0, years.astype(float) - float(break_year)))
    return np.column_stack(columns)


def _ols_rss(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """Fit OLS with NumPy and return beta, residuals, RSS and fitted values."""
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    fitted = x @ beta
    residuals = y - fitted
    rss = float(residuals @ residuals)
    return beta, residuals, rss, fitted


def _bic(rss: float, n: int, k: int) -> float:
    """Gaussian OLS BIC up to constants common to compared models."""
    if rss <= 0.0:
        raise ValueError("RSS must be strictly positive.")
    return float(n * np.log(rss / n) + k * np.log(n))


def _candidate_years(years: np.ndarray, min_segment: int) -> np.ndarray:
    """Return break years leaving at least ``min_segment`` observations on each side."""
    if min_segment < 3:
        raise ValueError("min_segment must be at least 3.")
    if len(years) < 2 * min_segment + 1:
        raise ValueError("Sample is too short for the requested minimum segment length.")
    return years[min_segment - 1 : -(min_segment - 1)]


def _search_break(
    y: np.ndarray,
    years: np.ndarray,
    min_segment: int,
) -> tuple[int, float, np.ndarray, np.ndarray, float, float, np.ndarray, np.ndarray]:
    """Search a continuous one-kink model and return the minimum-RSS break."""
    n = len(y)
    linear_x = _design(years)
    _, linear_residuals, linear_rss, linear_fitted = _ols_rss(y, linear_x)
    best: tuple[int, float, np.ndarray, np.ndarray, float, np.ndarray] | None = None
    sup_f = -np.inf
    for year in _candidate_years(years, min_segment):
        x = _design(years, int(year))
        beta, residuals, rss, fitted = _ols_rss(y, x)
        f_value = float((linear_rss - rss) / (rss / (n - x.shape[1])))
        sup_f = max(sup_f, f_value)
        if best is None or rss < best[1]:
            best = (int(year), rss, beta, residuals, f_value, fitted)
    if best is None:
        raise RuntimeError("Break search produced no candidate model.")
    year, rss, beta, residuals, _, fitted = best
    return year, sup_f, beta, residuals, rss, linear_rss, fitted, linear_fitted


def _circular_block_sample(
    residuals: np.ndarray,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Circular moving-block resample preserving short-range residual dependence."""
    n = len(residuals)
    if not 1 <= block_length <= n:
        raise ValueError("block_length must lie between 1 and the sample size.")
    n_blocks = int(np.ceil(n / block_length))
    starts = rng.integers(0, n, size=n_blocks)
    values: list[float] = []
    offsets = np.arange(block_length)
    for start in starts:
        values.extend(residuals[(int(start) + offsets) % n].tolist())
    return np.asarray(values[:n], dtype=float)


def _bootstrap_sup_f_p_value(
    y: np.ndarray,
    years: np.ndarray,
    observed_sup_f: float,
    min_segment: int,
    repetitions: int,
    block_length: int,
    rng: np.random.Generator,
) -> float:
    """Residual circular-block bootstrap p-value for the maximum break-search F statistic."""
    x = _design(years)
    _, residuals, _, fitted = _ols_rss(y, x)
    centered = residuals - float(residuals.mean())
    exceedances = 0
    for _ in range(repetitions):
        y_star = fitted + _circular_block_sample(centered, block_length, rng)
        _, sup_f_star, *_ = _search_break(y_star, years, min_segment)
        if sup_f_star >= observed_sup_f:
            exceedances += 1
    return float((exceedances + 1) / (repetitions + 1))


def _bootstrap_break_interval(
    y: np.ndarray,
    years: np.ndarray,
    selected_break: int,
    min_segment: int,
    repetitions: int,
    block_length: int,
    rng: np.random.Generator,
) -> tuple[int, int, int]:
    """Percentile bootstrap interval for the selected break year under the segmented model."""
    x = _design(years, selected_break)
    _, residuals, _, fitted = _ols_rss(y, x)
    centered = residuals - float(residuals.mean())
    dates = np.empty(repetitions, dtype=int)
    for index in range(repetitions):
        y_star = fitted + _circular_block_sample(centered, block_length, rng)
        break_year, *_ = _search_break(y_star, years, min_segment)
        dates[index] = break_year
    low, median, high = np.quantile(dates.astype(float), [0.025, 0.5, 0.975])
    return int(round(low)), int(round(median)), int(round(high))


def _approx_pct(log_slope: float) -> float:
    """Convert a log-point annual slope to its exact percentage annual change."""
    return float(100.0 * np.expm1(log_slope))


def endogenous_break(
    panel: pd.DataFrame,
    metric: str,
    *,
    min_segment: int = 5,
    bootstrap_repetitions: int = 5000,
    block_length: int = 3,
    seed: int = 20260823,
) -> BreakSearchResult:
    """Estimate one continuous slope break and small-sample bootstrap diagnostics."""
    data = _validate_panel(panel)
    if metric not in METRICS:
        raise ValueError(f"Unknown metric {metric!r}.")
    years = data["year"].to_numpy(dtype=int)
    y = np.log(data[metric].to_numpy(dtype=float))
    selected, sup_f, beta, _, segmented_rss, linear_rss, _, _ = _search_break(
        y, years, min_segment
    )
    rng_p = np.random.default_rng(seed)
    p_value = _bootstrap_sup_f_p_value(
        y,
        years,
        sup_f,
        min_segment,
        bootstrap_repetitions,
        block_length,
        rng_p,
    )
    rng_ci = np.random.default_rng(seed + 1)
    ci_low, ci_median, ci_high = _bootstrap_break_interval(
        y,
        years,
        selected,
        min_segment,
        bootstrap_repetitions,
        block_length,
        rng_ci,
    )
    pre_slope = float(beta[1])
    slope_change = float(beta[2])
    post_slope = pre_slope + slope_change
    n = len(data)
    linear_bic = _bic(linear_rss, n, 2)
    segmented_bic = _bic(segmented_rss, n, 3)
    return BreakSearchResult(
        metric=metric,
        label=METRICS[metric],
        start_year=int(years[0]),
        end_year=int(years[-1]),
        n=n,
        selected_break_year=selected,
        break_ci_low=ci_low,
        break_ci_median=ci_median,
        break_ci_high=ci_high,
        pre_break_slope_log_points=pre_slope,
        post_break_slope_log_points=post_slope,
        slope_change_log_points=slope_change,
        pre_break_slope_pct_approx=_approx_pct(pre_slope),
        post_break_slope_pct_approx=_approx_pct(post_slope),
        sup_f=sup_f,
        bootstrap_p_value=p_value,
        bic_linear=linear_bic,
        bic_segmented=segmented_bic,
        delta_bic_segmented_minus_linear=segmented_bic - linear_bic,
        bootstrap_repetitions=bootstrap_repetitions,
        bootstrap_block_length=block_length,
        publication_eligible=PUBLICATION_ELIGIBLE,
    )


def historical_break(panel: pd.DataFrame, metric: str, break_year: int) -> HistoricalBreakResult:
    """Fit a historically specified continuous break with HAC uncertainty on slope change."""
    data = _validate_panel(panel)
    if metric not in METRICS:
        raise ValueError(f"Unknown metric {metric!r}.")
    years = data["year"].to_numpy(dtype=int)
    if break_year not in years:
        raise ValueError(f"Break year {break_year} is outside the sample.")
    y = np.log(data[metric].to_numpy(dtype=float))
    linear_x = _design(years)
    _, _, linear_rss, _ = _ols_rss(y, linear_x)
    x = _design(years, break_year)
    model = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
    residuals = np.asarray(model.resid, dtype=float)
    rss = float(residuals @ residuals)
    n = len(data)
    f_value = float((linear_rss - rss) / (rss / (n - x.shape[1])))
    pre_slope = float(model.params[1])
    slope_change = float(model.params[2])
    post_slope = pre_slope + slope_change
    return HistoricalBreakResult(
        metric=metric,
        label=METRICS[metric],
        break_year=break_year,
        pre_break_slope_log_points=pre_slope,
        post_break_slope_log_points=post_slope,
        slope_change_log_points=slope_change,
        pre_break_slope_pct_approx=_approx_pct(pre_slope),
        post_break_slope_pct_approx=_approx_pct(post_slope),
        slope_change_hac_se=float(model.bse[2]),
        slope_change_hac_p_value=float(model.pvalues[2]),
        f_vs_linear=f_value,
        bic_segmented=_bic(rss, n, x.shape[1]),
        publication_eligible=PUBLICATION_ELIGIBLE,
    )


def _plot_breaks(panel: pd.DataFrame, searches: list[BreakSearchResult], output: Path) -> None:
    """Plot observed log ratios with selected continuous segmented trends."""
    data = _validate_panel(panel)
    years = data["year"].to_numpy(dtype=int)
    fig, axes = plt.subplots(2, 2, figsize=(10.0, 7.0), sharex=True)
    for axis, result in zip(axes.flat, searches, strict=True):
        y = np.log(data[result.metric].to_numpy(dtype=float))
        x = _design(years, result.selected_break_year)
        beta, *_ = np.linalg.lstsq(x, y, rcond=None)
        fitted = np.exp(x @ beta)
        axis.plot(years, data[result.metric], marker="o", label="Observed")
        axis.plot(years, fitted, label="Segmented trend")
        axis.axvline(result.selected_break_year, linestyle="--", linewidth=1.0)
        axis.set_title(f"{result.label}: break {result.selected_break_year}")
        axis.set_ylabel("Ratio")
        axis.legend(fontsize=8)
    for axis in axes[-1, :]:
        axis.set_xlabel("Year")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _latex_escape(value: str) -> str:
    """Escape the small subset of LaTeX-special characters used in generated labels."""
    return value.replace("_", r"\_").replace("%", r"\%")


def write_paper_fragments(
    searches: list[BreakSearchResult],
    historical: list[HistoricalBreakResult],
    paper_dir: Path,
) -> None:
    """Write Paper 2 result fragments directly from machine-readable model objects."""
    generated = paper_dir / "generated"
    generated.mkdir(parents=True, exist_ok=True)

    main = {item.metric: item for item in searches}
    d10d1 = main["d10_d1_ratio"]
    d10d5 = main["d10_d5_ratio"]
    meanmed = main["mean_median_ratio"]
    results = (
        "The endogenous one-kink search does not identify a unique common break across "
        "distribution margins. For $D10/D1$, the selected break is "
        f"{d10d1.selected_break_year} (bootstrap 95\\% interval "
        f"{d10d1.break_ci_low}--{d10d1.break_ci_high}), after which the fitted annual trend is "
        f"{d10d1.post_break_slope_pct_approx:.2f}\\%. "
        f"For $D10/D5$ the selected break is {d10d5.selected_break_year}, while the "
        f"mean/median ratio selects {meanmed.selected_break_year}. This ordering is consistent "
        "with staggered compression rather than a single common 2008 breakpoint. "
        "Historically specified 2008 and 2009 models are reported separately and do not receive "
        "the status of data-selected break dates.\n"
    )
    (generated / "results_summary.tex").write_text(results)

    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Endogenous continuous segmented-trend break search}",
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        "Measure & Break & 95\\% interval & Pre slope (\\%) & Post slope (\\%) & Bootstrap $p$ " + r"\\",
        r"\midrule",
    ]
    for item in searches:
        lines.append(
            f"{_latex_escape(item.label)} & {item.selected_break_year} & "
            f"{item.break_ci_low}--{item.break_ci_high} & "
            f"{item.pre_break_slope_pct_approx:.2f} & {item.post_break_slope_pct_approx:.2f} & "
            f"{item.bootstrap_p_value:.4f} " + r"\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    (generated / "table_endogenous_breaks.tex").write_text("\n".join(lines))

    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Historically specified 2008 and 2009 segmented trends}",
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        "Measure & Break & Pre slope (\\%) & Post slope (\\%) & HAC $p$ for slope change " + r"\\",
        r"\midrule",
    ]
    for item in historical:
        lines.append(
            f"{_latex_escape(item.label)} & {item.break_year} & "
            f"{item.pre_break_slope_pct_approx:.2f} & {item.post_break_slope_pct_approx:.2f} & "
            f"{item.slope_change_hac_p_value:.4g} " + r"\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    (generated / "table_historical_breaks.tex").write_text("\n".join(lines))


def run_analysis(
    input_path: Path,
    output_dir: Path,
    *,
    paper_dir: Path | None = None,
    min_segment: int = 5,
    bootstrap_repetitions: int = 5000,
    block_length: int = 3,
    seed: int = 20260823,
) -> None:
    """Run Paper 2 break search and write reproducible machine-readable outputs."""
    panel = pd.read_csv(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    searches = [
        endogenous_break(
            panel,
            metric,
            min_segment=min_segment,
            bootstrap_repetitions=bootstrap_repetitions,
            block_length=block_length,
            seed=seed + index * 100,
        )
        for index, metric in enumerate(METRICS)
    ]
    historical = [
        historical_break(panel, metric, break_year)
        for metric in METRICS
        for break_year in HISTORICAL_BREAKS
    ]

    search_frame = pd.DataFrame(asdict(item) for item in searches)
    historical_frame = pd.DataFrame(asdict(item) for item in historical)
    search_path = output_dir / "endogenous_break_search.csv"
    historical_path = output_dir / "historical_2008_2009_breaks.csv"
    search_frame.to_csv(search_path, index=False)
    historical_frame.to_csv(historical_path, index=False)

    summary = {
        "schema_version": 1,
        "analysis_status": "post_hoc_exploratory_locked_for_reproduction",
        "publication_eligible": False,
        "causal_claims_authorized": False,
        "sample": {"start_year": 2002, "end_year": 2024, "n": 23},
        "model": "continuous one-kink segmented trend in log distribution ratios",
        "candidate_break_rule": f"at least {min_segment} observations in each segment",
        "historical_candidate_breaks": list(HISTORICAL_BREAKS),
        "bootstrap": {
            "method": "circular moving-block residual bootstrap",
            "repetitions": bootstrap_repetitions,
            "block_length": block_length,
            "seed": seed,
        },
        "endogenous_breaks": [asdict(item) for item in searches],
        "historical_breaks": [asdict(item) for item in historical],
        "interpretation": (
            "Break dates differ across dispersion margins; the evidence is consistent with "
            "staggered wage compression rather than a unique common break in 2008."
        ),
    }
    summary_path = output_dir / "break_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    figure_path = output_dir / "segmented_breaks.png"
    _plot_breaks(panel, searches, figure_path)

    provenance = {
        "schema_version": 1,
        "publication_eligible": False,
        "reason": (
            "Paper 2 analysis was specified after inspection of the exploratory wage-distribution "
            "series and its underlying official tables are not yet an untouched source freeze."
        ),
        "input": {"path": str(input_path), "sha256": sha256_file(input_path)},
        "outputs": {
            path.name: sha256_file(path)
            for path in (search_path, historical_path, summary_path, figure_path)
        },
    }
    (output_dir / "BREAK_ANALYSIS_PROVENANCE.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    )
    if paper_dir is not None:
        write_paper_fragments(searches, historical, paper_dir)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-segment", type=int, default=5)
    parser.add_argument("--bootstrap-repetitions", type=int, default=5000)
    parser.add_argument("--block-length", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--paper-dir", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = _parser().parse_args(argv)
    run_analysis(
        args.input,
        args.output_dir,
        min_segment=args.min_segment,
        bootstrap_repetitions=args.bootstrap_repetitions,
        block_length=args.block_length,
        seed=args.seed,
        paper_dir=args.paper_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
