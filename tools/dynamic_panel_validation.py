"""Monte Carlo validation of the dynamic-panel estimator and of its bootstrap interval.

The manuscript claims two things about the estimator that cannot be checked from the estimates
themselves: that the bias correction removes most of the dynamic fixed-effects bias, and that the
percentile interval it reports has usable coverage despite the moving-block bootstrap visibly
displacing the resampling distribution. Both claims need evidence, not assertion.

This tool supplies it. It sits outside ``src/wage_transmission`` and estimates nothing itself: it
generates panels with known parameters and runs the locked estimator on them, so the numbers it
reports describe the estimator that produced the paper's results and no other.

**The data-generating process is the estimator's own model**, which is the point and also the
limitation. Panels are drawn as::

    dlog p_it = mu_p + phi_t + v_it
    dlog w_it = a_i + l_t + sum_j beta_j dlog p_{i,t-j} + gamma dlog w_{i,t-1} + e_it
    e_it = c_i f_t + d_i z_it,   f_t, z_it ~ N(0, 1)

with the dimensions of the estimation sample -- thirteen countries, thirty-one annual levels, one
country a year short -- and moments calibrated to the observed primary-driver panel.

The error design deserves a note, because an earlier version of this study got it wrong. Drawing
``e_it = sqrt(rho) u_t + sqrt(1 - rho) z_it`` with ``u_t`` common to every country does *not* give
the estimator cross-country dependence to contend with: the primary specification carries
unrestricted year effects, so ``l_t + sqrt(rho) u_t`` is another year effect and the time dummies
absorb ``u_t`` exactly. Such a design tests the estimator against no residual dependence at all.

The factor form above avoids that. The loadings ``c_i`` are heterogeneous and come from the leading
eigenvector of the cross-country covariance of the observed within residuals, and ``d_i`` from the
part of each country's residual variance the factor leaves. Decomposing ``c_i = cbar + ctilde_i``,
the ``cbar f_t`` component is absorbed by the year dummies and ``ctilde_i f_t`` is not, so what the
estimator faces is dependence the year effects cannot remove -- calibrated from the data rather than
assumed. ``dependence_diagnostic`` measures how much survives under each design.

A correctly specified DGP measures whether the estimator recovers what it targets. It says nothing
about behaviour under misspecification, and in particular nothing about the endogeneity the paper
declines to rule out: the driver path here is strictly exogenous by construction.

Usage::

    poetry run python tools/dynamic_panel_validation.py \\
        --output results/vintages/2026-08-25/publication_dossier/dynamic_panel_validation.json

The artefact belongs beside the dossier the paper reads, so the paper packet binds its digest
like any other input.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import beta

from wage_transmission.data.common import sha256_bytes
from wage_transmission.models.dynamic_panel import (
    BiasCorrector,
    GrowthPanel,
    WithinProjector,
    bootstrap_dynamic_panel,
    build_growth_panel,
    build_panel_design,
    cumulative_multiplier,
    fit_lsdv,
)
from wage_transmission.reporting import write_json
from wage_transmission.version import __version__

#: Country labels and the shape of the estimation sample.
N_COUNTRIES = 13
N_YEARS = 30
SHORT_COUNTRY = N_COUNTRIES - 1
#: Common-component share of the superseded equicorrelated design, kept for the diagnostic
#: that shows the year dummies absorb it.
EQUICORRELATED_SHARE = 0.35
COUNTRIES = tuple(f"C{index:02d}" for index in range(N_COUNTRIES))


@dataclass(frozen=True)
class Calibration:
    """Moments taken from the observed panel so the simulation is not free-floating."""

    driver_mean: float
    driver_sd: float
    driver_common_sd: float
    error_sd: float
    effect_sd: float
    year_effect_sd: float
    factor_loadings: tuple[float, ...]
    idiosyncratic_sd: tuple[float, ...]
    observed_mean_correlation: float
    observed_mean_absolute_correlation: float
    observed_leading_eigenvalue_share: float

    def to_dict(self) -> dict[str, Any]:
        """Return the calibration as plain values for the artefact."""
        loadings = np.asarray(self.factor_loadings, dtype=float)
        return {
            "driver_mean": self.driver_mean,
            "driver_sd": self.driver_sd,
            "driver_common_sd": self.driver_common_sd,
            "error_sd": self.error_sd,
            "country_effect_sd": self.effect_sd,
            "year_effect_sd": self.year_effect_sd,
            "factor_loadings": [float(value) for value in loadings],
            "factor_loading_mean": float(np.mean(loadings)),
            "factor_loading_sd": float(np.std(loadings, ddof=1)),
            "idiosyncratic_sd": [float(value) for value in self.idiosyncratic_sd],
            "observed_mean_correlation": self.observed_mean_correlation,
            "observed_mean_absolute_correlation": self.observed_mean_absolute_correlation,
            "observed_leading_eigenvalue_share": self.observed_leading_eigenvalue_share,
        }


def clopper_pearson(successes: int, trials: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact binomial interval for a coverage proportion.

    A coverage estimate is itself an estimate. Reporting it to three digits from a few hundred
    draws implies a precision the experiment does not have, so the interval travels with it.
    """
    if trials <= 0:
        return (float("nan"), float("nan"))
    lower = (
        0.0 if successes == 0 else float(beta.ppf(alpha / 2.0, successes, trials - successes + 1))
    )
    upper = (
        1.0
        if successes == trials
        else float(beta.ppf(1.0 - alpha / 2.0, successes + 1, trials - successes))
    )
    return (lower, upper)


