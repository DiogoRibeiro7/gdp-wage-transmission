from __future__ import annotations

import numpy as np
import pandas as pd

from wage_transmission.decomposition import decompose_real_wage_growth


def test_accounting_decomposition_closes() -> None:
    years = np.arange(2000, 2020)
    real_gdp = 100.0 * 1.025 ** np.arange(len(years))
    gdp_deflator = 1.0 * 1.02 ** np.arange(len(years))
    cpi = 1.0 * 1.018 ** np.arange(len(years))
    nominal_gdp = real_gdp * gdp_deflator
    labour_share = 0.55 * 0.998 ** np.arange(len(years))
    compensation = nominal_gdp * labour_share
    employees = 5.0 * 1.006 ** np.arange(len(years))
    frame = pd.DataFrame(
        {
            "year": years,
            "nominal_gdp": nominal_gdp,
            "real_gdp": real_gdp,
            "employee_compensation": compensation,
            "employees": employees,
            "consumer_price_index": cpi,
        }
    )
    out = decompose_real_wage_growth(frame)
    residual = out["identity_residual"].dropna().to_numpy()
    assert np.max(np.abs(residual)) < 1e-10


def test_panel_decomposition_preserves_country_and_summary() -> None:
    from wage_transmission.decomposition import decompose_panel

    years = np.arange(2010, 2020)
    base = pd.DataFrame(
        {
            "year": years,
            "nominal_gdp": 100.0 * 1.04 ** np.arange(len(years)),
            "real_gdp": 100.0 * 1.02 ** np.arange(len(years)),
            "employee_compensation": 52.0 * 1.035 ** np.arange(len(years)),
            "employees": 4.0 * 1.005 ** np.arange(len(years)),
            "consumer_price_index": 100.0 * 1.018 ** np.arange(len(years)),
        }
    )
    panel = pd.concat(
        [
            base.assign(country="AAA"),
            base.assign(country="BBB", employee_compensation=base["employee_compensation"] * 1.1),
        ],
        ignore_index=True,
    )
    components, summaries = decompose_panel(panel)
    assert set(components["country"]) == {"AAA", "BBB"}
    assert len(summaries) == 2
    assert all(summary.max_abs_identity_residual < 1e-10 for summary in summaries)
