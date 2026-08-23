"""Build an exploratory annual labour-income decomposition for Portugal.

This helper is intentionally outside :mod:`wage_transmission` so it cannot alter the
pre-results analysis-source hash. It applies the already-locked accounting identity to an
annual input table and keeps the publication denominator contract explicit.

The locked denominator is Eurostat national-accounts employees in the domestic concept
(``SAL_DC``). If that series is absent or incomplete, employee-independent components are still
computed, while the employment term and total locked identity remain unavailable. A complete
Labour Force Survey (LFS) employee series may be supplied as a separately labelled sensitivity;
it is never treated as equivalent to ``SAL_DC``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from wage_transmission.decomposition import (
    COMPONENT_COLUMNS,
    decompose_real_wage_growth,
    summarise_decomposition,
)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "year",
    "nominal_gdp_m_eur",
    "employee_compensation_m_eur",
    "gdp_deflator",
    "hicp_annual_avg",
    "employees_lfs_thousand",
)
OPTIONAL_SAL_DC_COLUMN = "employees_sal_dc_thousand"
LOCKED_EMPLOYEE_CONCEPT = "Eurostat national-accounts employees, domestic concept (SAL_DC)"


@dataclass(frozen=True)
class AnnualDecompositionSummary:
    """Machine-readable status and cumulative annual-decomposition contributions."""

    country: str
    start_year: int
    end_year: int
    n_level_observations: int
    n_growth_observations: int
    publication_eligible: bool
    employee_independent_terms_complete: bool
    locked_employee_concept: str
    locked_sal_dc_status: str
    locked_sal_dc_level_observations: int
    locked_sal_dc_complete: bool
    lfs_sensitivity_complete: bool
    cumulative_real_gdp_log_contribution: float
    cumulative_labour_share_log_contribution: float
    cumulative_relative_price_log_contribution: float
    cumulative_locked_employment_log_contribution: float | None
    cumulative_locked_real_compensation_per_employee_log_change: float | None
    cumulative_lfs_employment_log_contribution: float
    cumulative_lfs_real_compensation_per_employee_log_change: float
    cumulative_lfs_real_compensation_per_employee_level_change_pct: float
    lfs_max_abs_identity_residual: float


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a continuous annual input table while allowing missing ``SAL_DC`` levels."""
    missing = set(REQUIRED_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Missing annual decomposition columns: {sorted(missing)}")
    if len(frame) < 2:
        raise ValueError("Annual decomposition requires at least two annual observations.")

    columns = list(REQUIRED_COLUMNS)
    if OPTIONAL_SAL_DC_COLUMN in frame.columns:
        columns.append(OPTIONAL_SAL_DC_COLUMN)
    data = frame.loc[:, columns].copy()

    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    if data["year"].isna().any() or not np.all(np.equal(np.mod(data["year"], 1), 0)):
        raise ValueError("Annual decomposition years must be integer-valued.")
    data["year"] = data["year"].astype(int)
    data = data.sort_values("year").reset_index(drop=True)
    if data["year"].duplicated().any():
        raise ValueError("Annual decomposition years must be unique.")

    expected = np.arange(int(data["year"].min()), int(data["year"].max()) + 1)
    if not np.array_equal(data["year"].to_numpy(), expected):
        raise ValueError("Annual decomposition years must form a continuous sequence.")

    numeric_required = [column for column in REQUIRED_COLUMNS if column != "year"]
    for column in numeric_required:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    required_values = data[numeric_required].to_numpy(dtype=float)
    if not np.isfinite(required_values).all():
        raise ValueError("Required annual decomposition levels must be finite numeric values.")
    if (required_values <= 0.0).any():
        raise ValueError("Required annual decomposition levels must be strictly positive.")

    if OPTIONAL_SAL_DC_COLUMN in data.columns:
        data[OPTIONAL_SAL_DC_COLUMN] = pd.to_numeric(
            data[OPTIONAL_SAL_DC_COLUMN], errors="coerce"
        )
        observed_sal_dc = data[OPTIONAL_SAL_DC_COLUMN].dropna()
        if (observed_sal_dc <= 0.0).any() or not np.isfinite(observed_sal_dc).all():
            raise ValueError("Observed SAL_DC levels must be finite and strictly positive.")
    else:
        data[OPTIONAL_SAL_DC_COLUMN] = math.nan
    return data


def _locked_schema(data: pd.DataFrame, employees: pd.Series) -> pd.DataFrame:
    """Map reporting inputs onto the locked decomposition schema."""
    return pd.DataFrame(
        {
            "year": data["year"],
            "nominal_gdp": data["nominal_gdp_m_eur"],
            "real_gdp": data["nominal_gdp_m_eur"] / data["gdp_deflator"],
            "employee_compensation": data["employee_compensation_m_eur"],
            "employees": employees,
            "consumer_price_index": data["hicp_annual_avg"],
        }
    )


def _partial_from_lfs_decomposition(
    data: pd.DataFrame,
    lfs_decomposed: pd.DataFrame,
) -> pd.DataFrame:
    """Retain only employee-independent locked terms until exact ``SAL_DC`` is available."""
    partial = pd.DataFrame(
        {
            "year": data["year"],
            "real_gdp_component": lfs_decomposed["real_gdp_component"],
            "labour_share_component": lfs_decomposed["labour_share_component"],
            "employment_component": math.nan,
            "relative_price_component": lfs_decomposed["relative_price_component"],
            "decomposed_real_wage_growth": math.nan,
        }
    )
    partial["employment_status"] = "missing_locked_sal_dc"
    partial.loc[partial.index[0], "employment_status"] = "not_applicable_first_level"
    partial["publication_eligible"] = False
    return partial


def _locked_decomposition_if_complete(data: pd.DataFrame) -> pd.DataFrame | None:
    """Return the locked decomposition only when every ``SAL_DC`` level is present."""
    sal_dc = data[OPTIONAL_SAL_DC_COLUMN]
    if sal_dc.isna().any():
        return None
    return decompose_real_wage_growth(_locked_schema(data, sal_dc))


def calculate_annual_decomposition(
    frame: pd.DataFrame,
    *,
    country: str = "PRT",
) -> tuple[pd.DataFrame, pd.DataFrame, AnnualDecompositionSummary]:
    """Calculate annual locked/partial terms plus a separate LFS-denominator sensitivity.

    Returns
    -------
    partial_or_locked:
        Annual locked decomposition when complete ``SAL_DC`` is supplied; otherwise an explicitly
        incomplete table containing only the employee-independent components.
    lfs_sensitivity:
        Full accounting identity using LFS employees, labelled as a concept-mismatched sensitivity.
    summary:
        Cumulative contributions and publication-eligibility status.
    """
    data = _validate_input(frame)

    lfs_decomposed = decompose_real_wage_growth(
        _locked_schema(data, data["employees_lfs_thousand"])
    )
    lfs_summary = summarise_decomposition(lfs_decomposed, country=country)
    lfs_sensitivity = lfs_decomposed.copy()
    lfs_sensitivity["denominator_concept"] = (
        "LFS employees (national/resident concept), not SAL_DC"
    )
    lfs_sensitivity["denominator_concept_matches_locked_specification"] = False
    lfs_sensitivity["publication_eligible"] = False

    locked_decomposed = _locked_decomposition_if_complete(data)
    sal_dc_observations = int(data[OPTIONAL_SAL_DC_COLUMN].notna().sum())
    locked_complete = locked_decomposed is not None

    if locked_complete:
        assert locked_decomposed is not None
        locked_output = locked_decomposed.copy()
        locked_output["employment_status"] = "available_locked_sal_dc"
        locked_output.loc[locked_output.index[0], "employment_status"] = "not_applicable_first_level"
        locked_output["publication_eligible"] = False
        locked_summary = summarise_decomposition(locked_decomposed, country=country)
        locked_status = "complete_indexed_exploratory_only"
        locked_emp = locked_summary.employment_log_contribution
        locked_total = locked_summary.decomposed_real_wage_log_change
    else:
        locked_output = _partial_from_lfs_decomposition(data, lfs_decomposed)
        locked_status = "incomplete_annual_sal_dc_vector_unavailable"
        locked_emp = None
        locked_total = None

    summary = AnnualDecompositionSummary(
        country=country,
        start_year=int(data["year"].min()),
        end_year=int(data["year"].max()),
        n_level_observations=int(len(data)),
        n_growth_observations=int(len(data) - 1),
        publication_eligible=False,
        employee_independent_terms_complete=True,
        locked_employee_concept=LOCKED_EMPLOYEE_CONCEPT,
        locked_sal_dc_status=locked_status,
        locked_sal_dc_level_observations=sal_dc_observations,
        locked_sal_dc_complete=locked_complete,
        lfs_sensitivity_complete=True,
        cumulative_real_gdp_log_contribution=lfs_summary.real_gdp_log_contribution,
        cumulative_labour_share_log_contribution=lfs_summary.labour_share_log_contribution,
        cumulative_relative_price_log_contribution=lfs_summary.relative_price_log_contribution,
        cumulative_locked_employment_log_contribution=locked_emp,
        cumulative_locked_real_compensation_per_employee_log_change=locked_total,
        cumulative_lfs_employment_log_contribution=lfs_summary.employment_log_contribution,
        cumulative_lfs_real_compensation_per_employee_log_change=(
            lfs_summary.observed_real_wage_log_change
        ),
        cumulative_lfs_real_compensation_per_employee_level_change_pct=(
            100.0 * math.expm1(lfs_summary.observed_real_wage_log_change)
        ),
        lfs_max_abs_identity_residual=lfs_summary.max_abs_identity_residual,
    )
    return locked_output, lfs_sensitivity, summary


def write_outputs(
    frame: pd.DataFrame,
    *,
    output_dir: Path,
    country: str = "PRT",
) -> dict[str, Path]:
    """Write deterministic CSV/JSON artifacts for the annual exploratory decomposition."""
    output_dir.mkdir(parents=True, exist_ok=True)
    locked, lfs, summary = calculate_annual_decomposition(frame, country=country)
    start, end = summary.start_year, summary.end_year

    locked_path = output_dir / f"portugal_annual_decomposition_partial_{start}_{end}.csv"
    lfs_path = output_dir / f"portugal_annual_decomposition_lfs_sensitivity_{start}_{end}.csv"
    summary_path = output_dir / f"portugal_annual_decomposition_{start}_{end}.json"
    locked.to_csv(locked_path, index=False)
    lfs.to_csv(lfs_path, index=False)
    summary_path.write_text(
        json.dumps(asdict(summary), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"locked": locked_path, "lfs": lfs_path, "summary": summary_path}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Annual level input CSV.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Artifact directory.")
    parser.add_argument("--country", default="PRT", help="Country code for metadata.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = _parser().parse_args(argv)
    frame = pd.read_csv(args.input)
    outputs = write_outputs(frame, output_dir=args.output_dir, country=args.country)
    payload: dict[str, Any] = {
        name: {"path": str(path), "sha256": sha256_file(path)}
        for name, path in outputs.items()
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