def _binomial_se(successes: int, trials: int) -> float:
    """Monte Carlo standard error of a coverage proportion."""
    if trials <= 0:
        return float("nan")
    share = successes / trials
    return float(np.sqrt(share * (1.0 - share) / trials))


def _pairwise_covariance(matrix: np.ndarray) -> np.ndarray:
    """Cross-country covariance of an unbalanced country-by-period matrix.

    Each pair uses the periods on which both countries are observed. The panel loses one endpoint
    for one country, so this differs from a complete-case covariance only in that cell.
    """
    count = matrix.shape[0]
    covariance = np.zeros((count, count), dtype=float)
    for row in range(count):
        for column in range(row, count):
            both = np.isfinite(matrix[row]) & np.isfinite(matrix[column])
            if int(both.sum()) < 3:
                continue
            left = matrix[row, both]
            right = matrix[column, both]
            value = float(np.mean((left - left.mean()) * (right - right.mean())))
            value *= both.sum() / (both.sum() - 1)
            covariance[row, column] = value
            covariance[column, row] = value
    return covariance


def _dependence_statistics(matrix: np.ndarray) -> dict[str, float]:
    """Summarise cross-country dependence in a country-by-period matrix.

    The mean off-diagonal correlation is reported but is not on its own a usable summary: a factor
    whose loadings have mixed signs induces strong pairwise dependence that averages to nearly zero.
    The mean absolute correlation and the leading eigenvalue share of the correlation matrix do not
    cancel that way, so all three travel together.
    """
    covariance = _pairwise_covariance(matrix)
    scale = np.sqrt(np.clip(np.diag(covariance), 1e-24, None))
    correlation = covariance / np.outer(scale, scale)
    off = ~np.eye(correlation.shape[0], dtype=bool)
    finite = correlation[off][np.isfinite(correlation[off])]
    eigenvalues = np.linalg.eigvalsh(np.nan_to_num(correlation, nan=0.0))
    return {
        "mean_correlation": float(np.mean(finite)) if finite.size else float("nan"),
        "mean_absolute_correlation": float(np.mean(np.abs(finite)))
        if finite.size
        else float("nan"),
        "leading_eigenvalue_share": float(np.max(eigenvalues) / correlation.shape[0]),
    }


def _mean_offdiagonal_correlation(matrix: np.ndarray) -> float:
    """Mean correlation between distinct countries, over the periods each pair shares."""
    return _dependence_statistics(matrix)["mean_correlation"]


