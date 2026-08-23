from __future__ import annotations

import numpy as np
import pandas as pd

from wage_transmission.config import ReliabilityConfig
from wage_transmission.empirical_audit import assess_reliability, audit_country_frame
from wage_transmission.models.local_projections import LocalProjectionPoint
from wage_transmission.models.state_space import TimeVaryingElasticityResult
from wage_transmission.models.structural_breaks import BreakSegment, StructuralBreakResult


def _frame() -> pd.DataFrame:
    years = np.arange(2000, 2021)
    productivity = 100.0 * np.exp(0.01 * np.arange(len(years)))
    # Insert four contractions so asymmetry remains deliberately underpowered.
    productivity[[5, 9, 13, 17]] *= 0.97
    wage = 100.0 * np.exp(0.008 * np.arange(len(years)))
    return pd.DataFrame({"year": years, "real_wage": wage, "productivity": productivity})


def test_empirical_audit_counts_driver_signs() -> None:
    audit = audit_country_frame(_frame())
    assert audit.start_year == 2000
    assert audit.end_year == 2020
    assert audit.n_levels == 21
    assert audit.n_growth_observations == 20
    assert audit.negative_driver_changes >= 4
    assert audit.positive_driver_changes > audit.negative_driver_changes


def test_reliability_flags_weak_identification() -> None:
    audit = audit_country_frame(_frame())
    breaks = StructuralBreakResult(
        break_years=(2010,),
        segments=(
            BreakSegment(2001, 2009, 0.0, 0.5, 1.0, 9),
            BreakSegment(2010, 2020, 0.0, 0.5, 1.0, 11),
        ),
        bic=0.0,
        n_breaks=1,
    )
    state_space = TimeVaryingElasticityResult(
        year=np.array([2019, 2020]),
        intercept=np.array([0.0, 0.0]),
        elasticity=np.array([0.1, 0.2]),
        elasticity_std_error=np.array([0.4, 0.4]),
        observation_variance=1.0,
        state_variance=0.1,
        log_likelihood=-1.0,
        converged=True,
    )
    lp = (
        LocalProjectionPoint(0, 0.1, 0.1, -0.096, 0.296, 30),
        LocalProjectionPoint(1, 0.1, 0.1, -0.096, 0.296, 20),
    )
    assessment = assess_reliability(
        audit=audit,
        cointegration_p_value=0.20,
        breaks=breaks,
        state_space=state_space,
        local_projections=lp,
        config=ReliabilityConfig(),
    )
    assert assessment.ecm_long_run_interpretation == "unsupported_without_cointegration"
    assert assessment.asymmetry_interpretation == "underpowered_shock_balance"
    assert assessment.state_space_interpretation == "latest_slope_imprecise"
    assert assessment.structural_break_interpretation == "small_regime_segments"
    assert assessment.local_projection_supported_horizons == (0,)
    assert assessment.local_projection_exploratory_horizons == (1,)
    assert len(assessment.warnings) == 5
