"""End-to-end one-country analysis pipeline."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pandas as pd

from wage_transmission.config import ModelsConfig
from wage_transmission.diagnostics.cointegration import engle_granger
from wage_transmission.diagnostics.stationarity import adf_test, kpss_test
from wage_transmission.empirical_audit import assess_reliability, audit_country_frame
from wage_transmission.models.asymmetry import fit_asymmetric_transmission
from wage_transmission.models.distributed_lag import fit_distributed_lag
from wage_transmission.models.ecm import select_ecm_lags
from wage_transmission.models.local_projections import fit_local_projections
from wage_transmission.models.state_space import fit_time_varying_elasticity
from wage_transmission.models.structural_breaks import fit_structural_breaks
from wage_transmission.plots import (
    plot_levels,
    plot_local_projections,
    plot_time_varying_elasticity,
)
from wage_transmission.reporting import write_json
from wage_transmission.validation import add_log_growth_columns, validate_level_frame


def analyse_country(
    frame: pd.DataFrame,
    output_dir: Path,
    *,
    driver_column: str = "productivity",
    model_config: ModelsConfig | None = None,
) -> dict[str, object]:
    """Run the core diagnostics and models for one country and one positive driver series.

    `driver_column` may be `productivity`, `real_gdp`, or another positive level series. Internally
    it is mapped to the canonical `productivity` slot so the estimators stay identical across
    robustness definitions.
    """
    if driver_column not in frame.columns:
        raise ValueError(f"Driver column not found: {driver_column}")
    prepared = frame.copy()
    prepared["productivity"] = pd.to_numeric(prepared[driver_column], errors="coerce")
    data = validate_level_frame(prepared)
    cfg = model_config or ModelsConfig()
    transformed = add_log_growth_columns(data)
    output_dir.mkdir(parents=True, exist_ok=True)

    cointegration = engle_granger(
        transformed["log_wage"].to_numpy(),
        transformed["log_productivity"].to_numpy(),
    )
    diagnostics = {
        "adf_log_wage": asdict(adf_test(transformed["log_wage"].to_numpy())),
        "adf_log_productivity": asdict(adf_test(transformed["log_productivity"].to_numpy())),
        "adf_dlog_wage": asdict(adf_test(transformed["dlog_wage"].to_numpy(), regression="c")),
        "adf_dlog_productivity": asdict(
            adf_test(transformed["dlog_productivity"].to_numpy(), regression="c")
        ),
        "kpss_log_wage": asdict(kpss_test(transformed["log_wage"].to_numpy())),
        "kpss_log_productivity": asdict(kpss_test(transformed["log_productivity"].to_numpy())),
        "kpss_dlog_wage": asdict(kpss_test(transformed["dlog_wage"].to_numpy(), regression="c")),
        "kpss_dlog_productivity": asdict(
            kpss_test(transformed["dlog_productivity"].to_numpy(), regression="c")
        ),
        "cointegration": asdict(cointegration),
        "cointegration_supported_5pct": bool(cointegration.p_value < 0.05),
    }
    distributed = fit_distributed_lag(
        data,
        x_lags=cfg.distributed_lag.x_lags,
        y_lags=cfg.distributed_lag.y_lags,
        hac_lags=cfg.distributed_lag.hac_lags,
    )
    # The ECM is reported as a conditional long-run specification. Its long-run coefficient must
    # not be interpreted as established if the cointegration diagnostics do not support it.
    ecm = select_ecm_lags(
        data,
        max_wage_growth_lags=cfg.ecm.max_wage_growth_lags,
        max_productivity_growth_lags=cfg.ecm.max_productivity_growth_lags,
        hac_lags=cfg.ecm.hac_lags,
    )
    breaks = fit_structural_breaks(
        data,
        max_breaks=cfg.structural_breaks.max_breaks,
        min_segment=cfg.structural_breaks.min_segment,
    )
    state_space = fit_time_varying_elasticity(
        data,
        initial_state_variance=cfg.state_space.initial_state_variance,
    )
    local_projections = fit_local_projections(
        data,
        horizon=cfg.local_projections.horizon,
        control_lags=cfg.local_projections.control_lags,
        hac_lags=cfg.local_projections.hac_lags,
    )
    asymmetry = fit_asymmetric_transmission(
        data,
        lags=cfg.asymmetry.lags,
        hac_lags=cfg.asymmetry.hac_lags,
    )
    audit = audit_country_frame(data)
    reliability = assess_reliability(
        audit=audit,
        cointegration_p_value=cointegration.p_value,
        breaks=breaks,
        state_space=state_space,
        local_projections=local_projections,
        config=cfg.reliability,
    )

    outputs: dict[str, object] = {
        "metadata": {
            "driver_column": driver_column,
            "ecm_long_run_interpretation_supported_5pct": bool(cointegration.p_value < 0.05),
        },
        "empirical_audit": audit,
        "reliability": reliability,
        "diagnostics": diagnostics,
        "distributed_lag": distributed,
        "ecm": ecm,
        "structural_breaks": breaks,
        "state_space": state_space,
        "local_projections": local_projections,
        "asymmetry": asymmetry,
    }
    write_json(outputs, output_dir / "model_results.json")
    plot_levels(data, output_dir / "levels.png")
    plot_time_varying_elasticity(state_space, output_dir / "time_varying_elasticity.png")
    plot_local_projections(local_projections, output_dir / "local_projections.png")
    return outputs
