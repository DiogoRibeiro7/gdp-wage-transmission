"""Median-earnings series, attached only where harmonised coverage permits.

Mean and median wages answer different questions. A mean annual wage moves with the top of the
distribution; a median moves with the middle. Transmission estimated on the mean and on the
median can differ for reasons that have nothing to do with the transmission mechanism, so the
two are kept as separate series and never substituted for one another.

Harmonised median earnings are far patchier than mean wages: they are collected less often, on
different reference concepts, and for fewer countries. Attaching a sparse median series to a
panel silently changes which countries and years identify a coefficient. Everything here is
therefore gated on measured coverage, and a country that fails the gate is dropped explicitly
and reported rather than carried with gaps.

The source flow is supplied by the caller rather than hard-coded. Median-earnings dataflow
identifiers differ by provider and vintage, and a wrong identifier that silently returns a
neighbouring concept is exactly the failure this package is built to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from wage_transmission.data.common import canonical_observations

MEDIAN_VALUE_COLUMN = "median_wage"
DEFAULT_MIN_COVERAGE = 0.8


@dataclass(frozen=True)
class MedianWageSpec:
    """A median-earnings selection, supplied from configuration rather than assumed."""

    flow_ref: str
    key_template: str
    source: str
    label: str
    value_name: str = MEDIAN_VALUE_COLUMN

    def __post_init__(self) -> None:
        if not self.flow_ref.strip():
            raise ValueError(
                "A median-earnings flow reference must be supplied explicitly; there is no "
                "safe default, because a wrong dataflow returns a neighbouring concept."
            )


@dataclass(frozen=True)
class CountryCoverage:
    """Observed coverage of a median series for one country over a requested window."""

    country: str
    observed_years: int
    requested_years: int
    coverage: float
    first_year: int
    last_year: int
    eligible: bool


def canonicalise_median_wages(frame: pd.DataFrame, *, spec: MedianWageSpec) -> pd.DataFrame:
    """Reduce a labelled median-earnings response to canonical country-year observations."""
    return canonical_observations(frame, value_name=spec.value_name, source=spec.source)


def assess_median_coverage(
    median: pd.DataFrame,
    *,
    start_year: int,
    end_year: int,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    value_name: str = MEDIAN_VALUE_COLUMN,
) -> tuple[CountryCoverage, ...]:
    """Measure per-country coverage of a median series over the requested window."""
    if end_year < start_year:
        raise ValueError("end_year must not precede start_year")
    if not 0.0 < min_coverage <= 1.0:
        raise ValueError("min_coverage must lie in (0, 1]")
    missing = {"country", "year", value_name}.difference(median.columns)
    if missing:
        raise ValueError(f"Median series is missing columns: {sorted(missing)}")

    requested = end_year - start_year + 1
    window = median.loc[median["year"].between(start_year, end_year) & median[value_name].notna()]

    reports: list[CountryCoverage] = []
    for country, rows in window.groupby("country", sort=True):
        observed = int(rows["year"].nunique())
        coverage = observed / requested
        reports.append(
            CountryCoverage(
                country=str(country),
                observed_years=observed,
                requested_years=requested,
                coverage=float(coverage),
                first_year=int(rows["year"].min()),
                last_year=int(rows["year"].max()),
                eligible=bool(coverage >= min_coverage),
            )
        )
    return tuple(reports)


def attach_median_wages(
    panel: pd.DataFrame,
    median: pd.DataFrame,
    *,
    start_year: int,
    end_year: int,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    value_name: str = MEDIAN_VALUE_COLUMN,
) -> tuple[pd.DataFrame, tuple[CountryCoverage, ...]]:
    """Attach a median series to the panel for eligible countries only.

    Returns the panel with the median column added, and the full coverage report including the
    countries that were excluded. The report is part of the return value rather than a log line
    because which countries were dropped changes what the estimates mean.
    """
    missing = {"country", "year"}.difference(panel.columns)
    if missing:
        raise ValueError(f"Panel is missing columns: {sorted(missing)}")

    coverage = assess_median_coverage(
        median,
        start_year=start_year,
        end_year=end_year,
        min_coverage=min_coverage,
        value_name=value_name,
    )
    eligible = {report.country for report in coverage if report.eligible}
    if not eligible:
        raise ValueError(
            "No country meets the median-earnings coverage threshold of "
            f"{min_coverage:.0%} over {start_year}-{end_year}; the series cannot be used."
        )

    usable = median.loc[median["country"].isin(eligible), ["country", "year", value_name]]
    merged = panel.merge(usable, on=["country", "year"], how="left")
    return merged, coverage
