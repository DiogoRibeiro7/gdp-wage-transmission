"""Run the pooled panel estimator on a frozen vintage as a post-hoc robustness exercise.

This tool sits outside ``src/wage_transmission`` and estimates nothing itself: it calls
``estimate_panel_fixed_effects``, which is part of the locked analysis package and was written
before the specification lock. Running it therefore changes no locked byte, and the lock still
verifies against the code that produced every pre-specified estimate.

What is post-hoc is the decision to report the result, taken after the pre-specified estimates
were seen. That is a real distinction and the output records it: the manifest carries
``prespecified: false`` so a table built from it cannot be presented as part of the confirmatory
hierarchy. The pooled estimate is a robustness exercise, never a replacement for the
country-specific estimates.

The result is written as a JSON artefact with the digest of every input panel, so a table
generated from it is as traceable as one generated from the dossier.

**Superseded in v0.8.0, and deliberately kept.** This specification is static: wage growth on
contemporaneous driver growth, no lags and no lagged dependent variable, so its coefficient is a
contemporaneous association and not the cumulative multiplier the paper reports. It also uses
every available first difference, 389 observations, where a dynamic panel matching the primary
specification uses 363. The two are different objects and were briefly compared as though they
were not. :mod:`wage_transmission.models.dynamic_panel` now provides the comparable estimator,
and the paper reports that one instead; this tool and its output remain as a historical artefact
of the earlier release. Do not wire its output back into the manuscript.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from wage_transmission.cross_country import estimate_panel_fixed_effects
from wage_transmission.version import __version__

DRIVERS = {
    "panel_per_worker.csv": "productivity_per_worker",
    "panel_per_hour.csv": "productivity",
}


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(panel_dir: Path, vintage: str) -> dict[str, Any]:
    """Estimate the pooled specification for each driver, with and without year effects."""
    records: list[dict[str, Any]] = []
    inputs: dict[str, str] = {}

    for filename, driver in DRIVERS.items():
        path = panel_dir / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        inputs[filename] = sha256_file(path)
        panel = pd.read_csv(path)
        for time_effects in (False, True):
            result = estimate_panel_fixed_effects(
                panel, driver_column=driver, time_effects=time_effects
            )
            record = asdict(result)
            record["source_panel"] = filename
            records.append(record)

    return {
        "schema_version": 1,
        "vintage": vintage,
        "package_version": __version__,
        "prespecified": False,
        "status": "post_hoc_robustness_not_part_of_the_confirmatory_hierarchy",
        "note": (
            "The estimator is part of the locked analysis package; the decision to report it was "
            "taken after the pre-specified estimates were seen. Cluster-robust inference is "
            "asymptotic in the number of clusters, and thirteen is well below the conventional "
            "threshold, so the reported standard errors are optimistic."
        ),
        "causal_claims_authorized": False,
        "inputs": inputs,
        "estimates": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--panel-dir", type=Path, required=True)
    parser.add_argument("--vintage", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    payload = build(args.panel_dir, args.vintage)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")

    for record in payload["estimates"]:
        effects = "country + year" if record["time_effects"] else "country"
        print(
            f"{record['driver']:24s} {effects:14s} "
            f"{record['elasticity']:+.3f} (clustered se {record['std_error']:.3f}, "
            f"{record['n_countries']} clusters)"
        )
    print(f"\nWritten to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
