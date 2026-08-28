"""Post-hoc comparison of the two functionals the paper reports.

The country regressions and the dynamic panel do not report the same function of the same
coefficients. The country specification

    dlog w_t = alpha + sum_j beta_j dlog p_{t-j} + gamma dlog w_{t-1} + e_t

reports ``Theta = sum_j beta_j``, the sum of the current and lagged driver coefficients with lagged
wage growth held fixed. The panel reports ``sum_j beta_j / (1 - gamma)``, the long-run response of
the same equation to a permanent change in driver growth. These coincide only when ``gamma`` is
zero. Comparing the country median with the panel estimate therefore compares two different
quantities, and this tool measures how much that matters.

Nothing here is pre-specified and nothing here revises a reported number. The locked estimator is
called, not modified: coefficients and their HAC covariance come from the same routine that
produced the paper's estimates, and the long-run figure is computed from them afterwards.

Because the long-run figure is a ratio of estimated quantities, it also gets an interval that does
not assume the denominator is far from zero. Fieller's theorem inverts the test of
``a - R b = 0`` and so respects the geometry of a ratio: when the denominator is poorly determined
the resulting set is unbounded, which is the honest answer and one a delta-method standard error
cannot give. Both intervals are reported so the difference is visible.

Usage::

    poetry run python tools/longrun_sensitivity.py \\
        --output results/vintages/2026-08-25/publication_dossier/longrun_sensitivity.json
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from wage_transmission.data.common import sha256_bytes
from wage_transmission.models._regression import fit_ols_hac, lagged
from wage_transmission.models.distributed_lag import fit_distributed_lag
from wage_transmission.reporting import write_json
from wage_transmission.validation import add_log_growth_columns
from wage_transmission.version import __version__

#: The frozen lag structure. These mirror ``config/models.yml`` and are not selected here.
X_LAGS = 2
Y_LAGS = 1
HAC_LAGS = 2


def _fieller_interval(
    *,
    numerator: float,
    denominator: float,
    var_numerator: float,
    var_denominator: float,
    covariance: float,
    alpha: float,
) -> tuple[float, float, bool]:
    """Fieller interval for ``numerator / denominator``.

    Inverting the test of ``a - R b = 0`` gives the quadratic ``A R^2 + B R + C <= 0``. When the
    leading coefficient is not positive the denominator is not distinguishable from zero at this
    level and the solution set is unbounded rather than an interval; that case is reported as such
    instead of being silently truncated.
    """
    z = float(norm.ppf(1.0 - alpha / 2.0))
    a_coefficient = denominator**2 - z**2 * var_denominator
    b_coefficient = -2.0 * (numerator * denominator - z**2 * covariance)
    c_coefficient = numerator**2 - z**2 * var_numerator
    discriminant = b_coefficient**2 - 4.0 * a_coefficient * c_coefficient
    if a_coefficient <= 0.0 or discriminant < 0.0:
        return (float("-inf"), float("inf"), False)
    root = np.sqrt(discriminant)
    low = (-b_coefficient - root) / (2.0 * a_coefficient)
    high = (-b_coefficient + root) / (2.0 * a_coefficient)
    return (float(min(low, high)), float(max(low, high)), True)


def _country_row(frame: pd.DataFrame, *, alpha: float) -> dict[str, Any]:
    """Both functionals, and three intervals, for one country."""
    data = add_log_growth_columns(frame)
    design = lagged(data["dlog_productivity"], "prod", X_LAGS, include_zero=True)
    design = pd.concat(
        [design, lagged(data["dlog_wage"], "wage", Y_LAGS, include_zero=False)], axis=1
    )
    fitted = fit_ols_hac(data["dlog_wage"], design, hac_lags=HAC_LAGS)

    driver_names = [f"prod_l{lag}" for lag in range(X_LAGS + 1)]
    names = [*driver_names, "wage_l1"]
    covariance = fitted.cov_params().loc[names, names].to_numpy(dtype=float)
    selector_sum = np.array([1.0, 1.0, 1.0, 0.0])
    selector_gamma = np.array([0.0, 0.0, 0.0, 1.0])

    total = float(sum(fitted.params[name] for name in driver_names))
    gamma = float(fitted.params["wage_l1"])
    denominator = 1.0 - gamma

    var_total = float(selector_sum @ covariance @ selector_sum)
    var_gamma = float(selector_gamma @ covariance @ selector_gamma)
    # d(1 - gamma) = -d gamma, so the covariance of the numerator with the denominator flips sign.
    cov_total_denominator = -float(selector_sum @ covariance @ selector_gamma)

    z = float(norm.ppf(1.0 - alpha / 2.0))
    impact_se = float(np.sqrt(max(var_total, 0.0)))

    long_run = total / denominator if denominator != 0.0 else float("nan")
    # Delta method for a ratio: gradient (1/b, a/b^2) against the (a, b) covariance.
    gradient = np.array([1.0 / denominator, total / denominator**2])
    ratio_covariance = np.array(
        [[var_total, cov_total_denominator], [cov_total_denominator, var_gamma]]
    )
    long_run_var = float(gradient @ ratio_covariance @ gradient)
    long_run_se = float(np.sqrt(max(long_run_var, 0.0)))

    fieller_low, fieller_high, bounded = _fieller_interval(
        numerator=total,
        denominator=denominator,
        var_numerator=var_total,
        var_denominator=var_gamma,
        covariance=cov_total_denominator,
        alpha=alpha,
    )

    return {
        "impact_sum": total,
        "impact_std_error": impact_se,
        "impact_ci_low": total - z * impact_se,
        "impact_ci_high": total + z * impact_se,
        "persistence": gamma,
        "one_minus_persistence": denominator,
        "long_run": long_run,
        "long_run_std_error": long_run_se,
        "long_run_delta_ci_low": long_run - z * long_run_se,
        "long_run_delta_ci_high": long_run + z * long_run_se,
        "long_run_fieller_ci_low": fieller_low,
        "long_run_fieller_ci_high": fieller_high,
        "long_run_fieller_bounded": bounded,
        "n_observations": int(fitted.nobs),
    }


def build(panels: dict[str, Path], *, alpha: float) -> dict[str, Any]:
    """Assemble the comparison for every driver and country."""
    drivers: dict[str, Any] = {}
    for driver, path in panels.items():
        panel = pd.read_csv(path)
        column = next(name for name in panel.columns if name.startswith("productivity"))
        rows = []
        for country, block in panel.groupby("country"):
            frame = block.sort_values("year").rename(columns={column: "productivity"})
            # Guard the comparison against drift: the impact sum recomputed here must equal the
            # number the locked estimator reports, or the two are not describing one regression.
            reference = fit_distributed_lag(frame, x_lags=X_LAGS, y_lags=Y_LAGS, hac_lags=HAC_LAGS)
            row = _country_row(frame, alpha=alpha)
            if abs(row["impact_sum"] - reference.cumulative_transmission) > 1e-9:
                raise ValueError(f"impact sum disagrees with the locked estimator for {country}")
            if abs(row["impact_std_error"] - reference.cumulative_std_error) > 1e-9:
                raise ValueError(f"impact error disagrees with the locked estimator for {country}")
            row["country"] = str(country)
            rows.append(row)

        impact = np.array([row["impact_sum"] for row in rows])
        long_run = np.array([row["long_run"] for row in rows])
        drivers[driver] = {
            "panel_path": path.as_posix(),
            "panel_sha256": sha256_bytes(path.read_bytes()),
            "countries": rows,
            "median_impact_sum": float(np.median(impact)),
            "median_long_run": float(np.median(long_run)),
            "n_impact_above_one": int(np.sum(impact > 1.0)),
            "n_long_run_above_one": int(np.sum(long_run > 1.0)),
            "n_sign_disagreement": int(np.sum(np.sign(impact) != np.sign(long_run))),
            "n_fieller_unbounded": int(sum(not row["long_run_fieller_bounded"] for row in rows)),
        }
    return drivers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--per-worker",
        type=Path,
        default=Path("data/processed/2026-08-25/panel_per_worker.csv"),
    )
    parser.add_argument(
        "--per-hour",
        type=Path,
        default=Path("data/processed/2026-08-25/panel_per_hour.csv"),
    )
    parser.add_argument("--alpha", type=float, default=0.05)
    args = parser.parse_args(argv)

    drivers = build(
        {"productivity_per_worker": args.per_worker, "productivity_per_hour": args.per_hour},
        alpha=args.alpha,
    )
    write_json(
        {
            "package_version": __version__,
            "prespecified": False,
            "purpose": "post_hoc_comparison_of_reported_functionals",
            "alpha": args.alpha,
            "lag_structure": {"x_lags": X_LAGS, "y_lags": Y_LAGS, "hac_lags": HAC_LAGS},
            "drivers": drivers,
        },
        args.output,
    )
    for driver, payload in drivers.items():
        print(
            f"{driver}: median impact {payload['median_impact_sum']:.4f}"
            f"  median long run {payload['median_long_run']:.4f}"
            f"  above one {payload['n_impact_above_one']}->{payload['n_long_run_above_one']}"
            f"  unbounded Fieller {payload['n_fieller_unbounded']}",
            flush=True,
        )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
