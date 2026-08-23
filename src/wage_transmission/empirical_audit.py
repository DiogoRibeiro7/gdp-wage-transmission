"""Empirical sample audit and interpretation guardrails."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from wage_transmission.config import ReliabilityConfig
from wage_transmission.models.local_projections import LocalProjectionPoint
from wage_transmission.models.state_space import TimeVaryingElasticityResult
from wage_transmission.models.structural_breaks import StructuralBreakResult
from wage_transmission.validation import add_log_growth_columns


@dataclass(frozen=True)
class EmpiricalAudit:
    """Descriptive properties that determine what the time-series sample can support."""

    start_year: int
    end_year: int
    n_levels: int
    n_growth_observations: int
    annualized_wage_growth: float
    annualized_driver_growth: float
    growth_correlation: float
    positive_driver_changes: int
    negative_driver_changes: int
    zero_driver_changes: int


@dataclass(frozen=True)
class ReliabilityAssessment:
    """Machine-readable interpretation guardrails for the fitted model stack."""

    cointegration_supported_5pct: bool
    ecm_long_run_interpretation: str
    asymmetry_min_shock_count: int
    asymmetry_interpretation: str
    state_space_latest_z_score: float
    state_space_latest_distinguishable_from_zero_95pct: bool
    state_space_interpretation: str
    structural_break_smallest_segment: int
    structural_break_interpretation: str
    local_projection_min_nobs: int
    local_projection_supported_horizons: tuple[int, ...]
    local_projection_exploratory_horizons: tuple[int, ...]
    local_projection_interpretation: str
    warnings: tuple[str, ...]


def audit_country_frame(frame: pd.DataFrame) -> EmpiricalAudit:
    """Summarise coverage, trend growth and the balance of driver shocks."""
    data = add_log_growth_columns(frame)
    growth = data.dropna(subset=["dlog_wage", "dlog_productivity"]).copy()
    if growth.empty:
        raise ValueError("At least one complete growth observation is required.")

    years = int(data["year"].iloc[-1] - data["year"].iloc[0])
    if years <= 0:
        raise ValueError("The sample must span at least one calendar year.")

    wage_growth = float(
        np.exp((data["log_wage"].iloc[-1] - data["log_wage"].iloc[0]) / years) - 1.0
    )
    driver_growth = float(
        np.exp((data["log_productivity"].iloc[-1] - data["log_productivity"].iloc[0]) / years) - 1.0
    )
    correlation = float(growth["dlog_wage"].corr(growth["dlog_productivity"]))

    driver_changes = growth["dlog_productivity"].to_numpy(dtype=float)
    zero_mask = np.isclose(driver_changes, 0.0, atol=1e-12, rtol=0.0)
    positive = int(np.sum((driver_changes > 0.0) & ~zero_mask))
    negative = int(np.sum((driver_changes < 0.0) & ~zero_mask))
    zero = int(np.sum(zero_mask))

    return EmpiricalAudit(
        start_year=int(data["year"].iloc[0]),
        end_year=int(data["year"].iloc[-1]),
        n_levels=len(data),
        n_growth_observations=len(growth),
        annualized_wage_growth=wage_growth,
        annualized_driver_growth=driver_growth,
        growth_correlation=correlation,
        positive_driver_changes=positive,
        negative_driver_changes=negative,
        zero_driver_changes=zero,
    )


def assess_reliability(
    *,
    audit: EmpiricalAudit,
    cointegration_p_value: float,
    breaks: StructuralBreakResult,
    state_space: TimeVaryingElasticityResult,
    local_projections: tuple[LocalProjectionPoint, ...],
    config: ReliabilityConfig,
) -> ReliabilityAssessment:
    """Convert sample limitations into explicit interpretation labels and warnings."""
    cointegration_supported = bool(cointegration_p_value < 0.05)
    ecm_label = "supported" if cointegration_supported else "unsupported_without_cointegration"

    min_shocks = min(audit.positive_driver_changes, audit.negative_driver_changes)
    asymmetry_supported = min_shocks >= config.min_asymmetry_shocks_per_sign
    asymmetry_label = (
        "supported_for_interpretation" if asymmetry_supported else "underpowered_shock_balance"
    )

    latest_elasticity = float(state_space.elasticity[-1])
    latest_se = float(state_space.elasticity_std_error[-1])
    z_score = float(latest_elasticity / latest_se) if latest_se > 0.0 else float("inf")
    state_space_significant = bool(abs(z_score) >= config.state_space_z_threshold)
    state_space_label = (
        "latest_slope_distinguishable_from_zero"
        if state_space_significant
        else "latest_slope_imprecise"
    )

    smallest_segment = min(segment.nobs for segment in breaks.segments)
    breaks_supported = smallest_segment >= config.min_break_segment_for_interpretation
    break_label = "supported_for_interpretation" if breaks_supported else "small_regime_segments"

    supported_horizons = tuple(
        point.horizon
        for point in local_projections
        if point.nobs >= config.min_local_projection_nobs
    )
    exploratory_horizons = tuple(
        point.horizon
        for point in local_projections
        if point.nobs < config.min_local_projection_nobs
    )
    lp_label = (
        "all_horizons_meet_sample_threshold"
        if not exploratory_horizons
        else "long_horizons_exploratory"
    )

    warnings: list[str] = []
    if not cointegration_supported:
        warnings.append(
            "Engle-Granger does not support cointegration at 5%; do not interpret the ECM long-run elasticity as established."
        )
    if not asymmetry_supported:
        warnings.append(
            "Too few productivity changes of the rarer sign for a stable positive-versus-negative response comparison."
        )
    if not state_space_significant:
        warnings.append(
            "The latest time-varying elasticity is not distinguishable from zero at the configured normal-approximation threshold."
        )
    if not breaks_supported:
        warnings.append(
            "At least one estimated structural-break regime is shorter than the interpretation threshold."
        )
    if exploratory_horizons:
        warnings.append(
            "Some local-projection horizons fall below the minimum effective sample size and are exploratory only."
        )

    return ReliabilityAssessment(
        cointegration_supported_5pct=cointegration_supported,
        ecm_long_run_interpretation=ecm_label,
        asymmetry_min_shock_count=min_shocks,
        asymmetry_interpretation=asymmetry_label,
        state_space_latest_z_score=z_score,
        state_space_latest_distinguishable_from_zero_95pct=state_space_significant,
        state_space_interpretation=state_space_label,
        structural_break_smallest_segment=smallest_segment,
        structural_break_interpretation=break_label,
        local_projection_min_nobs=config.min_local_projection_nobs,
        local_projection_supported_horizons=supported_horizons,
        local_projection_exploratory_horizons=exploratory_horizons,
        local_projection_interpretation=lp_label,
        warnings=tuple(warnings),
    )