def _two_way_within(matrix: np.ndarray, iterations: int = 200) -> np.ndarray:
    """Sweep out country and year means by alternating projections.

    For an unbalanced panel the two-way within transform is not one pass of row and column
    demeaning, so the projections alternate to convergence. This mirrors what the estimator does to
    the data and is the space in which surviving dependence should be measured.
    """
    observed = np.isfinite(matrix)
    mask = observed.astype(float)
    working = np.where(observed, matrix, 0.0)
    row_count = mask.sum(axis=1, keepdims=True)
    column_count = mask.sum(axis=0, keepdims=True)
    for _ in range(iterations):
        row_mean = np.divide(
            working.sum(axis=1, keepdims=True),
            row_count,
            out=np.zeros_like(row_count),
            where=row_count > 0,
        )
        working = working - mask * row_mean
        column_mean = np.divide(
            working.sum(axis=0, keepdims=True),
            column_count,
            out=np.zeros_like(column_count),
            where=column_count > 0,
        )
        working = working - mask * column_mean
    return np.where(observed, working, np.nan)


def _draw_errors(
    *,
    calibration: Calibration,
    rng: np.random.Generator,
    design: str,
) -> np.ndarray:
    """Draw one country-by-year error matrix under the named dependence design."""
    if design == "factor":
        loadings = np.asarray(calibration.factor_loadings, dtype=float)
        idiosyncratic = np.asarray(calibration.idiosyncratic_sd, dtype=float)
        factor = rng.normal(0.0, 1.0, size=N_YEARS)
        return loadings[:, None] * factor[None, :] + idiosyncratic[:, None] * rng.normal(
            0.0, 1.0, size=(N_COUNTRIES, N_YEARS)
        )
    if design == "independent":
        # Same total variance per country as the factor design, without the common factor, so a
        # coverage comparison isolates dependence rather than scale.
        loadings = np.asarray(calibration.factor_loadings, dtype=float)
        idiosyncratic = np.asarray(calibration.idiosyncratic_sd, dtype=float)
        total_sd = np.sqrt(loadings**2 + idiosyncratic**2)
        return np.asarray(
            total_sd[:, None] * rng.normal(0.0, 1.0, size=(N_COUNTRIES, N_YEARS)), dtype=float
        )
    if design == "equicorrelated":
        share = EQUICORRELATED_SHARE
        common = rng.normal(0.0, calibration.error_sd, size=N_YEARS)
        idiosyncratic = rng.normal(0.0, calibration.error_sd, size=(N_COUNTRIES, N_YEARS))
        equicorrelated = np.sqrt(share) * common[None, :] + np.sqrt(1.0 - share) * idiosyncratic
        return np.asarray(equicorrelated, dtype=float)
    raise ValueError(f"unknown dependence design: {design}")


def dependence_diagnostic(
    *,
    calibration: Calibration,
    replications: int,
    seed: int,
) -> dict[str, Any]:
    """Measure how much cross-country dependence each design leaves for the estimator.

    This is the check the earlier version of this appendix lacked. Correlation is reported before
    and after the two-way within transform. A design whose within-transformed correlation is at the
    level the transform induces mechanically, about -1/(N-1), has had its dependence absorbed by
    the year dummies and tests nothing.
    """
    rows: dict[str, Any] = {
        "replications": replications,
        "mechanical_within_correlation": -1.0 / (N_COUNTRIES - 1),
        "observed_within_mean_correlation": calibration.observed_mean_correlation,
        "observed_within_mean_absolute_correlation": (
            calibration.observed_mean_absolute_correlation
        ),
        "observed_within_leading_eigenvalue_share": (calibration.observed_leading_eigenvalue_share),
    }
    for design in ("factor", "equicorrelated", "independent"):
        rng = np.random.default_rng(seed)
        raw: list[dict[str, float]] = []
        within: list[dict[str, float]] = []
        for _ in range(replications):
            errors = _draw_errors(calibration=calibration, rng=rng, design=design)
            errors[SHORT_COUNTRY, -1] = np.nan
            raw.append(_dependence_statistics(errors))
            within.append(_dependence_statistics(_two_way_within(errors)))
        summary: dict[str, float] = {}
        for key in ("mean_correlation", "mean_absolute_correlation", "leading_eigenvalue_share"):
            summary[f"raw_{key}"] = float(np.nanmean([entry[key] for entry in raw]))
            summary[f"within_{key}"] = float(np.nanmean([entry[key] for entry in within]))
        rows[design] = summary
        print(
            f"  dependence  {design:15s}"
            f"  within |rho|={summary['within_mean_absolute_correlation']:.4f}"
            f"  within lead={summary['within_leading_eigenvalue_share']:.4f}",
            flush=True,
        )
    return rows


