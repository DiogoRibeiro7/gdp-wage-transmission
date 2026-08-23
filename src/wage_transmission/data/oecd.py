"""OECD SDMX REST client for wages and productivity."""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Literal, Mapping
from urllib.parse import urlencode

import httpx
import pandas as pd

from wage_transmission.data.common import canonical_observations, write_snapshot

OECD_BASE = "https://sdmx.oecd.org/public/rest/data"
WAGE_FLOW = "OECD.ELS.SAE,DSD_EARNINGS@AV_AN_WAGE,1.0"
PRODUCTIVITY_FLOW = "OECD.SDD.TPS,DSD_PDB@DF_PDB,2.0"

ProductivityMeasure = Literal["GDPHRS", "GDPEMP"]


@dataclass(frozen=True)
class ProductivitySeriesSpec:
    """OECD Productivity Database selection for one labour-productivity concept."""

    measure: ProductivityMeasure
    unit_code: str
    value_name: str
    source: str
    label: str


PRODUCTIVITY_SERIES: dict[ProductivityMeasure, ProductivitySeriesSpec] = {
    "GDPHRS": ProductivitySeriesSpec(
        measure="GDPHRS",
        unit_code="USD_PPP_H",
        value_name="productivity",
        source="OECD_PDB_GDPHRS",
        label="GDP per hour worked",
    ),
    "GDPEMP": ProductivitySeriesSpec(
        measure="GDPEMP",
        unit_code="USD_PPP_PS",
        value_name="productivity_per_worker",
        source="OECD_PDB_GDPEMP",
        label="GDP per person employed",
    ),
}


@dataclass(frozen=True)
class OECDDownload:
    """An OECD query and its decoded response."""

    url: str
    frame: pd.DataFrame
    raw_path: Path | None = None


def build_oecd_url(
    flow_ref: str,
    key: str,
    *,
    start_year: int,
    end_year: int,
    response_format: str = "csvfilewithlabels",
) -> str:
    """Build a deterministic OECD SDMX data URL."""
    if start_year > end_year:
        raise ValueError("start_year must be <= end_year")
    params = {
        "startPeriod": start_year,
        "endPeriod": end_year,
        "dimensionAtObservation": "AllDimensions",
        "format": response_format,
    }
    return f"{OECD_BASE}/{flow_ref}/{key}?{urlencode(params)}"


def _request_csv(url: str, *, timeout: float = 60.0) -> tuple[pd.DataFrame, bytes]:
    """Request one OECD CSV payload and validate the HTTP response."""
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
    content = response.content
    frame = pd.read_csv(StringIO(content.decode("utf-8-sig")), low_memory=False)
    if frame.empty:
        raise ValueError(f"OECD query returned no rows: {url}")
    return frame, content


def _label_filter(frame: pd.DataFrame, filters: Mapping[str, str]) -> pd.DataFrame:
    """Filter labelled OECD columns when present, without guessing identifier codes."""
    out = frame.copy()
    for column, expected in filters.items():
        if column not in out.columns:
            continue
        mask = out[column].astype(str).str.contains(expected, case=False, regex=False, na=False)
        out = out.loc[mask]
    return out


def validate_productivity_selection(frame: pd.DataFrame, measure: ProductivityMeasure) -> None:
    """Validate productivity-measure identity when the labelled/code columns are present."""
    spec = PRODUCTIVITY_SERIES[measure]
    if "MEASURE" in frame.columns:
        codes = set(frame["MEASURE"].dropna().astype(str).unique())
        if codes != {measure}:
            raise ValueError(
                f"OECD productivity semantic contract expected MEASURE={measure}, got {sorted(codes)}."
            )
    if "Measure" in frame.columns:
        labels = frame["Measure"].dropna().astype(str)
        if not labels.empty and not labels.str.contains(spec.label, case=False, regex=False).all():
            observed = sorted(labels.unique().tolist())[:10]
            raise ValueError(
                f"OECD productivity semantic contract expected {spec.label!r}; got {observed!r}."
            )


def select_constant_price_wages(frame: pd.DataFrame) -> pd.DataFrame:
    """Select the OECD constant-price wage observations and fail if the label is absent.

    The current SDMX key already pins the constant-price code (``Q``). The label check remains a
    second contract guard so a future source-dimension change fails loudly rather than changing
    the economic concept silently.
    """
    filtered = _label_filter(frame, {"Price base": "Constant prices"})
    if filtered.empty:
        raise ValueError("No constant-price OECD wage observations were found in the response.")
    return filtered.reset_index(drop=True)


