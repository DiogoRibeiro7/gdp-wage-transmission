"""Offline reconstruction of processed panels from already-frozen raw source payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pandas as pd

from wage_transmission.data.eurostat import (
    ISO3_TO_EUROSTAT,
    EurostatCoverageError,
    _canonical_annual_series,
    jsonstat_to_frame,
    summarise_decomposition_coverage,
    validate_jsonstat_filters,
)
from wage_transmission.data.oecd import (
    PRODUCTIVITY_FLOW,
    WAGE_FLOW,
    canonicalise_average_wages,
    canonicalise_gdp_per_employed,
    canonicalise_productivity,
    select_constant_price_wages,
    validate_productivity_selection,
)
from wage_transmission.data.panel import add_driver, merge_wages_productivity
from wage_transmission.data.snapshots import verify_snapshot

OfflineProductivityMeasure = Literal["GDPHRS", "GDPEMP"]


def _read_verified_csv(path: Path, *, require_metadata: bool) -> pd.DataFrame:
    if require_metadata:
        verify_snapshot(path)
    return pd.read_csv(path, low_memory=False)


def build_oecd_panel_from_snapshots(
    wage_snapshot: Path,
    productivity_snapshot: Path,
    *,
    measure: OfflineProductivityMeasure,
    require_metadata: bool = True,
) -> pd.DataFrame:
    """Rebuild a canonical OECD panel using bytes already frozen under ``data/raw``."""
    wage_raw = _read_verified_csv(wage_snapshot, require_metadata=require_metadata)
    productivity_raw = _read_verified_csv(productivity_snapshot, require_metadata=require_metadata)
    if require_metadata:
        wage_meta = verify_snapshot(wage_snapshot)
        productivity_meta = verify_snapshot(productivity_snapshot)
        if wage_meta.flow is not None and wage_meta.flow != WAGE_FLOW:
            raise ValueError(
                f"Wage snapshot flow mismatch: expected {WAGE_FLOW}, got {wage_meta.flow}."
            )
        if productivity_meta.flow is not None and productivity_meta.flow != PRODUCTIVITY_FLOW:
            raise ValueError(
                "Productivity snapshot flow mismatch: "
                f"expected {PRODUCTIVITY_FLOW}, got {productivity_meta.flow}."
            )
        if productivity_meta.measure is not None and productivity_meta.measure != measure:
            raise ValueError(
                f"Productivity snapshot metadata expected measure {measure}, "
                f"got {productivity_meta.measure}."
            )
    wages = canonicalise_average_wages(select_constant_price_wages(wage_raw))
    validate_productivity_selection(productivity_raw, measure)

    if measure == "GDPHRS":
        productivity = canonicalise_productivity(productivity_raw)
        return merge_wages_productivity(wages, productivity)
    if measure == "GDPEMP":
        per_worker = canonicalise_gdp_per_employed(productivity_raw)
        base = wages.loc[:, ["country", "year", "real_wage"]].copy()
        panel = add_driver(base, per_worker, column="productivity_per_worker")
        return panel.dropna(subset=["productivity_per_worker"]).reset_index(drop=True)
    raise ValueError(f"Unsupported OECD productivity measure: {measure!r}")


def _read_verified_json(path: Path, *, require_metadata: bool) -> dict[str, object]:
    if require_metadata:
        verify_snapshot(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in Eurostat snapshot: {path}")
    return payload


def build_decomposition_from_snapshots(
    raw_dir: Path,
    *,
    countries: list[str],
    start_year: int,
    end_year: int,
    coverage_path: Path | None = None,
    require_metadata: bool = True,
) -> pd.DataFrame:
    """Reconstruct the Eurostat decomposition panel from frozen JSON-stat payloads."""
    source_specs = {
        "nominal_gdp": (
            "EUROSTAT_NAMA_10_GDP_CP",
            "nama_10_gdp",
            {"freq": "A", "unit": "CP_MEUR", "na_item": "B1GQ"},
        ),
        "real_gdp": (
            "EUROSTAT_NAMA_10_GDP_CLV20",
            "nama_10_gdp",
            {"freq": "A", "unit": "CLV20_MEUR", "na_item": "B1GQ"},
        ),
        "employee_compensation": (
            "EUROSTAT_NAMA_10_GDP_D1",
            "nama_10_gdp",
            {"freq": "A", "unit": "CP_MEUR", "na_item": "D1"},
        ),
        "employees": (
            "EUROSTAT_NAMA_10_PE_SAL_DC",
            "nama_10_pe",
            {"freq": "A", "unit": "THS_PER", "na_item": "SAL_DC"},
        ),
        "consumer_price_index": (
            "EUROSTAT_PRC_HICP_AIND_CP00",
            "prc_hicp_aind",
            {"freq": "A", "unit": "INX_A_AVG", "coicop": "CP00"},
        ),
    }
    series_frames: dict[str, pd.DataFrame] = {}
    for value_name, (source, dataset, expected_filters) in source_specs.items():
        rows: list[pd.DataFrame] = []
        requested_any = False
        for country in countries:
            path = raw_dir / f"eurostat_{value_name}_{country}_{start_year}_{end_year}.json"
            if not path.exists():
                continue
            requested_any = True
            payload = _read_verified_json(path, require_metadata=require_metadata)
            if require_metadata:
                metadata = verify_snapshot(path)
                if metadata.dataset is not None and metadata.dataset != dataset:
                    raise ValueError(
                        f"Eurostat snapshot dataset mismatch for {value_name}: "
                        f"expected {dataset}, got {metadata.dataset}."
                    )
            geo = ISO3_TO_EUROSTAT.get(country)
            if geo is None:
                continue
            try:
                validate_jsonstat_filters(
                    payload,
                    expected={**expected_filters, "geo": geo},
                )
            except EurostatCoverageError:
                # A valid response with no observations. The country keeps its place in the
                # configured list and the coverage report records the gap, so the absence is
                # explicit rather than a silent drop.
                continue
            decoded = jsonstat_to_frame(payload)
            canonical = _canonical_annual_series(
                decoded,
                country=country,
                start_year=start_year,
                end_year=end_year,
                value_name=value_name,
                source=source,
            )
            if not canonical.empty:
                rows.append(canonical)
        if rows:
            series_frames[value_name] = pd.concat(rows, ignore_index=True)
        elif requested_any:
            # Individual countries may legitimately have no coverage, but a series where every
            # requested country is empty means the query itself is wrong, not the source.
            raise ValueError(
                f"No configured country returned observations for {value_name!r} from "
                f"{dataset!r}. This indicates a broken query rather than a coverage gap."
            )
        else:
            series_frames[value_name] = pd.DataFrame(
                columns=["country", "year", value_name, "source"]
            )

    if coverage_path is not None:
        coverage = summarise_decomposition_coverage(
            series_frames,
            countries=countries,
            start_year=start_year,
            end_year=end_year,
        )
        coverage_path.parent.mkdir(parents=True, exist_ok=True)
        coverage.to_csv(coverage_path, index=False)

    merged: pd.DataFrame | None = None
    for value_name, frame in series_frames.items():
        current = frame.loc[:, ["country", "year", value_name]].copy()
        merged = (
            current
            if merged is None
            else merged.merge(
                current,
                on=["country", "year"],
                how="inner",
                validate="one_to_one",
            )
        )
    if merged is None:
        return pd.DataFrame(columns=["country", "year", *source_specs])
    return merged.sort_values(["country", "year"]).reset_index(drop=True)
