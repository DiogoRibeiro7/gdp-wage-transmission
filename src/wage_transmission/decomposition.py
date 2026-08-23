"""Accounting decomposition of real compensation per employee growth."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REQUIRED = (
    "year",
    "nominal_gdp",
    "real_gdp",
    "employee_compensation",
    "employees",
    "consumer_price_index",
)

COMPONENT_COLUMNS = (
    "real_gdp_component",
    "labour_share_component",
    "employment_component",
    "relative_price_component",
)


@dataclass(frozen=True)
class DecompositionSummary:
    """Cumulative log-change contributions over one country's common sample."""

    country: str | None
    start_year: int
    end_year: int
    n_growth_observations: int
    observed_real_wage_log_change: float
    real_gdp_log_contribution: float
    labour_share_log_contribution: float
    employment_log_contribution: float
    relative_price_log_contribution: float
    decomposed_real_wage_log_change: float
    max_abs_identity_residual: float


def decompose_real_wage_growth(frame: pd.DataFrame) -> pd.DataFrame:
    """Decompose real compensation-per-employee growth.

    Define labour share ``s_L = compensation / nominal GDP`` and the implicit GDP deflator
    ``P_Y = nominal GDP / real GDP``. With a consumer-price index ``P_C``:

    ``real compensation per employee = s_L * real GDP * P_Y / (employees * P_C)``.

    Therefore the exact log-growth identity is

    ``g_w = g_Y + g_sL - g_N + (pi_Y - pi_C)``.

    Eurostat reports compensation/GDP in million euro and employees in thousands of persons. Those
    fixed scale factors do not affect log differences. The returned ``identity_residual`` should be
    numerical noise when all inputs are aligned.
    """
    missing = set(REQUIRED).difference(frame.columns)
    if missing:
        raise ValueError(f"Missing decomposition columns: {sorted(missing)}")
    data = frame.loc[:, list(REQUIRED)].copy().sort_values("year").reset_index(drop=True)
    numeric = [column for column in REQUIRED if column != "year"]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data[numeric].isna().any().any():
        raise ValueError("Decomposition input contains non-numeric or missing level values.")
    if (data[numeric] <= 0).any().any():
        raise ValueError("All decomposition level series must be positive.")
    if data["year"].duplicated().any():
        raise ValueError("Decomposition input must be unique by year.")

    data["labour_share"] = data["employee_compensation"] / data["nominal_gdp"]
    data["gdp_deflator"] = data["nominal_gdp"] / data["real_gdp"]
    data["real_compensation_per_employee"] = (
        data["employee_compensation"] / data["employees"] / data["consumer_price_index"]
    )

    def dlog(column: str) -> pd.Series:
        return np.log(data[column]).diff()

    data["real_gdp_component"] = dlog("real_gdp")
    data["labour_share_component"] = dlog("labour_share")
    data["employment_component"] = -dlog("employees")
    data["relative_price_component"] = dlog("gdp_deflator") - dlog("consumer_price_index")
    data["observed_real_wage_growth"] = dlog("real_compensation_per_employee")
    data["decomposed_real_wage_growth"] = data[list(COMPONENT_COLUMNS)].sum(axis=1, min_count=4)
    data["identity_residual"] = (
        data["observed_real_wage_growth"] - data["decomposed_real_wage_growth"]
    )
    return data


def summarise_decomposition(
    frame: pd.DataFrame,
    *,
    country: str | None = None,
) -> DecompositionSummary:
    """Summarise cumulative contributions from an already decomposed country frame."""
    required = {
        "year",
        "observed_real_wage_growth",
        "decomposed_real_wage_growth",
        "identity_residual",
        *COMPONENT_COLUMNS,
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing decomposed columns: {sorted(missing)}")
    growth = frame.dropna(
        subset=["observed_real_wage_growth", "decomposed_real_wage_growth", *COMPONENT_COLUMNS]
    ).copy()
    if growth.empty:
        raise ValueError("At least one complete decomposition growth observation is required.")
    residual = pd.to_numeric(growth["identity_residual"], errors="coerce").dropna()
    max_residual = float(residual.abs().max()) if not residual.empty else float("nan")
    return DecompositionSummary(
        country=country,
        start_year=int(frame["year"].min()),
        end_year=int(frame["year"].max()),
        n_growth_observations=int(len(growth)),
        observed_real_wage_log_change=float(growth["observed_real_wage_growth"].sum()),
        real_gdp_log_contribution=float(growth["real_gdp_component"].sum()),
        labour_share_log_contribution=float(growth["labour_share_component"].sum()),
        employment_log_contribution=float(growth["employment_component"].sum()),
        relative_price_log_contribution=float(growth["relative_price_component"].sum()),
        decomposed_real_wage_log_change=float(growth["decomposed_real_wage_growth"].sum()),
        max_abs_identity_residual=max_residual,
    )


def decompose_panel(frame: pd.DataFrame) -> tuple[pd.DataFrame, tuple[DecompositionSummary, ...]]:
    """Run the exact accounting decomposition separately for every country in a panel."""
    if "country" not in frame.columns:
        decomposed = decompose_real_wage_growth(frame)
        return decomposed, (summarise_decomposition(decomposed),)

    outputs: list[pd.DataFrame] = []
    summaries: list[DecompositionSummary] = []
    for country, group in frame.groupby("country", sort=True):
        decomposed = decompose_real_wage_growth(group)
        decomposed.insert(0, "country", str(country))
        outputs.append(decomposed)
        summaries.append(summarise_decomposition(decomposed, country=str(country)))
    if not outputs:
        return pd.DataFrame(), tuple()
    return pd.concat(outputs, ignore_index=True), tuple(summaries)
