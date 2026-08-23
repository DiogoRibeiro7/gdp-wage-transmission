from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_levels() -> pd.DataFrame:
    rng = np.random.default_rng(20260822)
    years = np.arange(1965, 2025)
    prod_growth = rng.normal(0.018, 0.018, len(years))
    prod_growth[1:] += 0.20 * prod_growth[:-1]
    wage_growth = np.empty(len(years))
    wage_growth[0] = 0.01
    for idx in range(1, len(years)):
        beta = 0.85 if years[idx] < 1995 else 0.45
        wage_growth[idx] = 0.002 + beta * prod_growth[idx] + 0.15 * wage_growth[idx - 1] + rng.normal(0, 0.008)
    productivity = 25.0 * np.exp(np.cumsum(prod_growth))
    wage = 18000.0 * np.exp(np.cumsum(wage_growth))
    return pd.DataFrame({"year": years, "real_wage": wage, "productivity": productivity})
