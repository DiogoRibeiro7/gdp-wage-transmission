"""Eurostat Statistics API client and canonical national-accounts extractors."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import product
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import pandas as pd

from wage_transmission.data.common import write_snapshot

EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def _ordered_codes(category: Mapping[str, Any]) -> list[str]:
    """Return category codes in JSON-stat index order."""
    raw_index = category.get("index", {})
    if isinstance(raw_index, list):
        return [str(value) for value in raw_index]
    if isinstance(raw_index, dict):
        return [key for key, _ in sorted(raw_index.items(), key=lambda item: int(item[1]))]
    raise ValueError("Unsupported JSON-stat category index representation.")


def validate_jsonstat_filters(
    payload: Mapping[str, Any],
    *,
    expected: Mapping[str, str],
) -> None:
    """Validate that filtered JSON-stat dimensions contain exactly the expected source codes.

    Hash verification proves byte integrity, not semantic identity. This contract prevents a valid
    but incorrectly downloaded Eurostat response from being canonicalised under the wrong series
    name.
    """
    dim_payload = payload.get("dimension", {})
    if not isinstance(dim_payload, Mapping):
        raise ValueError("Invalid JSON-stat dimension object.")
    for dimension, expected_code in expected.items():
        raw_dimension = dim_payload.get(dimension)
        if not isinstance(raw_dimension, Mapping):
            raise ValueError(f"Eurostat payload is missing expected dimension {dimension!r}.")
        category = raw_dimension.get("category")
        if not isinstance(category, Mapping):
            raise ValueError(f"Eurostat dimension {dimension!r} has no category object.")
        codes = _ordered_codes(category)
        if codes != [expected_code]:
            raise ValueError(
                f"Eurostat semantic contract failed for {dimension!r}: "
                f"expected only {expected_code!r}, got {codes!r}."
            )


def jsonstat_to_frame(payload: Mapping[str, Any]) -> pd.DataFrame:
    """Decode a Eurostat JSON-stat dataset into a tidy DataFrame."""
    dimensions = [str(value) for value in payload.get("id", [])]
    sizes = [int(value) for value in payload.get("size", [])]
    if not dimensions or len(dimensions) != len(sizes):
        raise ValueError("Invalid JSON-stat dimensions or sizes.")

    dim_payload = payload.get("dimension", {})
    codes: list[list[str]] = []
    for dimension in dimensions:
        category = dim_payload[dimension]["category"]
        dimension_codes = _ordered_codes(category)
        if len(dimension_codes) != sizes[len(codes)]:
            raise ValueError(f"Dimension size mismatch for {dimension}.")
        codes.append(dimension_codes)

    value_map = payload.get("value", {})
    rows: list[dict[str, Any]] = []
    for flat_index, coordinate in enumerate(product(*codes)):
        value = value_map.get(str(flat_index), value_map.get(flat_index))
        if value is None:
            continue
        row = dict(zip(dimensions, coordinate, strict=True))
        row["OBS_VALUE"] = value
        rows.append(row)
    return pd.DataFrame(rows)


def build_eurostat_url(dataset: str, *, filters: Mapping[str, str | int]) -> str:
    """Build a deterministic Eurostat Statistics API URL without performing a request."""
    params = {"format": "JSON", "lang": "EN", **filters}
    return f"{EUROSTAT_BASE}/{dataset}?{urlencode(params)}"


def fetch_eurostat(
    dataset: str,
    *,
    filters: Mapping[str, str | int],
    raw_path: Path | None = None,
    timeout: float = 60.0,
) -> pd.DataFrame:
    """Fetch a filtered Eurostat dataset through the Statistics API."""
    url = build_eurostat_url(dataset, filters=filters)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
    content = response.content
    if raw_path is not None:
        write_snapshot(
            content,
            raw_path,
            {
                "source": "Eurostat",
                "dataset": dataset,
                "url": url,
                "filters": dict(filters),
            },
        )
    payload = response.json()
    return jsonstat_to_frame(payload)


ISO3_TO_EUROSTAT = {
    "AUT": "AT",
    "BEL": "BE",
    "CZE": "CZ",
    "DEU": "DE",
    "DNK": "DK",
    "ESP": "ES",
    "EST": "EE",
    "FIN": "FI",
    "FRA": "FR",
    "GBR": "UK",
    "GRC": "EL",
    "IRL": "IE",
    "ITA": "IT",
    "LTU": "LT",
    "LUX": "LU",
    "LVA": "LV",
    "NLD": "NL",
    "POL": "PL",
    "PRT": "PT",
    "SVK": "SK",
    "SVN": "SI",
    "SWE": "SE",
    "USA": "US",
}
EUROSTAT_TO_ISO3 = {value: key for key, value in ISO3_TO_EUROSTAT.items()}


def _canonical_annual_series(
    frame: pd.DataFrame,
    *,
    country: str,
    start_year: int,
    end_year: int,
    value_name: str,
    source: str,
) -> pd.DataFrame:
    """Reduce one filtered Eurostat response to a unique country-year level series."""
    if frame.empty:
        return pd.DataFrame(columns=["country", "year", value_name, "source"])
    if "time" not in frame.columns or "OBS_VALUE" not in frame.columns:
        raise ValueError(
            "Unexpected Eurostat response dimensions: expected `time` and `OBS_VALUE`."
        )

    out = frame.loc[:, ["time", "OBS_VALUE"]].copy()
    out["year"] = pd.to_numeric(out["time"], errors="coerce")
    out[value_name] = pd.to_numeric(out["OBS_VALUE"], errors="coerce")
    out = out.dropna(subset=["year", value_name])
    out["year"] = out["year"].astype(int)
    out = out.loc[out["year"].between(start_year, end_year), ["year", value_name]]
    out["country"] = country
    out["source"] = source
    if out.duplicated(["country", "year"]).any():
        raise ValueError(f"Eurostat selection for {value_name} is not unique by country-year.")
    return (
        out.loc[:, ["country", "year", value_name, "source"]]
        .sort_values("year")
        .reset_index(drop=True)
    )


def _download_annual_series(
    countries: list[str],
    *,
    dataset: str,
    filters: Mapping[str, str | int],
    value_name: str,
    source: str,
    start_year: int,
    end_year: int,
    raw_dir: Path | None,
) -> pd.DataFrame:
    """Download one Eurostat annual series for all supported requested countries."""
    if start_year > end_year:
        raise ValueError("start_year must be <= end_year")
    rows: list[pd.DataFrame] = []
    for country in countries:
        geo = ISO3_TO_EUROSTAT.get(country)
        if geo is None:
            continue
        raw_path = None
        if raw_dir is not None:
            raw_path = raw_dir / f"eurostat_{value_name}_{country}_{start_year}_{end_year}.json"
        frame = fetch_eurostat(
            dataset,
            filters={
                **filters,
                "geo": geo,
                "sinceTimePeriod": start_year,
                "untilTimePeriod": end_year,
            },
            raw_path=raw_path,
        )
        canonical = _canonical_annual_series(
            frame,
            country=country,
            start_year=start_year,
            end_year=end_year,
            value_name=value_name,
            source=source,
        )
        if not canonical.empty:
            rows.append(canonical)
    if not rows:
        return pd.DataFrame(columns=["country", "year", value_name, "source"])
    return (
        pd.concat(rows, ignore_index=True).sort_values(["country", "year"]).reset_index(drop=True)
    )


def download_real_gdp(
    countries: list[str],
    *,
    start_year: int,
    end_year: int,
    raw_dir: Path | None = None,
) -> pd.DataFrame:
    """Download annual real GDP in chain-linked 2020 million euro units."""
    return _download_annual_series(
        countries,
        dataset="nama_10_gdp",
        filters={"freq": "A", "unit": "CLV20_MEUR", "na_item": "B1GQ"},
        value_name="real_gdp",
        source="EUROSTAT_NAMA_10_GDP_CLV20",
        start_year=start_year,
        end_year=end_year,
        raw_dir=raw_dir,
    )


def download_nominal_gdp(
    countries: list[str],
    *,
    start_year: int,
    end_year: int,
    raw_dir: Path | None = None,
) -> pd.DataFrame:
    """Download GDP at current market prices in million euro."""
    return _download_annual_series(
        countries,
        dataset="nama_10_gdp",
        filters={"freq": "A", "unit": "CP_MEUR", "na_item": "B1GQ"},
        value_name="nominal_gdp",
        source="EUROSTAT_NAMA_10_GDP_CP",
        start_year=start_year,
        end_year=end_year,
        raw_dir=raw_dir,
    )


def download_employee_compensation(
    countries: list[str],
    *,
    start_year: int,
    end_year: int,
    raw_dir: Path | None = None,
) -> pd.DataFrame:
    """Download compensation of employees (ESA transaction D.1) in million euro."""
    return _download_annual_series(
        countries,
        dataset="nama_10_gdp",
        filters={"freq": "A", "unit": "CP_MEUR", "na_item": "D1"},
        value_name="employee_compensation",
        source="EUROSTAT_NAMA_10_GDP_D1",
        start_year=start_year,
        end_year=end_year,
        raw_dir=raw_dir,
    )


def download_employees(
    countries: list[str],
    *,
    start_year: int,
    end_year: int,
    raw_dir: Path | None = None,
) -> pd.DataFrame:
    """Download employees in the domestic concept (SAL_DC), thousands of persons.

    ``SAL_DC`` is used rather than total employment ``EMP_DC`` because compensation of employees
    belongs to employees. Mixing D.1 with employees plus self-employed would break the intended
    per-employee accounting interpretation.
    """
    return _download_annual_series(
        countries,
        dataset="nama_10_pe",
        filters={"freq": "A", "unit": "THS_PER", "na_item": "SAL_DC"},
        value_name="employees",
        source="EUROSTAT_NAMA_10_PE_SAL_DC",
        start_year=start_year,
        end_year=end_year,
        raw_dir=raw_dir,
    )


def download_hicp_index(
    countries: list[str],
    *,
    start_year: int,
    end_year: int,
    raw_dir: Path | None = None,
) -> pd.DataFrame:
    """Download the all-items HICP annual-average index.

    The index base is irrelevant for log growth because any constant rebasing cancels. HICP is used
    as the consumer-price deflator in the real-compensation-per-employee accounting decomposition.
    """
    return _download_annual_series(
        countries,
        dataset="prc_hicp_aind",
        filters={"freq": "A", "unit": "INX_A_AVG", "coicop": "CP00"},
        value_name="consumer_price_index",
        source="EUROSTAT_PRC_HICP_AIND_CP00",
        start_year=start_year,
        end_year=end_year,
        raw_dir=raw_dir,
    )


def summarise_decomposition_coverage(
    series: Mapping[str, pd.DataFrame],
    *,
    countries: list[str],
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """Summarise source-by-source country coverage before the common-sample inner join.

    Keeping this audit separate from the merged decomposition panel prevents an incomplete source
    from disappearing silently when the five required series are intersected by country-year.
    """
    if start_year > end_year:
        raise ValueError("start_year must be <= end_year")
    expected = end_year - start_year + 1
    records: list[dict[str, str | int | float | None]] = []
    for value_name, frame in series.items():
        required = {"country", "year", value_name}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(
                f"Coverage source {value_name!r} is missing columns: {sorted(missing)}"
            )
        for country in countries:
            subset = frame.loc[
                (frame["country"].astype(str) == country)
                & pd.to_numeric(frame["year"], errors="coerce").between(start_year, end_year)
            ].copy()
            years = pd.to_numeric(subset["year"], errors="coerce").dropna().astype(int)
            values = pd.to_numeric(subset[value_name], errors="coerce")
            complete_years = years.loc[values.notna()].drop_duplicates().sort_values()
            n_observations = len(complete_years)
            records.append(
                {
                    "country": country,
                    "series": value_name,
                    "first_year": int(complete_years.iloc[0]) if n_observations else None,
                    "last_year": int(complete_years.iloc[-1]) if n_observations else None,
                    "n_observations": n_observations,
                    "requested_years": expected,
                    "coverage_ratio": float(n_observations / expected),
                }
            )
    return (
        pd.DataFrame.from_records(records).sort_values(["country", "series"]).reset_index(drop=True)
    )


def download_decomposition_inputs(
    countries: list[str],
    *,
    start_year: int,
    end_year: int,
    raw_dir: Path | None = None,
    coverage_path: Path | None = None,
) -> pd.DataFrame:
    """Build the Eurostat accounting panel needed for the wage-growth decomposition.

    The output intentionally uses an inner join across the five required level series. Every row
    therefore satisfies one common country-year definition and can be passed directly to
    :func:`wage_transmission.decomposition.decompose_real_wage_growth`.
    """
    series = {
        "nominal_gdp": download_nominal_gdp(
            countries, start_year=start_year, end_year=end_year, raw_dir=raw_dir
        ),
        "real_gdp": download_real_gdp(
            countries, start_year=start_year, end_year=end_year, raw_dir=raw_dir
        ),
        "employee_compensation": download_employee_compensation(
            countries, start_year=start_year, end_year=end_year, raw_dir=raw_dir
        ),
        "employees": download_employees(
            countries, start_year=start_year, end_year=end_year, raw_dir=raw_dir
        ),
        "consumer_price_index": download_hicp_index(
            countries, start_year=start_year, end_year=end_year, raw_dir=raw_dir
        ),
    }
    if coverage_path is not None:
        coverage = summarise_decomposition_coverage(
            series,
            countries=countries,
            start_year=start_year,
            end_year=end_year,
        )
        coverage_path.parent.mkdir(parents=True, exist_ok=True)
        coverage.to_csv(coverage_path, index=False)

    value_columns = list(series)
    result: pd.DataFrame | None = None
    for value_name, frame in series.items():
        current = frame.loc[:, ["country", "year", value_name]].copy()
        result = (
            current
            if result is None
            else result.merge(
                current,
                on=["country", "year"],
                how="inner",
                validate="one_to_one",
            )
        )
    if result is None:
        return pd.DataFrame(columns=["country", "year", *value_columns])
    return result.sort_values(["country", "year"]).reset_index(drop=True)