def calibrate(panel_path: Path, driver_column: str) -> Calibration:
    """Read the observed panel and take the moments the simulation needs."""
    growth = build_growth_panel(pd.read_csv(panel_path), driver_column=driver_column)
    design = build_panel_design(
        growth.wage_growth, growth.driver_growth, growth.countries, driver_lags=2
    )
    projector = WithinProjector(design, fixed_effects="country_and_year")
    fit = fit_lsdv(design, projector)

    driver = growth.driver_growth
    observed = np.isfinite(driver)
    year_means = np.array(
        [np.mean(driver[observed[:, column], column]) for column in range(driver.shape[1])]
    )
    residual_driver = driver - year_means[None, :]

    effects = fit.fixed_effect_part
    country_means = np.array(
        [float(np.mean(effects[design.country_index == index])) for index in range(N_COUNTRIES)]
    )
    period_means = np.array(
        [float(np.mean(effects[design.period_index == index])) for index in range(design.n_periods)]
    )
    # The error design is calibrated, not assumed: take the cross-country covariance of the
    # observed within residuals and read a one-factor representation off its leading eigenpair.
    residual_matrix = np.full((N_COUNTRIES, design.n_periods), np.nan, dtype=float)
    residual_matrix[design.country_index, design.period_index] = fit.residuals
    covariance = _pairwise_covariance(residual_matrix)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    leading = int(np.argmax(eigenvalues))
    loadings = eigenvectors[:, leading] * np.sqrt(max(float(eigenvalues[leading]), 0.0))
    if float(np.mean(loadings)) < 0.0:
        loadings = -loadings
    # A one-factor fit can leave a country with no idiosyncratic variance; floor it so the design
    # never produces a country whose errors are a deterministic multiple of the factor.
    error_sd = float(np.std(fit.residuals, ddof=1))
    idiosyncratic_var = np.maximum(np.diag(covariance) - loadings**2, (0.1 * error_sd) ** 2)
    observed_dependence = _dependence_statistics(residual_matrix)

    return Calibration(
        driver_mean=float(np.mean(driver[observed])),
        driver_sd=float(np.std(residual_driver[observed], ddof=1)),
        driver_common_sd=float(np.std(year_means, ddof=1)),
        error_sd=error_sd,
        effect_sd=float(np.std(country_means, ddof=1)),
        year_effect_sd=float(np.std(period_means, ddof=1)),
        factor_loadings=tuple(float(value) for value in loadings),
        idiosyncratic_sd=tuple(float(value) for value in np.sqrt(idiosyncratic_var)),
        observed_mean_correlation=observed_dependence["mean_correlation"],
        observed_mean_absolute_correlation=observed_dependence["mean_absolute_correlation"],
        observed_leading_eigenvalue_share=observed_dependence["leading_eigenvalue_share"],
    )


