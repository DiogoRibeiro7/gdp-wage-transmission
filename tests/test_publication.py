from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from wage_transmission.config import load_publication_config
from wage_transmission.publication import (
    build_publication_dossier,
    build_specification_lock,
    read_specification_lock,
    verify_specification_lock,
    write_specification_lock,
)
from wage_transmission.reporting import write_json


def _write_model_result(path: Path, *, estimate: float, cointegrated: bool) -> None:
    payload = {
        "empirical_audit": {
            "start_year": 1995,
            "end_year": 2025,
            "n_levels": 31,
            "n_growth_observations": 30,
            "annualized_wage_growth": 0.01,
            "annualized_driver_growth": 0.012,
            "growth_correlation": 0.15,
            "positive_driver_changes": 24,
            "negative_driver_changes": 6,
            "zero_driver_changes": 0,
        },
        "reliability": {
            "cointegration_supported_5pct": cointegrated,
            "ecm_long_run_interpretation": "supported"
            if cointegrated
            else "unsupported_without_cointegration",
            "asymmetry_min_shock_count": 6,
            "asymmetry_interpretation": "underpowered_shock_balance",
            "state_space_latest_z_score": 0.5,
            "state_space_latest_distinguishable_from_zero_95pct": False,
            "state_space_interpretation": "latest_slope_imprecise",
            "structural_break_smallest_segment": 8,
            "structural_break_interpretation": "small_regime_segments",
            "local_projection_min_nobs": 25,
            "local_projection_supported_horizons": [0, 1, 2, 3],
            "local_projection_exploratory_horizons": [4, 5],
            "local_projection_interpretation": "long_horizons_exploratory",
            "warnings": ["guardrail"],
        },
        "distributed_lag": {
            "cumulative_transmission": estimate,
            "cumulative_std_error": 0.1,
            "cumulative_p_value": 0.02,
        },
        "ecm": {"long_run_elasticity": 0.7},
        "state_space": {"elasticity": [0.2, 0.3], "elasticity_std_error": [0.4, 0.5]},
        "structural_breaks": {"break_years": [2008, 2014]},
        "asymmetry": {"positive_cumulative": 0.5, "negative_cumulative": 0.9},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_cross_country(path: Path, *, driver: str) -> None:
    frame = pd.DataFrame(
        {
            "country": ["AAA", "BBB"],
            "driver": [driver, driver],
            "distributed_lag_cumulative": [0.4, 0.6],
            "distributed_lag_cumulative_se": [0.1, 0.2],
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    summary = {
        "driver": driver,
        "n_countries": 2,
        "median_cumulative_transmission": 0.5,
        "q25_cumulative_transmission": 0.45,
        "q75_cumulative_transmission": 0.55,
        "positive_country_share": 1.0,
        "fixed_effect_estimate": 0.44,
        "fixed_effect_std_error": 0.09,
        "random_effect_estimate": 0.48,
        "random_effect_std_error": 0.11,
        "tau_squared": 0.01,
        "cochran_q": 2.0,
        "i_squared_percent": 50.0,
        "interpretation": "moderate_cross_country_heterogeneity",
    }
    path.with_suffix(".summary.json").write_text(json.dumps(summary), encoding="utf-8")


def test_publication_config_loads() -> None:
    config = load_publication_config(Path("config/publication.yml"))
    assert config.primary_driver == "productivity_per_worker"
    assert config.primary_estimand == "distributed_lag_cumulative"


def test_hashed_artefacts_are_written_with_lf_only(tmp_path: Path) -> None:
    """Artefact bytes are hashed, so they must not depend on the writing platform."""
    project = tmp_path / "project.yml"
    models = tmp_path / "models.yml"
    publication = tmp_path / "publication.yml"
    project.write_text("a: 1\n", encoding="utf-8")
    models.write_text("b: 2\n", encoding="utf-8")
    publication.write_text("c: 3\n", encoding="utf-8")
    lock = build_specification_lock(
        project_config=project,
        models_config=models,
        publication_config=publication,
        label="lf-only",
    )
    lock_path = tmp_path / "lock.json"
    write_specification_lock(lock, lock_path)
    assert b"\r\n" not in lock_path.read_bytes()

    result_path = tmp_path / "result.json"
    write_json({"estimate": 0.5, "segments": [1, 2]}, result_path)
    assert b"\r\n" not in result_path.read_bytes()


def test_specification_lock_records_posix_paths(tmp_path: Path) -> None:
    """A lock written on Windows must stay verifiable on POSIX CI, and vice versa."""
    project = tmp_path / "nested" / "project.yml"
    models = tmp_path / "nested" / "models.yml"
    publication = tmp_path / "nested" / "publication.yml"
    project.parent.mkdir(parents=True)
    project.write_text("a: 1\n", encoding="utf-8")
    models.write_text("b: 2\n", encoding="utf-8")
    publication.write_text("c: 3\n", encoding="utf-8")
    lock = build_specification_lock(
        project_config=project,
        models_config=models,
        publication_config=publication,
        label="posix-paths",
    )
    recorded = [
        lock.analysis_code_root,
        lock.project_config.path,
        lock.models_config.path,
        lock.publication_config.path,
    ]
    assert all("\\" not in path for path in recorded)
    assert lock.analysis_code_root == "src/wage_transmission"


def test_specification_lock_detects_config_change(tmp_path: Path) -> None:
    project = tmp_path / "project.yml"
    models = tmp_path / "models.yml"
    publication = tmp_path / "publication.yml"
    project.write_text("a: 1\n", encoding="utf-8")
    models.write_text("b: 2\n", encoding="utf-8")
    publication.write_text("c: 3\n", encoding="utf-8")
    lock = build_specification_lock(
        project_config=project,
        models_config=models,
        publication_config=publication,
        label="before-results",
    )
    output = tmp_path / "lock.json"
    write_specification_lock(lock, output)
    loaded = read_specification_lock(output)
    verify_specification_lock(loaded, root=Path("."))
    models.write_text("b: 9\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash_mismatch"):
        verify_specification_lock(loaded, root=Path("."))


def test_specification_lock_detects_analysis_code_change(tmp_path: Path) -> None:
    project = tmp_path / "project.yml"
    models = tmp_path / "models.yml"
    publication = tmp_path / "publication.yml"
    code_root = tmp_path / "analysis_code"
    code_root.mkdir()
    code_file = code_root / "model.py"
    project.write_text("a: 1\n", encoding="utf-8")
    models.write_text("b: 2\n", encoding="utf-8")
    publication.write_text("c: 3\n", encoding="utf-8")
    code_file.write_text("VALUE = 1\n", encoding="utf-8")
    lock = build_specification_lock(
        project_config=project,
        models_config=models,
        publication_config=publication,
        label="before-results",
        analysis_code_root=code_root,
    )
    output = tmp_path / "lock.json"
    write_specification_lock(lock, output)
    loaded = read_specification_lock(output)
    verify_specification_lock(loaded, root=Path("."))
    code_file.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="code_hash_mismatch"):
        verify_specification_lock(loaded, root=Path("."))


def test_publication_dossier_enforces_reliability_gates(tmp_path: Path) -> None:
    project = tmp_path / "project.yml"
    models = tmp_path / "models.yml"
    publication_file = tmp_path / "publication.yml"
    project.write_text(Path("config/project.yml").read_text(encoding="utf-8"), encoding="utf-8")
    models.write_text(Path("config/models.yml").read_text(encoding="utf-8"), encoding="utf-8")
    publication_file.write_text(
        Path("config/publication.yml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    lock = build_specification_lock(
        project_config=project,
        models_config=models,
        publication_config=publication_file,
        label="before-results",
    )
    lock_path = tmp_path / "specification_lock.json"
    write_specification_lock(lock, lock_path)

    worker = tmp_path / "worker.json"
    hour = tmp_path / "hour.json"
    _write_model_result(worker, estimate=0.6, cointegrated=False)
    _write_model_result(hour, estimate=0.4, cointegrated=True)
    worker_cross = tmp_path / "worker_cross.csv"
    hour_cross = tmp_path / "hour_cross.csv"
    _write_cross_country(worker_cross, driver="productivity_per_worker")
    _write_cross_country(hour_cross, driver="productivity")

    config = load_publication_config(publication_file)
    out = build_publication_dossier(
        country_results={
            "productivity_per_worker": worker,
            "productivity": hour,
        },
        cross_country_results={
            "productivity_per_worker": worker_cross,
            "productivity": hour_cross,
        },
        decomposition_summary=None,
        dynamic_panel_results=None,
        specification_lock=lock_path,
        publication_config=config,
        output_dir=tmp_path / "dossier",
    )
    core = pd.read_csv(out.core_estimates)
    worker_row = core.loc[core["driver"] == "productivity_per_worker"].iloc[0]
    hour_row = core.loc[core["driver"] == "productivity"].iloc[0]
    assert not bool(worker_row["ecm_claim_eligible"])
    assert bool(hour_row["ecm_claim_eligible"])
    assert out.manifest.is_file()


def test_dossier_records_when_no_lock_was_verified(tmp_path: Path) -> None:
    """The lock lives outside version control, so a clean checkout may not have one."""
    worker = tmp_path / "worker.json"
    hour = tmp_path / "hour.json"
    _write_model_result(worker, estimate=0.6, cointegrated=False)
    _write_model_result(hour, estimate=0.4, cointegrated=True)
    worker_cross = tmp_path / "worker_cross.csv"
    hour_cross = tmp_path / "hour_cross.csv"
    _write_cross_country(worker_cross, driver="productivity_per_worker")
    _write_cross_country(hour_cross, driver="productivity")

    out = build_publication_dossier(
        country_results={"productivity_per_worker": worker, "productivity": hour},
        cross_country_results={
            "productivity_per_worker": worker_cross,
            "productivity": hour_cross,
        },
        decomposition_summary=None,
        dynamic_panel_results=None,
        specification_lock=None,
        publication_config=load_publication_config(Path("config/publication.yml")),
        output_dir=tmp_path / "dossier",
    )

    manifest = json.loads(out.manifest.read_text(encoding="utf-8"))
    # Auditable either way, but the manifest must not imply a commitment that was never checked.
    assert manifest["specification_lock_verified"] is False
    assert manifest["specification_lock_label"] is None
    assert manifest["outputs"]


def _write_dynamic_panel(path: Path, *, driver: str, gate_failures: list[str]) -> None:
    """A minimal frozen dynamic-panel payload with one primary specification."""

    def specification(
        role: str, effects: str, block: int, failures: list[str]
    ) -> dict[str, object]:
        return {
            "driver": driver,
            "role": role,
            "fixed_effects": effects,
            "n_countries": 13,
            "nobs": 363,
            "n_effective_years": 28,
            "driver_lags": 2,
            "block_length": block,
            "driscoll_kraay_lags": 3,
            "replications_requested": 4999,
            "replications_completed": 4999,
            "correction_iterations": 6,
            "correction_draws": 200,
            "seed": 20260825,
            "lsdv_driver_sum": 0.48,
            "lsdv_persistence": 0.10,
            "lsdv_multiplier": 0.53,
            "corrected_driver_sum": 0.45,
            "corrected_persistence": 0.15,
            "corrected_multiplier": 0.53,
            "lsdv_multiplier_bootstrap_median": 0.50,
            "corrected_multiplier_bootstrap_median": 0.50,
            "corrected_persistence_bootstrap_median": 0.13,
            "driscoll_kraay_driver_sum_std_error": 0.06,
            "driscoll_kraay_persistence_std_error": 0.08,
            "driscoll_kraay_multiplier_std_error": 0.09,
            "convergence_share": 1.0,
            "finite_multiplier_share": 1.0,
            "one_minus_persistence_min_abs": 0.6,
            "lsdv_multiplier_ci": [0.34, 0.75],
            "corrected_multiplier_ci": [0.33, 0.76],
            "corrected_persistence_ci": [-0.05, 0.32],
            "one_minus_persistence_quantiles": {"p2.5": 0.68, "p50": 0.87, "p97.5": 1.05},
            "correction_converged": True,
            "rank_deficient": False,
            "gate_failures": failures,
        }

    payload = {
        "driver": driver,
        "primary": specification("primary", "country_and_year", 4, gate_failures),
        "specifications": [
            specification("primary", "country_and_year", 4, gate_failures),
            specification("sensitivity_fixed_effects", "country", 4, []),
        ],
    }
    write_json(payload, path)


def test_dynamic_panel_enters_the_dossier_with_its_gate_verdict(tmp_path: Path) -> None:
    """An ineligible specification must reach the formatter labelled, not filtered out."""
    worker = tmp_path / "worker.json"
    hour = tmp_path / "hour.json"
    _write_model_result(worker, estimate=0.6, cointegrated=False)
    _write_model_result(hour, estimate=0.4, cointegrated=True)
    worker_cross = tmp_path / "worker_cross.csv"
    hour_cross = tmp_path / "hour_cross.csv"
    _write_cross_country(worker_cross, driver="productivity_per_worker")
    _write_cross_country(hour_cross, driver="productivity")
    worker_panel = tmp_path / "dynamic_worker.json"
    hour_panel = tmp_path / "dynamic_hour.json"
    _write_dynamic_panel(worker_panel, driver="productivity_per_worker", gate_failures=[])
    _write_dynamic_panel(
        hour_panel, driver="productivity", gate_failures=["insufficient_effective_years"]
    )

    out = build_publication_dossier(
        country_results={"productivity_per_worker": worker, "productivity": hour},
        cross_country_results={
            "productivity_per_worker": worker_cross,
            "productivity": hour_cross,
        },
        decomposition_summary=None,
        dynamic_panel_results={
            "productivity_per_worker": worker_panel,
            "productivity": hour_panel,
        },
        specification_lock=None,
        publication_config=load_publication_config(Path("config/publication.yml")),
        output_dir=tmp_path / "dossier",
    )

    assert out.dynamic_panel is not None
    frame = pd.read_csv(out.dynamic_panel)
    assert len(frame) == 4
    primary = frame.loc[(frame["driver"] == "productivity") & (frame["role"] == "primary")].iloc[0]
    assert not bool(primary["claim_eligible"])
    assert primary["gate_failures"] == "insufficient_effective_years"
    assert int(primary["nobs"]) == 363
    eligible = frame.loc[frame["driver"] == "productivity_per_worker"].iloc[0]
    assert bool(eligible["claim_eligible"])
    manifest = json.loads(out.manifest.read_text(encoding="utf-8"))
    assert str(worker_panel) in manifest["inputs"]


def test_dossier_rejects_a_dynamic_panel_file_for_the_wrong_driver(tmp_path: Path) -> None:
    worker = tmp_path / "worker.json"
    hour = tmp_path / "hour.json"
    _write_model_result(worker, estimate=0.6, cointegrated=False)
    _write_model_result(hour, estimate=0.4, cointegrated=True)
    worker_cross = tmp_path / "worker_cross.csv"
    hour_cross = tmp_path / "hour_cross.csv"
    _write_cross_country(worker_cross, driver="productivity_per_worker")
    _write_cross_country(hour_cross, driver="productivity")
    mislabelled = tmp_path / "dynamic_worker.json"
    _write_dynamic_panel(mislabelled, driver="productivity", gate_failures=[])

    with pytest.raises(ValueError, match="expected"):
        build_publication_dossier(
            country_results={"productivity_per_worker": worker, "productivity": hour},
            cross_country_results={
                "productivity_per_worker": worker_cross,
                "productivity": hour_cross,
            },
            decomposition_summary=None,
            dynamic_panel_results={
                "productivity_per_worker": mislabelled,
                "productivity": mislabelled,
            },
            specification_lock=None,
            publication_config=load_publication_config(Path("config/publication.yml")),
            output_dir=tmp_path / "dossier",
        )
