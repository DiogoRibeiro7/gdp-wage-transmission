"""Tests for the reporting-side annual exploratory decomposition."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from tools.exploratory_annual_decomposition import calculate_annual_decomposition


def _annual_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "year": [2022, 2023, 2024, 2025],
            "nominal_gdp_m_eur": [243957.086, 270352.615, 289784.317, 306765.485],
            "employee_compensation_m_eur": [113604.178, 127048.578, 137966.914, 147620.6447],
            "gdp_deflator": [1.053275, 1.132141, 1.187221, 1.233788],
            "hicp_annual_avg": [90.5408333333, 95.3075, 97.8533333333, 100.0008333333],
            "employees_lfs_thousand": [4190.3, 4310.5, 4349.9, 4474.2],
        }
    )


def test_missing_sal_dc_keeps_locked_annual_total_incomplete() -> None:
    locked, _, summary = calculate_annual_decomposition(_annual_frame())
    assert summary.locked_sal_dc_complete is False
    assert summary.locked_sal_dc_level_observations == 0
    assert summary.cumulative_locked_employment_log_contribution is None
    assert summary.cumulative_locked_real_compensation_per_employee_log_change is None
    assert locked["employment_component"].isna().all()
    assert locked["decomposed_real_wage_growth"].isna().all()


def test_employee_independent_terms_equal_full_lfs_identity_terms() -> None:
    locked, lfs, summary = calculate_annual_decomposition(_annual_frame())
    for column in ("real_gdp_component", "labour_share_component", "relative_price_component"):
        assert locked[column].tolist() == pytest.approx(lfs[column].tolist(), nan_ok=True)
    assert summary.employee_independent_terms_complete is True


def test_lfs_annual_identity_closes_and_is_non_publication() -> None:
    _, lfs, summary = calculate_annual_decomposition(_annual_frame())
    residual = lfs["identity_residual"].dropna().abs().max()
    assert float(residual) < 1e-12
    assert summary.lfs_max_abs_identity_residual < 1e-12
    assert summary.publication_eligible is False
    assert (lfs["publication_eligible"] == False).all()  # noqa: E712
    assert not bool(lfs["denominator_concept_matches_locked_specification"].any())


def test_complete_sal_dc_activates_locked_identity_without_changing_independent_terms() -> None:
    frame = _annual_frame()
    frame["employees_sal_dc_thousand"] = [4200.0, 4300.0, 4400.0, 4500.0]
    locked, _, summary = calculate_annual_decomposition(frame)
    assert summary.locked_sal_dc_complete is True
    assert summary.locked_sal_dc_level_observations == len(frame)
    assert summary.cumulative_locked_employment_log_contribution is not None
    assert summary.cumulative_locked_real_compensation_per_employee_log_change is not None
    assert locked["decomposed_real_wage_growth"].dropna().shape[0] == len(frame) - 1
    assert float(locked["identity_residual"].dropna().abs().max()) < 1e-12


def test_annual_input_requires_contiguous_positive_levels() -> None:
    gap = _annual_frame().drop(index=1)
    with pytest.raises(ValueError, match="continuous sequence"):
        calculate_annual_decomposition(gap)

    invalid = _annual_frame()
    invalid.loc[0, "hicp_annual_avg"] = 0.0
    with pytest.raises(ValueError, match="strictly positive"):
        calculate_annual_decomposition(invalid)

    partial_sal = _annual_frame()
    partial_sal["employees_sal_dc_thousand"] = [math.nan, 4300.0, math.nan, 4500.0]
    _, _, summary = calculate_annual_decomposition(partial_sal)
    assert summary.locked_sal_dc_complete is False
    assert summary.locked_sal_dc_level_observations == 2