def simulate_growth_panel(
    *,
    gamma: float,
    beta: np.ndarray,
    calibration: Calibration,
    rng: np.random.Generator,
    dependence: str = "factor",
) -> GrowthPanel:
    """Draw one panel from the estimator's own model, at the estimation sample's dimensions."""
    year_driver = rng.normal(0.0, calibration.driver_common_sd, size=N_YEARS)
    driver = (
        calibration.driver_mean
        + year_driver[None, :]
        + rng.normal(0.0, calibration.driver_sd, size=(N_COUNTRIES, N_YEARS))
    )

    country_effect = rng.normal(0.0, calibration.effect_sd, size=N_COUNTRIES)
    year_effect = rng.normal(0.0, calibration.year_effect_sd, size=N_YEARS)
    errors = _draw_errors(calibration=calibration, rng=rng, design=dependence)

    wage = np.zeros((N_COUNTRIES, N_YEARS), dtype=float)
    wage[:, 0] = country_effect / max(1.0 - gamma, 1e-6) + errors[:, 0]
    for step in range(1, N_YEARS):
        driven = np.zeros(N_COUNTRIES, dtype=float)
        for lag, coefficient in enumerate(beta):
            if step - lag >= 0:
                driven += coefficient * driver[:, step - lag]
        wage[:, step] = (
            country_effect
            + year_effect[step]
            + driven
            + gamma * wage[:, step - 1]
            + errors[:, step]
        )

    wage[SHORT_COUNTRY, -1] = np.nan
    driver = driver.copy()
    driver[SHORT_COUNTRY, -1] = np.nan
    return GrowthPanel(
        countries=COUNTRIES,
        years=tuple(range(1996, 1996 + N_YEARS)),
        wage_growth=wage,
        driver_growth=driver,
    )


def _fit_pair(
    growth: GrowthPanel,
    *,
    draws: int,
    iterations: int,
    seed: int,
) -> tuple[float, float, float, float, bool] | None:
    """Return LSDV and corrected persistence and multiplier for one simulated panel."""
    try:
        design = build_panel_design(
            growth.wage_growth, growth.driver_growth, growth.countries, driver_lags=2
        )
        projector = WithinProjector(design, fixed_effects="country_and_year")
        fit = fit_lsdv(design, projector, check_rank=False)
        correction = BiasCorrector(
            design,
            projector,
            draws=draws,
            iterations=iterations,
            rng=np.random.default_rng(seed),
        ).correct(fit)
    except (ValueError, np.linalg.LinAlgError):
        return None
    return (
        fit.persistence,
        fit.multiplier,
        correction.persistence,
        correction.multiplier,
        correction.converged,
    )


