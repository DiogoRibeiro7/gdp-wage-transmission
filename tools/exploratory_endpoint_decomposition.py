"""Build an exploratory endpoint labour-income decomposition for Portugal.

This reporting-side helper intentionally lives outside ``src/wage_transmission`` so it does not
change the pre-results analysis-source hash. It performs no network access and estimates no model.
It only applies the already-locked accounting identity to two supplied endpoint observations.

The publication specification requires Eurostat national-accounts employees in the domestic
concept (``SAL_DC``). When that denominator is unavailable, this tool keeps the locked decomposition
incomplete and may optionally calculate a clearly labelled sensitivity using another employee
series. Such a sensitivity is never publication-eligible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from wage_transmission.decomposition import (
    decompose_real_wage_growth,
    summarise_decomposition,
)

INPUT_COLUMNS: tuple[str, ...] = (
    "year",
    "nominal_gdp_m_eur",
    "employee_compensation_m_eur",
    "gdp_deflator",
    "hicp_annual_avg",
    "employees_lfs_thousand",
)

PARTIAL_COMPONENT_ORDER: tuple[str, ...] = (
    "real_gdp_component",
    "labour_share_component",
    "employment_component",
    "relative_price_component",
)


@dataclass(frozen=True)
class EndpointPartialSummary:
    """Employee-independent terms of the locked endpoint decomposition."""

    country: str
    start_year: int
    end_year: int
    locked_employee_concept: str
    locked_sal_dc_status: str
    publication_eligible: bool
    start_labour_share: float
    end_labour_share: float
    labour_share_level_change_pp: float
    real_gdp_log_contribution: float
    labour_share_log_contribution: float
    employment_log_contribution: float | None
    relative_price_log_contribution: float
    decomposed_real_wage_log_change: float | None


@dataclass(frozen=True)
class EndpointSensitivitySummary:
    """Full endpoint identity using a non-locked employee denominator for sensitivity only."""

    country: str
    start_year: int
    end_year: int
    sensitivity_denominator: str
    denominator_concept_matches_locked_specification: bool
    publication_eligible: bool
    observed_real_compensation_per_employee_log_change: float
    observed_real_compensation_per_employee_level_change_pct: float
    real_gdp_log_contribution: float
    labour_share_log_contribution: float
    employment_log_contribution: float
    relative_price_log_contribution: float
    decomposed_real_wage_log_change: float
    max_abs_identity_residual: float


def sha256_file(path: Path) -> str:
    """Return a SHA-256 digest for ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize exactly two positive endpoint observations."""
    missing = set(INPUT_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Missing endpoint decomposition columns: {sorted(missing)}")
    if len(frame) != 2:
        raise ValueError("Endpoint decomposition requires exactly two observations.")

    data = frame.loc[:, list(INPUT_COLUMNS)].copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    if data["year"].isna().any():
        raise ValueError("Endpoint years must be numeric.")
    if not np.all(np.equal(np.mod(data["year"], 1), 0)):
        raise ValueError("Endpoint years must be integers.")
    data["year"] = data["year"].astype(int)
    data = data.sort_values("year").reset_index(drop=True)
    if data["year"].duplicated().any() or int(data.loc[0, "year"]) >= int(data.loc[1, "year"]):
        raise ValueError("Endpoint years must be unique and increasing.")

    numeric = [column for column in INPUT_COLUMNS if column != "year"]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    values = data[numeric].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Endpoint decomposition levels must be finite numeric values.")
    if (values <= 0.0).any():
        raise ValueError("Endpoint decomposition levels must be strictly positive.")
    return data


def _to_locked_frame(data: pd.DataFrame) -> pd.DataFrame:
    """Map endpoint inputs onto the locked accounting-decomposition schema.

    ``real_gdp`` is reconstructed from current-price GDP and its deflator. Fixed unit scale factors
    cancel from the log differences used by the identity.
    """
    return pd.DataFrame(
        {
            "year": data["year"],
            "nominal_gdp": data["nominal_gdp_m_eur"],
            "real_gdp": data["nominal_gdp_m_eur"] / data["gdp_deflator"],
            "employee_compensation": data["employee_compensation_m_eur"],
            "employees": data["employees_lfs_thousand"],
            "consumer_price_index": data["hicp_annual_avg"],
        }
    )


def calculate_endpoint_decomposition(
    frame: pd.DataFrame,
    *,
    country: str = "PRT",
) -> tuple[pd.DataFrame, EndpointPartialSummary, pd.DataFrame, EndpointSensitivitySummary]:
    """Calculate the locked partial identity and a labelled LFS-denominator sensitivity.

    The partial result deliberately leaves the employment term and total unresolved because the
    locked denominator is Eurostat national-accounts employees, domestic concept (``SAL_DC``).
    The supplied ``employees_lfs_thousand`` column is used only for the separate sensitivity.
    """
    data = _validate_input(frame)
    locked_input = _to_locked_frame(data)
    decomposed = decompose_real_wage_growth(locked_input)
    summary = summarise_decomposition(decomposed, country=country)

    start = data.iloc[0]
    end = data.iloc[1]
    start_labour_share = float(start["employee_compensation_m_eur"] / start["nominal_gdp_m_eur"])
    end_labour_share = float(end["employee_compensation_m_eur"] / end["nominal_gdp_m_eur"])

    partial_rows = [
        {
            "component": "real_gdp_component",
            "log_point_contribution": summary.real_gdp_log_contribution,
            "status": "available",
            "interpretation": "Change in real GDP over the endpoint interval.",
        },
        {
            "component": "labour_share_component",
            "log_point_contribution": summary.labour_share_log_contribution,
            "status": "available",
            "interpretation": "Change in raw D.1 compensation share of nominal GDP.",
        },
        {
            "component": "employment_component",
            "log_point_contribution": math.nan,
            "status": "missing_locked_sal_dc",
            "interpretation": "Requires Eurostat national-accounts employees, domestic concept (SAL_DC).",
        },
        {
            "component": "relative_price_component",
            "log_point_contribution": summary.relative_price_log_contribution,
            "status": "available",
            "interpretation": "GDP-deflator inflation minus HICP inflation.",
        },
    ]
    partial = pd.DataFrame(partial_rows)

    partial_summary = EndpointPartialSummary(
        country=country,
        start_year=int(start["year"]),
        end_year=int(end["year"]),
        locked_employee_concept="Eurostat national-accounts employees, domestic concept (SAL_DC)",
        locked_sal_dc_status="incomplete_missing_start_endpoint",
        publication_eligible=False,
        start_labour_share=start_labour_share,
        end_labour_share=end_labour_share,
        labour_share_level_change_pp=100.0 * (end_labour_share - start_labour_share),
        real_gdp_log_contribution=summary.real_gdp_log_contribution,
        labour_share_log_contribution=summary.labour_share_log_contribution,
        employment_log_contribution=None,
        relative_price_log_contribution=summary.relative_price_log_contribution,
        decomposed_real_wage_log_change=None,
    )

    growth_row = decomposed.dropna(subset=["observed_real_wage_growth"]).iloc[-1]
    sensitivity = pd.DataFrame(
        [
            {
                "component": component,
                "log_point_contribution": float(growth_row[component]),
                "status": "sensitivity_only",
            }
            for component in PARTIAL_COMPONENT_ORDER
        ]
    )
    sensitivity.loc[len(sensitivity)] = {
        "component": "decomposed_real_wage_log_change",
        "log_point_contribution": summary.decomposed_real_wage_log_change,
        "status": "sensitivity_only",
    }
    sensitivity.loc[len(sensitivity)] = {
        "component": "observed_real_wage_log_change",
        "log_point_contribution": summary.observed_real_wage_log_change,
        "status": "sensitivity_only",
    }
    sensitivity.loc[len(sensitivity)] = {
        "component": "identity_residual",
        "log_point_contribution": float(growth_row["identity_residual"]),
        "status": "numerical_check",
    }

    sensitivity_summary = EndpointSensitivitySummary(
        country=country,
        start_year=int(start["year"]),
        end_year=int(end["year"]),
        sensitivity_denominator="LFS employees (national/resident concept), not SAL_DC",
        denominator_concept_matches_locked_specification=False,
        publication_eligible=False,
        observed_real_compensation_per_employee_log_change=summary.observed_real_wage_log_change,
        observed_real_compensation_per_employee_level_change_pct=(
            100.0 * math.expm1(summary.observed_real_wage_log_change)
        ),
        real_gdp_log_contribution=summary.real_gdp_log_contribution,
        labour_share_log_contribution=summary.labour_share_log_contribution,
        employment_log_contribution=summary.employment_log_contribution,
        relative_price_log_contribution=summary.relative_price_log_contribution,
        decomposed_real_wage_log_change=summary.decomposed_real_wage_log_change,
        max_abs_identity_residual=summary.max_abs_identity_residual,
    )
    return partial, partial_summary, sensitivity, sensitivity_summary


def write_outputs(
    input_path: Path,
    output_dir: Path,
    *,
    country: str = "PRT",
) -> dict[str, Path]:
    """Calculate endpoint decomposition outputs and bind them with a small JSON summary."""
    frame = pd.read_csv(input_path)
    partial, partial_summary, sensitivity, sensitivity_summary = calculate_endpoint_decomposition(
        frame,
        country=country,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    years = f"{partial_summary.start_year}_{partial_summary.end_year}"
    partial_path = output_dir / f"portugal_endpoint_decomposition_partial_{years}.csv"
    sensitivity_path = output_dir / f"portugal_endpoint_decomposition_lfs_sensitivity_{years}.csv"
    summary_path = output_dir / f"portugal_endpoint_decomposition_{years}.json"

    partial.to_csv(partial_path, index=False)
    sensitivity.to_csv(sensitivity_path, index=False)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "analysis_class": "exploratory_endpoint_accounting_decomposition",
        "publication_eligible": False,
        "locked_decomposition": asdict(partial_summary),
        "lfs_denominator_sensitivity": asdict(sensitivity_summary),
        "interpretation_limits": [
            "Endpoint decomposition telescopes over the full interval and does not identify timing.",
            "D.1 includes employer social contributions and is not take-home pay.",
            "The raw D.1/GDP labour share is not adjusted for self-employed labour income.",
            "The LFS denominator sensitivity does not match the locked SAL_DC domestic concept.",
            "No causal allocation claim is authorized.",
        ],
        "inputs": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
        },
    }
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "partial_csv": partial_path,
        "lfs_sensitivity_csv": sensitivity_path,
        "summary_json": summary_path,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Two-row endpoint input CSV.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for outputs.")
    parser.add_argument("--country", default="PRT", help="Country code stored in summaries.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the endpoint decomposition CLI."""
    args = build_parser().parse_args(argv)
    outputs = write_outputs(args.input, args.output_dir, country=args.country)
    for key, path in outputs.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
