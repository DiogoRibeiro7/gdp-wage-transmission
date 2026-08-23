"""Canonical panel construction."""

from __future__ import annotations

import pandas as pd


def merge_wages_productivity(wages: pd.DataFrame, productivity: pd.DataFrame) -> pd.DataFrame:
    """Merge canonical OECD wage and productivity series by country and year."""
    wage_cols = {"country", "year", "real_wage"}
    prod_cols = {"country", "year", "productivity"}
    if not wage_cols.issubset(wages.columns):
        raise ValueError(f"Wage data must contain {sorted(wage_cols)}")
    if not prod_cols.issubset(productivity.columns):
        raise ValueError(f"Productivity data must contain {sorted(prod_cols)}")

    left = wages.loc[:, ["country", "year", "real_wage"]].copy()
    right = productivity.loc[:, ["country", "year", "productivity"]].copy()
    panel = left.merge(right, on=["country", "year"], how="inner", validate="one_to_one")
    return panel.sort_values(["country", "year"]).reset_index(drop=True)


def add_driver(panel: pd.DataFrame, driver: pd.DataFrame, *, column: str) -> pd.DataFrame:
    """Left-join one denominator-explicit robustness driver by country and year."""
    if not column or column in {"country", "year", "real_wage", "productivity"}:
        raise ValueError(f"Invalid additional driver column: {column!r}")
    required = {"country", "year", column}
    if not required.issubset(driver.columns):
        raise ValueError(f"Driver data must contain {sorted(required)}")
    right = driver.loc[:, ["country", "year", column]].copy()
    return panel.merge(right, on=["country", "year"], how="left", validate="one_to_one")


def add_real_gdp(panel: pd.DataFrame, real_gdp: pd.DataFrame) -> pd.DataFrame:
    """Left-join an optional real-GDP robustness driver to the canonical panel."""
    required = {"country", "year", "real_gdp"}
    if not required.issubset(real_gdp.columns):
        raise ValueError(f"Real-GDP data must contain {sorted(required)}")
    right = real_gdp.loc[:, ["country", "year", "real_gdp"]].copy()
    return panel.merge(right, on=["country", "year"], how="left", validate="one_to_one")