def bias_study(
    *,
    gammas: tuple[float, ...],
    beta: np.ndarray,
    calibration: Calibration,
    replications: int,
    draws: int,
    iterations: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Measure how much of the dynamic fixed-effects bias the correction removes."""
    rows: list[dict[str, Any]] = []
    for gamma in gammas:
        true_multiplier = cumulative_multiplier(np.append(beta, gamma))
        lsdv_gamma: list[float] = []
        lsdv_theta: list[float] = []
        corrected_gamma: list[float] = []
        corrected_theta: list[float] = []
        converged = 0
        rng = np.random.default_rng(seed + round(gamma * 1000))
        for replication in range(replications):
            growth = simulate_growth_panel(gamma=gamma, beta=beta, calibration=calibration, rng=rng)
            fitted = _fit_pair(growth, draws=draws, iterations=iterations, seed=seed + replication)
            if fitted is None:
                continue
            lsdv_gamma.append(fitted[0])
            lsdv_theta.append(fitted[1])
            corrected_gamma.append(fitted[2])
            corrected_theta.append(fitted[3])
            converged += int(fitted[4])

        raw_gamma_bias = float(np.mean(lsdv_gamma)) - gamma
        left_gamma_bias = float(np.mean(corrected_gamma)) - gamma
        raw_theta_bias = float(np.mean(lsdv_theta)) - true_multiplier
        left_theta_bias = float(np.mean(corrected_theta)) - true_multiplier
        rows.append(
            {
                "true_persistence": gamma,
                "true_multiplier": true_multiplier,
                "replications": replications,
                "completed": len(lsdv_gamma),
                "converged": converged,
                "lsdv_persistence_mean": float(np.mean(lsdv_gamma)),
                "corrected_persistence_mean": float(np.mean(corrected_gamma)),
                "lsdv_persistence_bias": raw_gamma_bias,
                "corrected_persistence_bias": left_gamma_bias,
                "persistence_bias_removed": 1.0 - abs(left_gamma_bias) / abs(raw_gamma_bias),
                "nickell_approximation": -(1.0 + gamma) / 28.0,
                "lsdv_multiplier_mean": float(np.mean(lsdv_theta)),
                "corrected_multiplier_mean": float(np.mean(corrected_theta)),
                "lsdv_multiplier_bias": raw_theta_bias,
                "corrected_multiplier_bias": left_theta_bias,
                "corrected_multiplier_sd": float(np.std(corrected_theta, ddof=1)),
            }
        )
        print(
            f"  bias  gamma={gamma:.2f}  removed={rows[-1]['persistence_bias_removed'] * 100:5.1f}%",
            flush=True,
        )
    return rows


def coverage_study(
    *,
    gammas: tuple[float, ...],
    beta: np.ndarray,
    calibration: Calibration,
    replications: int,
    bootstrap_replications: int,
    draws: int,
    iterations: int,
    block_length: int,
    alpha: float,
    seed: int,
    dependence: str = "factor",
) -> list[dict[str, Any]]:
    """Measure coverage of the percentile and reverse-percentile intervals for Theta."""
    rows: list[dict[str, Any]] = []
    for gamma in gammas:
        true_multiplier = cumulative_multiplier(np.append(beta, gamma))
        percentile_hits = 0
        reverse_hits = 0
        percentile_widths: list[float] = []
        reverse_widths: list[float] = []
        displacements: list[float] = []
        completed = 0
        started = time.monotonic()
        rng = np.random.default_rng(seed + round(gamma * 1000))
        for replication in range(replications):
            growth = simulate_growth_panel(
                gamma=gamma,
                beta=beta,
                calibration=calibration,
                rng=rng,
                dependence=dependence,
            )
            try:
                design = build_panel_design(
                    growth.wage_growth, growth.driver_growth, growth.countries, driver_lags=2
                )
                projector = WithinProjector(design, fixed_effects="country_and_year")
                fit = fit_lsdv(design, projector, check_rank=False)
                point = BiasCorrector(
                    design,
                    projector,
                    draws=draws,
                    iterations=iterations,
                    rng=np.random.default_rng(seed + replication),
                ).correct(fit)
                bootstrap = bootstrap_dynamic_panel(
                    growth,
                    projector,
                    driver_lags=2,
                    block_length=block_length,
                    replications=bootstrap_replications,
                    bias_correction_draws=draws,
                    bias_correction_iterations=iterations,
                    rng=np.random.default_rng(seed + 100_000 + replication),
                )
            except (ValueError, np.linalg.LinAlgError):
                continue

            finite = bootstrap.corrected_multiplier[np.isfinite(bootstrap.corrected_multiplier)]
            if finite.size < bootstrap_replications // 2:
                continue
            low = float(np.quantile(finite, alpha / 2.0))
            high = float(np.quantile(finite, 1.0 - alpha / 2.0))
            estimate = point.multiplier
            # Reverse percentile (basic): reflects the resampling distribution about the estimate,
            # which is what a displaced bootstrap distribution calls for.
            reverse_low = 2.0 * estimate - high
            reverse_high = 2.0 * estimate - low

            completed += 1
            percentile_hits += int(low <= true_multiplier <= high)
            reverse_hits += int(reverse_low <= true_multiplier <= reverse_high)
            percentile_widths.append(high - low)
            reverse_widths.append(reverse_high - reverse_low)
            displacements.append(float(np.median(finite)) - estimate)

        rows.append(
            {
                "true_persistence": gamma,
                "true_multiplier": true_multiplier,
                "dependence": dependence,
                "replications": replications,
                "completed": completed,
                "bootstrap_replications": bootstrap_replications,
                "block_length": block_length,
                "nominal_coverage": 1.0 - alpha,
                "percentile_coverage": percentile_hits / completed if completed else float("nan"),
                "percentile_coverage_ci": clopper_pearson(percentile_hits, completed),
                "percentile_coverage_mc_se": _binomial_se(percentile_hits, completed),
                "reverse_percentile_coverage": (
                    reverse_hits / completed if completed else float("nan")
                ),
                "reverse_percentile_coverage_ci": clopper_pearson(reverse_hits, completed),
                "reverse_percentile_coverage_mc_se": _binomial_se(reverse_hits, completed),
                "percentile_mean_width": float(np.mean(percentile_widths)) if completed else 0.0,
                "reverse_percentile_mean_width": (
                    float(np.mean(reverse_widths)) if completed else 0.0
                ),
                "median_displacement": float(np.mean(displacements)) if completed else 0.0,
                "seconds": time.monotonic() - started,
            }
        )
        low, high = rows[-1]["percentile_coverage_ci"]
        print(
            f"  cover gamma={gamma:.2f}  percentile={rows[-1]['percentile_coverage']:.3f}"
            f" [{low:.3f}, {high:.3f}]"
            f"  reverse={rows[-1]['reverse_percentile_coverage']:.3f}"
            f"  ({rows[-1]['seconds']:.0f}s)",
            flush=True,
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--panel",
        type=Path,
        default=Path("data/processed/2026-08-25/panel_per_worker.csv"),
    )
    parser.add_argument("--driver", default="productivity_per_worker")
    parser.add_argument("--bias-replications", type=int, default=300)
    parser.add_argument("--coverage-replications", type=int, default=400)
    parser.add_argument("--bootstrap-replications", type=int, default=999)
    parser.add_argument("--draws", type=int, default=60)
    parser.add_argument("--iterations", type=int, default=12)
    parser.add_argument("--block-length", type=int, default=4)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument("--dependence-replications", type=int, default=400)
    args = parser.parse_args(argv)

    calibration = calibrate(args.panel, args.driver)
    beta = np.array([0.4501, -0.0700, 0.0900], dtype=float)
    print(f"calibration: {calibration.to_dict()}", flush=True)

    dependence = dependence_diagnostic(
        calibration=calibration,
        replications=args.dependence_replications,
        seed=args.seed,
    )

    bias_rows = bias_study(
        gammas=(0.1, 0.3, 0.5, 0.7),
        beta=beta,
        calibration=calibration,
        replications=args.bias_replications,
        draws=200,
        iterations=args.iterations,
        seed=args.seed,
    )
    coverage_rows = coverage_study(
        gammas=(0.15, 0.45),
        beta=beta,
        calibration=calibration,
        replications=args.coverage_replications,
        bootstrap_replications=args.bootstrap_replications,
        draws=args.draws,
        iterations=args.iterations,
        block_length=args.block_length,
        alpha=args.alpha,
        seed=args.seed,
    )

    write_json(
        {
            "package_version": __version__,
            "prespecified": False,
            "purpose": "monte_carlo_validation_of_a_locked_estimator",
            "panel_path": args.panel.as_posix(),
            "panel_sha256": sha256_bytes(args.panel.read_bytes()),
            "driver": args.driver,
            "dependence": dependence,
            "design": {
                "n_countries": N_COUNTRIES,
                "n_growth_years": N_YEARS,
                "short_country_missing_endpoint": True,
                "driver_lags": 2,
                "wage_lags": 1,
                "fixed_effects": "country_and_year",
                "error_design": "one_factor_heterogeneous_loadings",
                "beta": [float(value) for value in beta],
                "bias_correction_draws_bias_study": 200,
                "bias_correction_draws_coverage_study": args.draws,
                "bias_correction_max_iterations": args.iterations,
                "seed": args.seed,
            },
            "calibration": calibration.to_dict(),
            "bias_study": bias_rows,
            "coverage_study": coverage_rows,
        },
        args.output,
    )
    print(f"Validation written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
