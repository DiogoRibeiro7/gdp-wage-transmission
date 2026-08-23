from __future__ import annotations

import pandas as pd

from wage_transmission.data.oecd import (
    PRODUCTIVITY_FLOW,
    build_oecd_url,
    canonicalise_gdp_per_employed,
)


def test_gdp_per_employed_current_pdb_key() -> None:
    """The matched annual productivity series uses the current PDB v2.0 dimension codes."""
    url = build_oecd_url(
        PRODUCTIVITY_FLOW,
        "PRT.A.GDPEMP._T.USD_PPP_PS.LR.N..",
        start_year=1995,
        end_year=2025,
    )
    assert "DSD_PDB%40DF_PDB" not in url  # flow refs are already URL-safe path components
    assert "GDPEMP._T.USD_PPP_PS.LR.N.." in url
    assert "startPeriod=1995" in url
    assert "endPeriod=2025" in url


def test_canonicalise_gdp_per_employed_keeps_distinct_column() -> None:
    frame = pd.DataFrame(
        {
            "REF_AREA": ["PRT", "PRT"],
            "TIME_PERIOD": [2023, 2024],
            "OBS_VALUE": [100.0, 101.5],
        }
    )
    result = canonicalise_gdp_per_employed(frame)
    assert result.columns.tolist() == [
        "country",
        "year",
        "productivity_per_worker",
        "source",
    ]
    assert result["source"].eq("OECD_PDB_GDPEMP").all()


def test_current_wage_query_can_pin_constant_price_code() -> None:
    from wage_transmission.data.oecd import WAGE_FLOW

    url = build_oecd_url(
        WAGE_FLOW,
        "PRT..USD_PPP..Q..",
        start_year=1995,
        end_year=2025,
    )
    assert "PRT..USD_PPP..Q.." in url