def download_average_wages(
    countries: list[str],
    *,
    start_year: int,
    end_year: int,
    raw_dir: Path | None = None,
) -> OECDDownload:
    """Download OECD average annual wages for selected countries.

    The query requests the OECD's constant-price PPP wage series directly. Using a common
    fixed PPP unit makes the source selection unambiguous; the within-country elasticities are
    invariant to this fixed scale conversion.
    """
    if not countries:
        raise ValueError("At least one country code is required.")
    country_key = "+".join(sorted(set(countries)))
    # OECD Data Explorer query: US dollars, PPP converted, constant-price annual wage series.
    key = f"{country_key}..USD_PPP..Q.."
    url = build_oecd_url(WAGE_FLOW, key, start_year=start_year, end_year=end_year)
    frame, content = _request_csv(url)
    filtered = select_constant_price_wages(frame)

    raw_path: Path | None = None
    if raw_dir is not None:
        raw_path = raw_dir / f"oecd_average_wages_{start_year}_{end_year}.csv"
        write_snapshot(content, raw_path, {"source": "OECD", "url": url, "flow": WAGE_FLOW})
    return OECDDownload(url=url, frame=filtered.reset_index(drop=True), raw_path=raw_path)


def download_productivity_measure(
    countries: list[str],
    *,
    measure: ProductivityMeasure,
    start_year: int,
    end_year: int,
    raw_dir: Path | None = None,
) -> OECDDownload:
    """Download one constant-price PPP productivity level from the OECD Productivity database.

    The supported measures deliberately retain their different labour denominators:

    - ``GDPHRS``: GDP per hour worked;
    - ``GDPEMP``: GDP per person employed.

    Keeping both concepts explicit prevents an annual wage measure from being silently described as
    dimensionally matched to an hourly productivity measure.
    """
    if not countries:
        raise ValueError("At least one country code is required.")
    spec = PRODUCTIVITY_SERIES[measure]
    country_key = "+".join(sorted(set(countries)))
    # The key dimensions follow the current OECD Productivity Database v2.0 layout:
    # country.frequency.measure.activity.unit.price-base.transformation.asset.conversion.
    key = f"{country_key}.A.{spec.measure}._T.{spec.unit_code}.LR.N.."
    url = build_oecd_url(PRODUCTIVITY_FLOW, key, start_year=start_year, end_year=end_year)
    frame, content = _request_csv(url)
    raw_path: Path | None = None
    if raw_dir is not None:
        raw_path = raw_dir / (
            f"oecd_{spec.measure.lower()}_{start_year}_{end_year}.csv"
        )
        write_snapshot(
            content,
            raw_path,
            {
                "source": "OECD",
                "url": url,
                "flow": PRODUCTIVITY_FLOW,
                "measure": spec.measure,
                "label": spec.label,
            },
        )
    return OECDDownload(url=url, frame=frame.reset_index(drop=True), raw_path=raw_path)


def download_productivity(
    countries: list[str],
    *,
    start_year: int,
    end_year: int,
    raw_dir: Path | None = None,
) -> OECDDownload:
    """Download GDP per hour worked; retained as the backwards-compatible primary helper."""
    return download_productivity_measure(
        countries,
        measure="GDPHRS",
        start_year=start_year,
        end_year=end_year,
        raw_dir=raw_dir,
    )


def download_gdp_per_employed(
    countries: list[str],
    *,
    start_year: int,
    end_year: int,
    raw_dir: Path | None = None,
) -> OECDDownload:
    """Download GDP per person employed for the annual-wage matched-denominator specification."""
    return download_productivity_measure(
        countries,
        measure="GDPEMP",
        start_year=start_year,
        end_year=end_year,
        raw_dir=raw_dir,
    )


def canonicalise_average_wages(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert an OECD wage response to canonical country-year wage data."""
    return canonical_observations(frame, value_name="real_wage", source="OECD_AV_AN_WAGE")


def canonicalise_productivity(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert an OECD productivity response to canonical country-year productivity data."""
    return canonical_observations(frame, value_name="productivity", source="OECD_PDB_GDPHRS")


def canonicalise_gdp_per_employed(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert GDP-per-employed observations to a denominator-explicit canonical column."""
    spec = PRODUCTIVITY_SERIES["GDPEMP"]
    return canonical_observations(frame, value_name=spec.value_name, source=spec.source)
