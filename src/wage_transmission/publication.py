"""Machine-generated empirical dossier for a verified result vintage."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from wage_transmission.config import PublicationConfig
from wage_transmission.data.common import sha256_bytes
from wage_transmission.reporting import write_json
from wage_transmission.version import __version__


@dataclass(frozen=True)
class PublicationDossierResult:
    """Paths produced by the publication-dossier builder."""

    core_estimates: Path
    reliability: Path
    cross_country: Path
    decomposition: Path | None
    summary_markdown: Path
    manifest: Path


def _require_mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return {str(key): item for key, item in value.items()}


def _load_json_mapping(path: Path) -> dict[str, Any]:
    return _require_mapping(json.loads(path.read_text(encoding="utf-8")), label=str(path))


def _float(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric.")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{label} must be finite.")
    return result


def _int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer.")
    return int(value)


def _bool(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean.")
    return value


def _nested(payload: Mapping[str, Any], key: str, *, label: str) -> dict[str, Any]:
    return _require_mapping(payload.get(key), label=f"{label}.{key}")


def _driver_role(driver: str, config: PublicationConfig) -> str:
    if driver == config.primary_driver:
        return "primary"
    if driver in config.secondary_drivers:
        return "secondary"
    return "unregistered"


def _summarise_model_result(
    *,
    path: Path,
    driver: str,
    config: PublicationConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = _load_json_mapping(path)
    audit = _nested(payload, "empirical_audit", label=str(path))
    reliability = _nested(payload, "reliability", label=str(path))
    distributed = _nested(payload, "distributed_lag", label=str(path))
    ecm = _nested(payload, "ecm", label=str(path))
    state = _nested(payload, "state_space", label=str(path))
    breaks = _nested(payload, "structural_breaks", label=str(path))
    asymmetry = _nested(payload, "asymmetry", label=str(path))

    estimate = _float(distributed.get("cumulative_transmission"), label="distributed estimate")
    std_error = _float(distributed.get("cumulative_std_error"), label="distributed std_error")
    p_value = _float(distributed.get("cumulative_p_value"), label="distributed p_value")
    critical = float(norm.ppf(1.0 - config.alpha / 2.0))
    ci_low = estimate - critical * std_error
    ci_high = estimate + critical * std_error

    state_elasticity = state.get("elasticity")
    state_se = state.get("elasticity_std_error")
    if not isinstance(state_elasticity, list) or not state_elasticity:
        raise ValueError("state_space.elasticity must be a non-empty list.")
    if not isinstance(state_se, list) or not state_se:
        raise ValueError("state_space.elasticity_std_error must be a non-empty list.")

    warnings = reliability.get("warnings")
    if not isinstance(warnings, list):
        raise ValueError("reliability.warnings must be a list.")
    break_years = breaks.get("break_years")
    if not isinstance(break_years, list):
        raise ValueError("structural_breaks.break_years must be a list.")

    core = {
        "driver": driver,
        "role": _driver_role(driver, config),
        "start_year": _int(audit.get("start_year"), label="start_year"),
        "end_year": _int(audit.get("end_year"), label="end_year"),
        "n_levels": _int(audit.get("n_levels"), label="n_levels"),
        "annualized_wage_growth": _float(
            audit.get("annualized_wage_growth"), label="annualized_wage_growth"
        ),
        "annualized_driver_growth": _float(
            audit.get("annualized_driver_growth"), label="annualized_driver_growth"
        ),
        "growth_correlation": _float(audit.get("growth_correlation"), label="growth_correlation"),
        "distributed_lag_cumulative": estimate,
        "distributed_lag_std_error": std_error,
        "distributed_lag_ci_low": ci_low,
        "distributed_lag_ci_high": ci_high,
        "distributed_lag_p_value": p_value,
        "distributed_lag_significant": p_value < config.alpha,
        "cointegration_supported_5pct": _bool(
            reliability.get("cointegration_supported_5pct"),
            label="cointegration_supported_5pct",
        ),
        "ecm_long_run_elasticity": _float(
            ecm.get("long_run_elasticity"), label="ecm_long_run_elasticity"
        ),
        "ecm_claim_eligible": reliability.get("ecm_long_run_interpretation") == "supported",
        "state_space_latest": _float(state_elasticity[-1], label="state_space_latest"),
        "state_space_latest_std_error": _float(state_se[-1], label="state_space_latest_std_error"),
        "state_space_claim_eligible": _bool(
            reliability.get("state_space_latest_distinguishable_from_zero_95pct"),
            label="state_space_latest_distinguishable_from_zero_95pct",
        ),
        "structural_break_years": ";".join(str(value) for value in break_years),
        "structural_break_claim_eligible": reliability.get("structural_break_interpretation")
        == "supported_for_interpretation",
        "asymmetry_positive_cumulative": _float(
            asymmetry.get("positive_cumulative"), label="asymmetry_positive_cumulative"
        ),
        "asymmetry_negative_cumulative": _float(
            asymmetry.get("negative_cumulative"), label="asymmetry_negative_cumulative"
        ),
        "asymmetry_claim_eligible": reliability.get("asymmetry_interpretation")
        == "supported_for_interpretation",
        "supported_local_projection_horizons": ";".join(
            str(value) for value in reliability.get("local_projection_supported_horizons", [])
        ),
        "warning_count": len(warnings),
        "source_result_path": str(path),
        "source_result_sha256": sha256_bytes(path.read_bytes()),
    }

    reliability_rows = [
        {
            "driver": driver,
            "model": "ecm_long_run",
            "claim_eligible": core["ecm_claim_eligible"],
            "policy": config.ecm_policy,
            "reason": str(reliability.get("ecm_long_run_interpretation")),
        },
        {
            "driver": driver,
            "model": "state_space_latest",
            "claim_eligible": core["state_space_claim_eligible"],
            "policy": config.state_space_policy,
            "reason": str(reliability.get("state_space_interpretation")),
        },
        {
            "driver": driver,
            "model": "structural_breaks",
            "claim_eligible": core["structural_break_claim_eligible"],
            "policy": config.structural_break_policy,
            "reason": str(reliability.get("structural_break_interpretation")),
        },
        {
            "driver": driver,
            "model": "asymmetry",
            "claim_eligible": core["asymmetry_claim_eligible"],
            "policy": config.asymmetry_policy,
            "reason": str(reliability.get("asymmetry_interpretation")),
        },
        {
            "driver": driver,
            "model": "local_projections",
            "claim_eligible": bool(reliability.get("local_projection_supported_horizons")),
            "policy": config.local_projection_policy,
            "reason": str(reliability.get("local_projection_interpretation")),
        },
    ]
    return core, reliability_rows


def _cross_country_summary(path: Path, *, driver: str) -> dict[str, Any]:
    frame = pd.read_csv(path)
    required = {
        "country",
        "distributed_lag_cumulative",
        "distributed_lag_cumulative_se",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Cross-country file {path} is missing columns: {sorted(missing)}")
    summary_path = path.with_suffix(".summary.json")
    if not summary_path.is_file():
        raise FileNotFoundError(summary_path)
    summary = _load_json_mapping(summary_path)
    return {
        "driver": driver,
        "n_countries": _int(summary.get("n_countries"), label="n_countries"),
        "median_cumulative_transmission": _float(
            summary.get("median_cumulative_transmission"), label="median_cumulative_transmission"
        ),
        "q25_cumulative_transmission": _float(
            summary.get("q25_cumulative_transmission"), label="q25_cumulative_transmission"
        ),
        "q75_cumulative_transmission": _float(
            summary.get("q75_cumulative_transmission"), label="q75_cumulative_transmission"
        ),
        "positive_country_share": _float(
            summary.get("positive_country_share"), label="positive_country_share"
        ),
        "random_effect_estimate": _float(
            summary.get("random_effect_estimate"), label="random_effect_estimate"
        ),
        "random_effect_std_error": _float(
            summary.get("random_effect_std_error"), label="random_effect_std_error"
        ),
        "i_squared_percent": _float(summary.get("i_squared_percent"), label="i_squared_percent"),
        "heterogeneity_interpretation": str(summary.get("interpretation")),
        "country_estimates_path": str(path),
        "country_estimates_sha256": sha256_bytes(path.read_bytes()),
        "summary_path": str(summary_path),
        "summary_sha256": sha256_bytes(summary_path.read_bytes()),
    }


def _decomposition_rows(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Decomposition summary must be a JSON list.")
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(raw):
        payload = _require_mapping(item, label=f"decomposition[{idx}]")
        row = {str(key): value for key, value in payload.items()}
        row["source_summary_path"] = str(path)
        row["source_summary_sha256"] = sha256_bytes(path.read_bytes())
        rows.append(row)
    return rows


def _write_markdown_summary(
    *,
    core: pd.DataFrame,
    cross_country: pd.DataFrame,
    config: PublicationConfig,
    output: Path,
) -> Path:
    primary = core.loc[core["driver"] == config.primary_driver]
    if len(primary) != 1:
        raise ValueError(
            f"Publication dossier requires exactly one primary driver result: {config.primary_driver}"
        )
    row = primary.iloc[0]
    lines = [
        "# Publication results dossier",
        "",
        "This file is generated mechanically from verified model outputs under the locked specification.",
        "Reduced-form estimates are descriptive and are not labelled causal.",
        "",
        "## Primary estimand",
        "",
        f"Primary driver: `{config.primary_driver}`.",
        f"Primary estimand: `{config.primary_estimand}`.",
        "",
        (
            "Cumulative distributed-lag transmission: "
            f"{float(row['distributed_lag_cumulative']):.4f} "
            f"(SE {float(row['distributed_lag_std_error']):.4f}; "
            f"{100 * (1 - config.alpha):.0f}% CI "
            f"[{float(row['distributed_lag_ci_low']):.4f}, "
            f"{float(row['distributed_lag_ci_high']):.4f}])."
        ),
        "",
        "## Reliability-gated models",
        "",
        (
            "ECM long-run interpretation: "
            + ("eligible" if bool(row["ecm_claim_eligible"]) else "not eligible")
            + "."
        ),
        (
            "Latest state-space slope: "
            + ("eligible" if bool(row["state_space_claim_eligible"]) else "not eligible")
            + "."
        ),
        (
            "Structural-break interpretation: "
            + ("eligible" if bool(row["structural_break_claim_eligible"]) else "not eligible")
            + "."
        ),
        (
            "Asymmetry interpretation: "
            + ("eligible" if bool(row["asymmetry_claim_eligible"]) else "not eligible")
            + "."
        ),
        "",
        "## Cross-country context",
        "",
    ]
    primary_cross = cross_country.loc[cross_country["driver"] == config.primary_driver]
    if len(primary_cross) == 1:
        cross = primary_cross.iloc[0]
        lines.extend(
            [
                f"Countries: {int(cross['n_countries'])}.",
                (
                    "Median country-specific cumulative transmission: "
                    f"{float(cross['median_cumulative_transmission']):.4f}."
                ),
                (
                    "Random-effects summary: "
                    f"{float(cross['random_effect_estimate']):.4f}; "
                    f"I² = {float(cross['i_squared_percent']):.1f}%."
                ),
                "",
                "The country-specific table remains the primary cross-country object; the meta-analytic summary is secondary.",
            ]
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return output


def build_publication_dossier(
    *,
    country_results: Mapping[str, Path],
    cross_country_results: Mapping[str, Path],
    decomposition_summary: Path | None,
    publication_config: PublicationConfig,
    output_dir: Path,
) -> PublicationDossierResult:
    """Build the machine-generated result dossier for one verified result vintage."""
    required_drivers = {publication_config.primary_driver, *publication_config.secondary_drivers}
    missing_country = required_drivers.difference(country_results)
    missing_cross = required_drivers.difference(cross_country_results)
    if missing_country:
        raise ValueError(f"Missing country model results for drivers: {sorted(missing_country)}")
    if missing_cross:
        raise ValueError(f"Missing cross-country results for drivers: {sorted(missing_cross)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    core_rows: list[dict[str, Any]] = []
    reliability_rows: list[dict[str, Any]] = []
    for driver in [publication_config.primary_driver, *publication_config.secondary_drivers]:
        core, reliability = _summarise_model_result(
            path=country_results[driver],
            driver=driver,
            config=publication_config,
        )
        core_rows.append(core)
        reliability_rows.extend(reliability)
    core_frame = pd.DataFrame(core_rows)
    reliability_frame = pd.DataFrame(reliability_rows)

    cross_rows = [
        _cross_country_summary(cross_country_results[driver], driver=driver)
        for driver in [publication_config.primary_driver, *publication_config.secondary_drivers]
    ]
    cross_frame = pd.DataFrame(cross_rows)

    core_path = output_dir / "core_estimates.csv"
    reliability_path = output_dir / "reliability_gates.csv"
    cross_path = output_dir / "cross_country_summary.csv"
    core_frame.to_csv(core_path, index=False)
    reliability_frame.to_csv(reliability_path, index=False)
    cross_frame.to_csv(cross_path, index=False)

    decomposition_path: Path | None = None
    if decomposition_summary is not None:
        rows = _decomposition_rows(decomposition_summary)
        decomposition_path = output_dir / "decomposition_summary.csv"
        pd.DataFrame(rows).to_csv(decomposition_path, index=False)

    markdown_path = _write_markdown_summary(
        core=core_frame,
        cross_country=cross_frame,
        config=publication_config,
        output=output_dir / "results_summary.md",
    )

    inputs: dict[str, str] = {
        **{str(path): sha256_bytes(path.read_bytes()) for path in country_results.values()},
        **{str(path): sha256_bytes(path.read_bytes()) for path in cross_country_results.values()},
    }
    for path in cross_country_results.values():
        summary_path = path.with_suffix(".summary.json")
        inputs[str(summary_path)] = sha256_bytes(summary_path.read_bytes())
    if decomposition_summary is not None:
        inputs[str(decomposition_summary)] = sha256_bytes(decomposition_summary.read_bytes())

    outputs = [core_path, reliability_path, cross_path, markdown_path]
    if decomposition_path is not None:
        outputs.append(decomposition_path)
    manifest_path = output_dir / "publication_manifest.json"
    write_json(
        {
            "package_version": __version__,
            "primary_country": publication_config.primary_country,
            "primary_driver": publication_config.primary_driver,
            "primary_estimand": publication_config.primary_estimand,
            "inputs": inputs,
            "outputs": {str(path): sha256_bytes(path.read_bytes()) for path in outputs},
            "causal_claims_authorized": False,
        },
        manifest_path,
    )
    return PublicationDossierResult(
        core_estimates=core_path,
        reliability=reliability_path,
        cross_country=cross_path,
        decomposition=decomposition_path,
        summary_markdown=markdown_path,
        manifest=manifest_path,
    )
