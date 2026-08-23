"""Tests for the reporting-side exploratory endpoint decomposition."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from tools.exploratory_endpoint_decomposition import calculate_endpoint_decomposition


def _endpoint_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "year": [1996, 2025],
            "nominal_gdp_m_eur": [94351.591, 306765.485],
            "employee_compensation_m_eur": [44760.176, 147620.6447],
            "gdp_deflator": [0.571002, 1.233788],
            "hicp_annual_avg": [53.58833333333334, 100.00083333333333],
            "employees_lfs_thousand": [3181.7, 4474.2],
        }
    )


def test_lfs_sensitivity_closes_exact_log_identity() -> None:
    _, _, _, sensitivity = calculate_endpoint_decomposition(_endpoint_frame())
    assert sensitivity.max_abs_identity_residual < 1e-12
    expected = (
        sensitivity.real_gdp_log_contribution
        + sensitivity.labour_share_log_contribution
        + sensitivity.employment_log_contribution
        + sensitivity.relative_price_log_contribution
    )
    assert sensitivity.decomposed_real_wage_log_change == pytest.approx(expected)
    assert sensitivity.observed_real_compensation_per_employee_log_change == pytest.approx(expected)


def test_locked_partial_keeps_sal_dc_term_missing() -> None:
    partial, summary, _, _ = calculate_endpoint_decomposition(_endpoint_frame())
    employment = partial.loc[partial["component"] == "employment_component"].iloc[0]
    assert math.isnan(float(employment["log_point_contribution"]))
    assert employment["status"] == "missing_locked_sal_dc"
    assert summary.locked_sal_dc_status == "incomplete_missing_start_endpoint"
    assert summary.employment_log_contribution is None
    assert summary.decomposed_real_wage_log_change is None
    assert summary.publication_eligible is False


def test_lfs_sensitivity_is_explicitly_non_publication_and_mismatched() -> None:
    _, _, _, sensitivity = calculate_endpoint_decomposition(_endpoint_frame())
    assert sensitivity.publication_eligible is False
    assert sensitivity.denominator_concept_matches_locked_specification is False
    assert "LFS employees" in sensitivity.sensitivity_denominator
    assert sensitivity.observed_real_compensation_per_employee_level_change_pct == pytest.approx(
        25.6798858706,
        rel=1e-9,
    )


def test_endpoint_input_rejects_wrong_row_count_and_nonpositive_values() -> None:
    with pytest.raises(ValueError, match="exactly two"):
        calculate_endpoint_decomposition(_endpoint_frame().iloc[[0]])

    invalid = _endpoint_frame()
    invalid.loc[0, "gdp_deflator"] = 0.0
    with pytest.raises(ValueError, match="strictly positive"):
        calculate_endpoint_decomposition(invalid)
