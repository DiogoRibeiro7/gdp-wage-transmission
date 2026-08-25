"""Build one complete result vintage from frozen processed panels.

The individual steps are all available as CLI commands, but running them by hand leaves the
exact sequence -- and, more importantly, the exact paths each step consumes -- as tribal
knowledge. This script is the sequence. It estimates nothing itself: every number comes from
the locked analysis package, and this file only decides what is run against what.

Two path choices are worth flagging because they are easy to get wrong:

* the publication dossier takes the **cross-country** decomposition summary, not the
  Portugal-only one, because the paper's decomposition appendix reports every covered country;
* the dynamic panel is run once per driver and the two are never pooled.

Usage::

    poetry run python tools/build_vintage.py --vintage 2026-08-25 \\
        --specification-lock paper/specification_lock_v0.8.0.json
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from wage_transmission.config import load_models_config, load_publication_config
from wage_transmission.cross_country import (
    estimate_country_robustness,
    summarise_country_robustness,
    write_country_robustness,
)
from wage_transmission.data.common import sha256_bytes
from wage_transmission.decomposition import decompose_panel
from wage_transmission.models.dynamic_panel import estimate_dynamic_panel_suite
from wage_transmission.pipeline import analyse_country
from wage_transmission.publication import build_publication_dossier
from wage_transmission.release import build_release_manifest, write_release_manifest
from wage_transmission.reporting import write_json
from wage_transmission.version import __version__

#: Driver column name in each processed panel, keyed by the publication driver label.
DRIVERS: dict[str, tuple[str, str]] = {
    "productivity_per_worker": ("panel_per_worker.csv", "productivity_per_worker"),
    "productivity": ("panel_per_hour.csv", "productivity"),
}

#: Result subdirectory for each driver's single-country run.
COUNTRY_DIRECTORY = {
    "productivity_per_worker": "portugal_per_worker",
    "productivity": "portugal_per_hour",
}

#: Cross-country and dynamic-panel filenames for each driver.
CROSS_COUNTRY_FILE = {
    "productivity_per_worker": "cross_country_per_worker.csv",
    "productivity": "cross_country_per_hour.csv",
}
DYNAMIC_PANEL_FILE = {
    "productivity_per_worker": "dynamic_panel_per_worker.json",
    "productivity": "dynamic_panel_per_hour.json",
}


def _announce(step: str, started: float) -> None:
    print(f"  [{time.monotonic() - started:7.1f}s] {step}", flush=True)


def build_vintage(
    *,
    vintage: str,
    processed_root: Path,
    results_root: Path,
    specification_lock: Path | None,
    models_config: Path,
    project_config: Path,
    publication_config: Path,
    primary_country: str,
) -> Path:
    """Run every step of one vintage and return the dossier directory."""
    started = time.monotonic()
    models = load_models_config(models_config)
    publication = load_publication_config(publication_config)
    processed = processed_root / vintage
    results_root.mkdir(parents=True, exist_ok=True)

    country_results: dict[str, Path] = {}
    cross_country_results: dict[str, Path] = {}
    dynamic_panel_results: dict[str, Path] = {}

    for driver, (panel_file, column) in DRIVERS.items():
        panel = pd.read_csv(processed / panel_file)

        single = panel.loc[panel["country"].astype(str) == primary_country].copy()
        output_dir = results_root / COUNTRY_DIRECTORY[driver]
        analyse_country(single, output_dir, driver_column=column, model_config=models)
        write_json(
            {
                "package_version": __version__,
                "country": primary_country,
                "driver": column,
                "input_path": (processed / panel_file).as_posix(),
                "input_sha256": sha256_bytes((processed / panel_file).read_bytes()),
                "models_config_path": models_config.as_posix(),
                "models_config_sha256": sha256_bytes(models_config.read_bytes()),
            },
            output_dir / "run_manifest.json",
        )
        country_results[driver] = output_dir / "model_results.json"
        _announce(f"country models: {driver}", started)

        estimates = estimate_country_robustness(panel, driver_column=column, config=models)
        cross_path = results_root / CROSS_COUNTRY_FILE[driver]
        write_country_robustness(estimates, cross_path)
        write_json(
            summarise_country_robustness(estimates, driver=driver),
            cross_path.with_suffix(".summary.json"),
        )
        cross_country_results[driver] = cross_path
        _announce(f"country-by-country estimates: {driver} ({len(estimates)} countries)", started)

        suite = estimate_dynamic_panel_suite(
            panel,
            driver_column=column,
            config=models.dynamic_panel,
            alpha=publication.alpha,
        )
        dynamic_path = results_root / DYNAMIC_PANEL_FILE[driver]
        write_json(suite, dynamic_path)
        dynamic_panel_results[driver] = dynamic_path
        primary = suite.primary
        _announce(
            f"dynamic panel: {driver} Theta={primary.corrected_multiplier:.4f} "
            f"[{primary.corrected_multiplier_ci[0]:.4f}, {primary.corrected_multiplier_ci[1]:.4f}] "
            f"n={primary.nobs} "
            f"({'eligible' if primary.claim_eligible else 'NOT eligible'})",
            started,
        )

    decomposition_inputs = pd.read_csv(processed / "decomposition_inputs.csv")
    cross_decomposition = _write_decomposition(
        decomposition_inputs,
        results_root / "cross_country_decomposition",
        country=None,
        source=processed / "decomposition_inputs.csv",
    )
    _write_decomposition(
        decomposition_inputs,
        results_root / "portugal_decomposition",
        country=primary_country,
        source=processed / "decomposition_inputs.csv",
    )
    _announce("decompositions", started)

    dossier = build_publication_dossier(
        country_results=country_results,
        cross_country_results=cross_country_results,
        decomposition_summary=cross_decomposition,
        dynamic_panel_results=dynamic_panel_results,
        specification_lock=specification_lock,
        publication_config=publication,
        output_dir=results_root / "publication_dossier",
    )
    _announce(f"publication dossier: {dossier.manifest}", started)

    manifest = build_release_manifest(
        vintage=vintage,
        raw_root=Path("data/raw") / vintage,
        model_config=models_config,
        project_config=project_config,
        publication_config=publication_config,
        outputs={
            "core_estimates": dossier.core_estimates,
            "cross_country_summary": dossier.cross_country,
            "reliability_gates": dossier.reliability,
            **({"dynamic_panel": dossier.dynamic_panel} if dossier.dynamic_panel else {}),
        },
    )
    write_release_manifest(manifest, results_root / "release_manifest.json")
    _announce("release manifest", started)
    return results_root / "publication_dossier"


def _write_decomposition(
    frame: pd.DataFrame,
    output_dir: Path,
    *,
    country: str | None,
    source: Path,
) -> Path:
    selected = frame if country is None else frame.loc[frame["country"].astype(str) == country]
    components, summaries = decompose_panel(selected.copy())
    output_dir.mkdir(parents=True, exist_ok=True)
    components.to_csv(output_dir / "decomposition_components.csv", index=False)
    summary_path = output_dir / "decomposition_summary.json"
    write_json(summaries, summary_path)
    write_json(
        {
            "package_version": __version__,
            "country_filter": country,
            "input_path": source.as_posix(),
            "input_sha256": sha256_bytes(source.read_bytes()),
        },
        output_dir / "run_manifest.json",
    )
    return summary_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vintage", required=True)
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--results-root", type=Path, default=None)
    parser.add_argument("--specification-lock", type=Path, default=None)
    parser.add_argument("--models-config", type=Path, default=Path("config/models.yml"))
    parser.add_argument("--project-config", type=Path, default=Path("config/project.yml"))
    parser.add_argument("--publication-config", type=Path, default=Path("config/publication.yml"))
    parser.add_argument("--primary-country", default="PRT")
    args = parser.parse_args(argv)

    results_root = args.results_root or Path("results/vintages") / args.vintage
    dossier = build_vintage(
        vintage=args.vintage,
        processed_root=args.processed_root,
        results_root=results_root,
        specification_lock=args.specification_lock,
        models_config=args.models_config,
        project_config=args.project_config,
        publication_config=args.publication_config,
        primary_country=args.primary_country,
    )
    print(f"Vintage {args.vintage} built; dossier at {dossier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
