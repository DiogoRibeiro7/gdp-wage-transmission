"""Build an exploratory Portugal wage-distribution panel from Quadros de Pessoal.

This reporting helper intentionally lives outside :mod:`wage_transmission`, preserving the
pre-source-freeze analysis hash. It stitches two overlapping official GEP/MTSSS chronological
series, validates their bridge year, deflates October monthly gains with October HICP, and
summarises distributional change across the mean, median, and decile-average gains.

The resulting evidence is exploratory only. The GEP/MTSSS population is full-time employees
with complete remuneration in the October reference period, on mainland Portugal. It is not
interchangeable with the OECD annual-average wage concept used in the locked transmission model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DECILE_COLUMNS: tuple[str, ...] = tuple(f"d{i}_mean_gain_eur" for i in range(1, 11))
CORE_COLUMNS: tuple[str, ...] = (
    "year",
    "employees_tco",
    "mean_gain_eur",
    "median_gain_eur",
    *DECILE_COLUMNS,
)
PUBLICATION_ELIGIBLE = False
SOURCE_URLS: dict[str, str] = {
    "historical": "https://www.gep.mtsss.gov.pt/documents/10182/10928/seriesqp_2002_2014.pdf/6c4c40c4-45ad-40c7-b4f9-7b541c69c14f",
    "current": "https://www.gep.mtsss.gov.pt/documents/10182/10928/serieqp_2014_2024.pdf/cf5306a5-4dbf-4eb6-b6c2-548326d670e6",
    "hicp": "https://fred.stlouisfed.org/data/CP0000PTM086NEST",
}
POPULATION_DEFINITION = (
    "Mainland Portugal; full-time employees with complete remuneration in October "
    "(Quadros de Pessoal)."
)


@dataclass(frozen=True)
class DistributionSummary:
    """Machine-readable summary of long-run wage-distribution change."""

    country: str
    geography: str
    start_year: int
    end_year: int
    n_years: int
    publication_eligible: bool
    population_definition: str
    nominal_mean_growth_pct: float
    nominal_median_growth_pct: float
    real_mean_growth_pct: float
    real_median_growth_pct: float
    real_d1_growth_pct: float
    real_d5_growth_pct: float
    real_d10_growth_pct: float
    mean_median_ratio_start: float
    mean_median_ratio_end: float
    d10_d1_ratio_start: float
    d10_d1_ratio_end: float
    d9_d1_ratio_start: float
    d9_d1_ratio_end: float
    d10_d5_ratio_start: float
    d10_d5_ratio_end: float
    median_mean_share_start: float
    median_mean_share_end: float
    top_bottom_real_growth_gap_pp: float
    maximum_decile_mean_reconstruction_error_eur: float


@dataclass(frozen=True)
class ProductivityEndpointComparison:
    """Common-endpoint comparison between GDP/person employed and wage-distribution positions."""

    country: str
    start_year: int
    end_year: int
    publication_eligible: bool
    productivity_per_worker_growth_pct: float
    real_mean_gain_growth_pct: float
    real_median_gain_growth_pct: float
    real_d1_gain_growth_pct: float
    real_d5_gain_growth_pct: float
    real_d10_gain_growth_pct: float
    mean_minus_productivity_growth_pp: float
    median_minus_productivity_growth_pp: float
    d1_minus_productivity_growth_pp: float
    d10_minus_productivity_growth_pp: float


def compare_productivity_endpoints(
    panel: pd.DataFrame,
    productivity: pd.DataFrame,
) -> ProductivityEndpointComparison:
    """Compare common endpoint growth without treating the two source concepts as identical."""
    required = {"year", "productivity_per_worker"}
    missing = required.difference(productivity.columns)
    if missing:
        raise ValueError(f"Productivity input is missing columns: {sorted(missing)}")
    prod = productivity.loc[:, ["year", "productivity_per_worker"]].copy()
    prod["year"] = pd.to_numeric(prod["year"], errors="coerce")
    prod["productivity_per_worker"] = pd.to_numeric(
        prod["productivity_per_worker"], errors="coerce"
    )
    if prod.isna().any().any() or (prod["productivity_per_worker"] <= 0.0).any():
        raise ValueError(
            "Productivity endpoint input must contain positive finite year/value pairs."
        )
    prod["year"] = prod["year"].astype(int)
    merged = panel.merge(prod, on="year", how="inner", validate="one_to_one").sort_values("year")
    if len(merged) < 2:
        raise ValueError("At least two common productivity/distribution years are required.")
    start = merged.iloc[0]
    end = merged.iloc[-1]
    prod_growth = _growth_pct(
        float(start["productivity_per_worker"]), float(end["productivity_per_worker"])
    )

    def real_growth(column: str) -> float:
        return _growth_pct(float(start[column]), float(end[column]))

    mean_growth = real_growth("real_mean_gain_2025_eur")
    median_growth = real_growth("real_median_gain_2025_eur")
    d1_growth = real_growth("real_d1_mean_gain_2025_eur")
    d5_growth = real_growth("real_d5_mean_gain_2025_eur")
    d10_growth = real_growth("real_d10_mean_gain_2025_eur")
    return ProductivityEndpointComparison(
        country="PRT",
        start_year=int(start["year"]),
        end_year=int(end["year"]),
        publication_eligible=False,
        productivity_per_worker_growth_pct=prod_growth,
        real_mean_gain_growth_pct=mean_growth,
        real_median_gain_growth_pct=median_growth,
        real_d1_gain_growth_pct=d1_growth,
        real_d5_gain_growth_pct=d5_growth,
        real_d10_gain_growth_pct=d10_growth,
        mean_minus_productivity_growth_pp=mean_growth - prod_growth,
        median_minus_productivity_growth_pp=median_growth - prod_growth,
        d1_minus_productivity_growth_pp=d1_growth - prod_growth,
        d10_minus_productivity_growth_pp=d10_growth - prod_growth,
    )


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_distribution_frame(frame: pd.DataFrame, *, label: str) -> pd.DataFrame:
    """Validate one chronological Quadros de Pessoal source table."""
    missing = set(CORE_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"{label} is missing columns: {sorted(missing)}")

    data = frame.loc[:, CORE_COLUMNS].copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    if data["year"].isna().any() or not np.all(np.equal(np.mod(data["year"], 1), 0)):
        raise ValueError(f"{label} years must be integer-valued.")
    data["year"] = data["year"].astype(int)
    data = data.sort_values("year").reset_index(drop=True)
    if data["year"].duplicated().any():
        raise ValueError(f"{label} years must be unique.")

    expected = np.arange(int(data["year"].min()), int(data["year"].max()) + 1)
    if not np.array_equal(data["year"].to_numpy(), expected):
        raise ValueError(f"{label} years must be contiguous.")

    numeric = [column for column in CORE_COLUMNS if column != "year"]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    values = data[numeric].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError(f"{label} wage/count values must be finite and strictly positive.")

    # Decile groups are approximately equally sized, so their simple average should reconstruct
    # the published mean to within the rounding of the decile-average table.
    reconstructed = data[list(DECILE_COLUMNS)].mean(axis=1)
    error = (reconstructed - data["mean_gain_eur"]).abs()
    if float(error.max()) > 2.0:
        raise ValueError(
            f"{label} decile means fail to reconstruct the published mean; max error={error.max():.3f}."
        )
    return data


def stitch_official_series(
    historical: pd.DataFrame,
    current: pd.DataFrame,
    *,
    bridge_year: int = 2014,
) -> pd.DataFrame:
    """Stitch overlapping historical/current official tables after a strict bridge-year audit."""
    old = _validate_distribution_frame(historical, label="historical source")
    new = _validate_distribution_frame(current, label="current source")

    old_bridge = old.loc[old["year"] == bridge_year]
    new_bridge = new.loc[new["year"] == bridge_year]
    if len(old_bridge) != 1 or len(new_bridge) != 1:
        raise ValueError(f"Both sources must contain bridge year {bridge_year} exactly once.")

    for column in CORE_COLUMNS[1:]:
        left = float(old_bridge.iloc[0][column])
        right = float(new_bridge.iloc[0][column])
        if not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"Official source mismatch at {bridge_year} for {column}: {left} != {right}."
            )

    if int(old["year"].max()) != bridge_year or int(new["year"].min()) != bridge_year:
        raise ValueError("The configured sources must meet exactly at the bridge year.")

    combined = pd.concat([old.loc[old["year"] < bridge_year], new], ignore_index=True)
    expected = np.arange(int(combined["year"].min()), int(combined["year"].max()) + 1)
    if not np.array_equal(combined["year"].to_numpy(), expected):
        raise ValueError("Stitched distribution series must be contiguous.")
    return combined


def october_hicp(monthly_hicp: pd.DataFrame) -> pd.DataFrame:
    """Return one October HICP observation per year from the monthly 2025=100 series."""
    required = {"date", "hicp_index_2025_100"}
    missing = required.difference(monthly_hicp.columns)
    if missing:
        raise ValueError(f"HICP input is missing columns: {sorted(missing)}")

    data = monthly_hicp.loc[:, ["date", "hicp_index_2025_100"]].copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["hicp_index_2025_100"] = pd.to_numeric(data["hicp_index_2025_100"], errors="coerce")
    if data["date"].isna().any() or data["hicp_index_2025_100"].isna().any():
        raise ValueError("HICP dates and values must be parseable and complete.")
    if (data["hicp_index_2025_100"] <= 0.0).any():
        raise ValueError("HICP values must be strictly positive.")

    october = data.loc[data["date"].dt.month == 10].copy()
    october["year"] = october["date"].dt.year.astype(int)
    if october["year"].duplicated().any():
        raise ValueError("HICP input contains duplicate October observations.")
    return october.loc[:, ["year", "hicp_index_2025_100"]].sort_values("year")


def build_distribution_panel(
    historical: pd.DataFrame,
    current: pd.DataFrame,
    monthly_hicp: pd.DataFrame,
) -> pd.DataFrame:
    """Build nominal and October-HICP-deflated wage-distribution measures."""
    wages = stitch_official_series(historical, current)
    prices = october_hicp(monthly_hicp)
    panel = wages.merge(prices, on="year", how="left", validate="one_to_one")
    if panel["hicp_index_2025_100"].isna().any():
        missing_years = panel.loc[panel["hicp_index_2025_100"].isna(), "year"].tolist()
        raise ValueError(f"Missing October HICP for wage years: {missing_years}")

    nominal_columns = ["mean_gain_eur", "median_gain_eur", *DECILE_COLUMNS]
    for column in nominal_columns:
        real_column = f"real_{column.removesuffix('_eur')}_2025_eur"
        panel[real_column] = panel[column] * 100.0 / panel["hicp_index_2025_100"]

    panel["mean_median_ratio"] = panel["mean_gain_eur"] / panel["median_gain_eur"]
    panel["median_mean_share"] = panel["median_gain_eur"] / panel["mean_gain_eur"]
    panel["d10_d1_ratio"] = panel["d10_mean_gain_eur"] / panel["d1_mean_gain_eur"]
    panel["d9_d1_ratio"] = panel["d9_mean_gain_eur"] / panel["d1_mean_gain_eur"]
    panel["d10_d5_ratio"] = panel["d10_mean_gain_eur"] / panel["d5_mean_gain_eur"]
    panel["decile_mean_reconstruction_eur"] = panel[list(DECILE_COLUMNS)].mean(axis=1)
    panel["decile_mean_reconstruction_error_eur"] = (
        panel["decile_mean_reconstruction_eur"] - panel["mean_gain_eur"]
    )
    panel["population_definition"] = POPULATION_DEFINITION
    panel["publication_eligible"] = PUBLICATION_ELIGIBLE
    return panel


def _growth_pct(start: float, end: float) -> float:
    """Return level growth in percentage points."""
    return 100.0 * (end / start - 1.0)


def summarise_distribution(panel: pd.DataFrame) -> DistributionSummary:
    """Summarise long-run nominal, real, and distribution-ratio change."""
    if panel.empty:
        raise ValueError("Distribution panel cannot be empty.")
    data = panel.sort_values("year").reset_index(drop=True)
    start = data.iloc[0]
    end = data.iloc[-1]

    real_mean = "real_mean_gain_2025_eur"
    real_median = "real_median_gain_2025_eur"
    real_d1 = "real_d1_mean_gain_2025_eur"
    real_d5 = "real_d5_mean_gain_2025_eur"
    real_d10 = "real_d10_mean_gain_2025_eur"
    d1_growth = _growth_pct(float(start[real_d1]), float(end[real_d1]))
    d10_growth = _growth_pct(float(start[real_d10]), float(end[real_d10]))

    return DistributionSummary(
        country="PRT",
        geography="Mainland Portugal (Continente)",
        start_year=int(start["year"]),
        end_year=int(end["year"]),
        n_years=len(data),
        publication_eligible=False,
        population_definition=POPULATION_DEFINITION,
        nominal_mean_growth_pct=_growth_pct(
            float(start["mean_gain_eur"]), float(end["mean_gain_eur"])
        ),
        nominal_median_growth_pct=_growth_pct(
            float(start["median_gain_eur"]), float(end["median_gain_eur"])
        ),
        real_mean_growth_pct=_growth_pct(float(start[real_mean]), float(end[real_mean])),
        real_median_growth_pct=_growth_pct(float(start[real_median]), float(end[real_median])),
        real_d1_growth_pct=d1_growth,
        real_d5_growth_pct=_growth_pct(float(start[real_d5]), float(end[real_d5])),
        real_d10_growth_pct=d10_growth,
        mean_median_ratio_start=float(start["mean_median_ratio"]),
        mean_median_ratio_end=float(end["mean_median_ratio"]),
        d10_d1_ratio_start=float(start["d10_d1_ratio"]),
        d10_d1_ratio_end=float(end["d10_d1_ratio"]),
        d9_d1_ratio_start=float(start["d9_d1_ratio"]),
        d9_d1_ratio_end=float(end["d9_d1_ratio"]),
        d10_d5_ratio_start=float(start["d10_d5_ratio"]),
        d10_d5_ratio_end=float(end["d10_d5_ratio"]),
        median_mean_share_start=float(start["median_mean_share"]),
        median_mean_share_end=float(end["median_mean_share"]),
        top_bottom_real_growth_gap_pp=d10_growth - d1_growth,
        maximum_decile_mean_reconstruction_error_eur=float(
            data["decile_mean_reconstruction_error_eur"].abs().max()
        ),
    )


def decile_growth_table(panel: pd.DataFrame) -> pd.DataFrame:
    """Return cumulative nominal and real growth by mean, median and decile-average gain."""
    data = panel.sort_values("year").reset_index(drop=True)
    start = data.iloc[0]
    end = data.iloc[-1]
    measures: list[tuple[str, str, str]] = [
        ("mean", "mean_gain_eur", "real_mean_gain_2025_eur"),
        ("median", "median_gain_eur", "real_median_gain_2025_eur"),
    ]
    measures.extend(
        (
            f"d{i}",
            f"d{i}_mean_gain_eur",
            f"real_d{i}_mean_gain_2025_eur",
        )
        for i in range(1, 11)
    )
    rows: list[dict[str, float | int | str | bool]] = []
    for label, nominal, real in measures:
        rows.append(
            {
                "measure": label,
                "start_year": int(start["year"]),
                "end_year": int(end["year"]),
                "start_nominal_eur": float(start[nominal]),
                "end_nominal_eur": float(end[nominal]),
                "nominal_growth_pct": _growth_pct(float(start[nominal]), float(end[nominal])),
                "start_real_2025_eur": float(start[real]),
                "end_real_2025_eur": float(end[real]),
                "real_growth_pct": _growth_pct(float(start[real]), float(end[real])),
                "publication_eligible": False,
            }
        )
    return pd.DataFrame(rows)


def _plot_real_indices(panel: pd.DataFrame, output: Path) -> None:
    """Plot cumulative real wage indices for selected distribution positions."""
    data = panel.sort_values("year").copy()
    series = {
        "Mean": "real_mean_gain_2025_eur",
        "Median": "real_median_gain_2025_eur",
        "D1 mean": "real_d1_mean_gain_2025_eur",
        "D5 mean": "real_d5_mean_gain_2025_eur",
        "D10 mean": "real_d10_mean_gain_2025_eur",
    }
    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    for label, column in series.items():
        indexed = 100.0 * data[column] / float(data[column].iloc[0])
        ax.plot(data["year"], indexed, label=label)
    ax.axhline(100.0, linewidth=0.8)
    ax.set_xlabel("Year")
    ax.set_ylabel("Real gain index (2002 = 100)")
    ax.set_title("Portugal monthly gain by distribution position, real 2025 euros")
    ax.legend(ncol=2)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _plot_inequality_ratios(panel: pd.DataFrame, output: Path) -> None:
    """Plot simple within-employee gain-distribution ratios."""
    data = panel.sort_values("year").copy()
    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    ax.plot(data["year"], data["d10_d1_ratio"], label="D10 / D1")
    ax.plot(data["year"], data["d10_d5_ratio"], label="D10 / D5")
    ax.plot(data["year"], data["mean_median_ratio"], label="Mean / median")
    ax.set_xlabel("Year")
    ax.set_ylabel("Ratio")
    ax.set_title("Portugal monthly gain distribution ratios")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def write_outputs(
    historical_path: Path,
    current_path: Path,
    hicp_path: Path,
    output_dir: Path,
    productivity_path: Path | None = None,
) -> DistributionSummary:
    """Build the exploratory panel and write all machine-readable/figure outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    historical = pd.read_csv(historical_path)
    current = pd.read_csv(current_path)
    hicp = pd.read_csv(hicp_path)
    panel = build_distribution_panel(historical, current, hicp)
    summary = summarise_distribution(panel)
    growth = decile_growth_table(panel)

    panel_path = output_dir / "portugal_wage_distribution_2002_2024.csv"
    growth_path = output_dir / "portugal_wage_distribution_growth_2002_2024.csv"
    summary_path = output_dir / "portugal_wage_distribution_summary_2002_2024.json"
    panel.to_csv(panel_path, index=False)
    growth.to_csv(growth_path, index=False)
    summary_path.write_text(json.dumps(asdict(summary), indent=2, sort_keys=True) + "\n")

    _plot_real_indices(panel, output_dir / "portugal_wage_distribution_real_indices.png")
    _plot_inequality_ratios(panel, output_dir / "portugal_wage_distribution_ratios.png")

    productivity_output: Path | None = None
    productivity_comparison: ProductivityEndpointComparison | None = None
    if productivity_path is not None:
        productivity_frame = pd.read_csv(productivity_path)
        productivity_comparison = compare_productivity_endpoints(panel, productivity_frame)
        productivity_output = (
            output_dir / "portugal_wage_distribution_productivity_endpoints_2002_2023.json"
        )
        productivity_output.write_text(
            json.dumps(asdict(productivity_comparison), indent=2, sort_keys=True) + "\n"
        )

    provenance = {
        "schema_version": 1,
        "publication_eligible": False,
        "reason": (
            "Indexed/transcribed official chronological tables are exploratory evidence; "
            "they are not untouched raw API/source-freeze payloads."
        ),
        "population_definition": POPULATION_DEFINITION,
        "bridge_year": 2014,
        "source_files": {
            str(historical_path): sha256_file(historical_path),
            str(current_path): sha256_file(current_path),
            str(hicp_path): sha256_file(hicp_path),
            **(
                {str(productivity_path): sha256_file(productivity_path)}
                if productivity_path is not None
                else {}
            ),
        },
        "source_urls": SOURCE_URLS,
        "source_notes": {
            "historical": "GEP/MTSSS Quadros de Pessoal chronological series, 2002-2014.",
            "current": "DGCP/MTSSS Quadros de Pessoal chronological series, 2014-2024.",
            "hicp": "Eurostat HICP through FRED, monthly index re-referenced to 2025=100.",
            "deflator_choice": "October HICP because Quadros de Pessoal gain is measured in October.",
        },
        "output_hashes": {
            panel_path.name: sha256_file(panel_path),
            growth_path.name: sha256_file(growth_path),
            summary_path.name: sha256_file(summary_path),
            **(
                {productivity_output.name: sha256_file(productivity_output)}
                if productivity_output is not None
                else {}
            ),
        },
    }
    (output_dir / "WAGE_DISTRIBUTION_PROVENANCE.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--hicp", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--productivity",
        type=Path,
        default=None,
        help="Optional exploratory GDP/person-employed panel for a common-endpoint comparison.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = _parser().parse_args(argv)
    summary = write_outputs(
        args.historical, args.current, args.hicp, args.output_dir, args.productivity
    )
    print(json.dumps(asdict(summary), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
