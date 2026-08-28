"""Document the simulation's error design, and measure what its dependence costs.

Two things the coverage study on its own cannot show.

The first is what the design actually is. A reader cannot check that simulated panels carry
cross-sectional dependence resembling the estimated one without the factor loadings, the
idiosyncratic scales, and a measure of the dependence that survives the two-way within transform.
All of that is recorded here, for three error designs:

``factor``
    the design the coverage study uses, ``e_it = c_i f_t + d_i z_it`` with heterogeneous loadings
    read off the leading eigenpair of the cross-country covariance of the observed within
    residuals;
``equicorrelated``
    one annual disturbance shared by every country, which unrestricted year effects remove
    exactly, included to show that a design of that shape tests nothing;
``independent``
    no common component, with each country's total variance held at the factor design's
    ``c_i^2 + d_i^2`` so the comparison isolates dependence rather than scale.

The second is how much of the interval's undercoverage is attributable to dependence at all. The
coverage study is repeated here under independent errors, at the same persistence values and the
same replication counts, so the two coverage figures differ only in whether the errors are
dependent.

Usage::

    poetry run python tools/dynamic_panel_dependence_benchmark.py \\
        --output results/vintages/2026-08-25/publication_dossier/dynamic_panel_benchmark.json
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from dynamic_panel_validation import (
    N_COUNTRIES,
    calibrate,
    coverage_study,
    dependence_diagnostic,
)
from wage_transmission.data.common import sha256_bytes
from wage_transmission.reporting import write_json
from wage_transmission.version import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--panel",
        type=Path,
        default=Path("data/processed/2026-08-25/panel_per_worker.csv"),
    )
    parser.add_argument("--driver", default="productivity_per_worker")
    parser.add_argument("--coverage-replications", type=int, default=400)
    parser.add_argument("--bootstrap-replications", type=int, default=999)
    parser.add_argument("--draws", type=int, default=60)
    parser.add_argument("--iterations", type=int, default=12)
    parser.add_argument("--block-length", type=int, default=4)
    parser.add_argument("--dependence-replications", type=int, default=400)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument(
        "--skip-coverage",
        action="store_true",
        help="Record the design and the dependence diagnostic without the benchmark coverage run.",
    )
    args = parser.parse_args(argv)

    calibration = calibrate(args.panel, args.driver)
    # The residual covariance is indexed by the estimation panel's country order, so the loadings
    # belong to named countries rather than to anonymous rows.
    labels = tuple(
        str(code) for code in sorted(pd.read_csv(args.panel)["country"].astype(str).unique())
    )
    dependence = dependence_diagnostic(
        calibration=calibration,
        replications=args.dependence_replications,
        seed=args.seed,
    )

    loadings = np.asarray(calibration.factor_loadings, dtype=float)
    idiosyncratic = np.asarray(calibration.idiosyncratic_sd, dtype=float)
    countries: list[dict[str, Any]] = [
        {
            "index": index,
            "country": labels[index] if index < len(labels) else f"C{index:02d}",
            "loading": float(loadings[index]),
            "idiosyncratic_sd": float(idiosyncratic[index]),
            "factor_variance_share": float(
                loadings[index] ** 2 / (loadings[index] ** 2 + idiosyncratic[index] ** 2)
            ),
        }
        for index in range(N_COUNTRIES)
    ]

    coverage: list[dict[str, Any]] = []
    if not args.skip_coverage:
        beta = np.array([0.4501, -0.0700, 0.0900], dtype=float)
        coverage = coverage_study(
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
            dependence="independent",
        )

    write_json(
        {
            "package_version": __version__,
            "prespecified": False,
            "purpose": "documentation_of_the_simulation_error_design_and_an_independent_benchmark",
            "panel_path": args.panel.as_posix(),
            "panel_sha256": sha256_bytes(args.panel.read_bytes()),
            "driver": args.driver,
            "decomposition": (
                "One-factor representation of the cross-country covariance of the observed within "
                "residuals. Loadings are the leading eigenvector scaled by the square root of its "
                "eigenvalue; idiosyncratic variances are the diagonal of that covariance less the "
                "squared loading, floored at one hundredth of the residual variance. Factor and "
                "idiosyncratic shocks are drawn independently from the standard normal."
            ),
            "countries": countries,
            "factor_loading_mean": float(np.mean(loadings)),
            "factor_loading_sd": float(np.std(loadings, ddof=1)),
            "dependence": dependence,
            "independent_coverage_study": coverage,
        },
        args.output,
    )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
