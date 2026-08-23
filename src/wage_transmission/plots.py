"""Publication-oriented plots built from model outputs."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wage_transmission.models.local_projections import LocalProjectionPoint
from wage_transmission.models.state_space import TimeVaryingElasticityResult


def plot_levels(frame: pd.DataFrame, path: Path) -> Path:
    """Plot indexed real wages and productivity on a common base year."""
    data = frame.sort_values("year").copy()
    wage_index = 100.0 * data["real_wage"] / float(data["real_wage"].iloc[0])
    prod_index = 100.0 * data["productivity"] / float(data["productivity"].iloc[0])
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(data["year"], wage_index, label="Real wage")
    ax.plot(data["year"], prod_index, label="Productivity")
    ax.set_ylabel("Index, first year = 100")
    ax.set_xlabel("Year")
    ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_time_varying_elasticity(result: TimeVaryingElasticityResult, path: Path) -> Path:
    """Plot filtered state-space elasticity with approximate 95% interval."""
    lower = result.elasticity - 1.96 * result.elasticity_std_error
    upper = result.elasticity + 1.96 * result.elasticity_std_error
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(result.year, result.elasticity, label="Transmission elasticity")
    ax.fill_between(result.year, lower, upper, alpha=0.2)
    ax.axhline(1.0, linestyle="--", linewidth=1.0, label="One-for-one")
    ax.set_ylabel("Elasticity")
    ax.set_xlabel("Year")
    ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_local_projections(points: tuple[LocalProjectionPoint, ...], path: Path) -> Path:
    """Plot local-projection response coefficients and 95% intervals."""
    horizons = [point.horizon for point in points]
    estimates = [point.estimate for point in points]
    lower = [point.lower_95 for point in points]
    upper = [point.upper_95 for point in points]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(horizons, estimates, marker="o")
    ax.fill_between(horizons, lower, upper, alpha=0.2)
    ax.axhline(0.0, linestyle="--", linewidth=1.0)
    ax.set_xlabel("Horizon (years)")
    ax.set_ylabel("Cumulative log-wage response")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_decomposition_components(frame: pd.DataFrame, path: Path) -> Path:
    """Plot annual log-growth contributions in the exact accounting decomposition."""
    required = {
        "year",
        "real_gdp_component",
        "labour_share_component",
        "employment_component",
        "relative_price_component",
        "observed_real_wage_growth",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing decomposition plot columns: {sorted(missing)}")
    data = frame.sort_values("year").dropna(subset=["observed_real_wage_growth"]).copy()
    if data.empty:
        raise ValueError("No complete decomposition observations to plot.")

    component_columns = [
        "real_gdp_component",
        "labour_share_component",
        "employment_component",
        "relative_price_component",
    ]
    labels = ["Real GDP", "Labour share", "Employees", "Relative prices"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    positive_bottom = np.zeros(len(data), dtype=float)
    negative_bottom = np.zeros(len(data), dtype=float)
    for column, label in zip(component_columns, labels, strict=True):
        values = data[column].to_numpy(dtype=float)
        bottoms = np.where(values >= 0.0, positive_bottom, negative_bottom)
        ax.bar(data["year"], values, bottom=bottoms, label=label, alpha=0.75)
        positive_bottom = positive_bottom + np.where(values >= 0.0, values, 0.0)
        negative_bottom = negative_bottom + np.where(values < 0.0, values, 0.0)
    ax.plot(
        data["year"],
        data["observed_real_wage_growth"],
        marker="o",
        linewidth=1.5,
        label="Observed real compensation/employee growth",
    )
    ax.axhline(0.0, linewidth=0.8)
    ax.set_xlabel("Year")
    ax.set_ylabel("Log change")
    ax.legend(ncol=2)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_cumulative_decomposition(frame: pd.DataFrame, path: Path) -> Path:
    """Plot cumulative log-change contributions from the first complete growth observation."""
    required = {
        "year",
        "real_gdp_component",
        "labour_share_component",
        "employment_component",
        "relative_price_component",
        "observed_real_wage_growth",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing decomposition plot columns: {sorted(missing)}")
    data = frame.sort_values("year").dropna(subset=["observed_real_wage_growth"]).copy()
    if data.empty:
        raise ValueError("No complete decomposition observations to plot.")

    series = {
        "Observed real compensation/employee": data["observed_real_wage_growth"].cumsum(),
        "Real GDP contribution": data["real_gdp_component"].cumsum(),
        "Labour-share contribution": data["labour_share_component"].cumsum(),
        "Employment contribution": data["employment_component"].cumsum(),
        "Relative-price contribution": data["relative_price_component"].cumsum(),
    }
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for label, values in series.items():
        ax.plot(data["year"], values, label=label)
    ax.axhline(0.0, linewidth=0.8)
    ax.set_xlabel("Year")
    ax.set_ylabel("Cumulative log change")
    ax.legend(ncol=2)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
