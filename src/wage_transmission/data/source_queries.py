"""Deterministic source-query manifests for externally reproducible raw-data freezes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from wage_transmission.data.eurostat import ISO3_TO_EUROSTAT, build_eurostat_url
from wage_transmission.data.oecd import PRODUCTIVITY_FLOW, WAGE_FLOW, build_oecd_url


@dataclass(frozen=True)
class SourceQuery:
    """One official source request and its expected immutable raw destination."""

    query_id: str
    source: str
    purpose: str
    url: str
    expected_raw_path: str
    dataset: str | None = None
    flow: str | None = None
    measure: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Convert the query definition to a JSON-compatible object."""
        return asdict(self)


def build_source_queries(
    *,
    countries: list[str],
    decomposition_countries: list[str],
    start_year: int,
    end_year: int,
    raw_root: Path,
) -> tuple[SourceQuery, ...]:
    """Build every current OECD/Eurostat query required for a publication data freeze."""
    if not countries:
        raise ValueError("At least one OECD country is required.")
    if start_year > end_year:
        raise ValueError("start_year must be <= end_year")

    country_key = "+".join(sorted(set(countries)))
    queries: list[SourceQuery] = []
    wage_key = f"{country_key}..USD_PPP..Q.."
    queries.append(
        SourceQuery(
            query_id="oecd_average_wages",
            source="OECD",
            purpose="Average annual wages, constant-price PPP series",
            url=build_oecd_url(WAGE_FLOW, wage_key, start_year=start_year, end_year=end_year),
            expected_raw_path=str(raw_root / f"oecd_average_wages_{start_year}_{end_year}.csv"),
            flow=WAGE_FLOW,
        )
    )
    for measure, unit, purpose in (
        ("GDPHRS", "USD_PPP_H", "GDP per hour worked"),
        ("GDPEMP", "USD_PPP_PS", "GDP per person employed"),
    ):
        key = f"{country_key}.A.{measure}._T.{unit}.LR.N.."
        queries.append(
            SourceQuery(
                query_id=f"oecd_{measure.lower()}",
                source="OECD",
                purpose=purpose,
                url=build_oecd_url(
                    PRODUCTIVITY_FLOW, key, start_year=start_year, end_year=end_year
                ),
                expected_raw_path=str(
                    raw_root / f"oecd_{measure.lower()}_{start_year}_{end_year}.csv"
                ),
                flow=PRODUCTIVITY_FLOW,
                measure=measure,
            )
        )

    eurostat_specs = {
        "nominal_gdp": ("nama_10_gdp", {"freq": "A", "unit": "CP_MEUR", "na_item": "B1GQ"}),
        "real_gdp": ("nama_10_gdp", {"freq": "A", "unit": "CLV20_MEUR", "na_item": "B1GQ"}),
        "employee_compensation": (
            "nama_10_gdp",
            {"freq": "A", "unit": "CP_MEUR", "na_item": "D1"},
        ),
        "employees": ("nama_10_pe", {"freq": "A", "unit": "THS_PER", "na_item": "SAL_DC"}),
        "consumer_price_index": (
            "prc_hicp_aind",
            {"freq": "A", "unit": "INX_A_AVG", "coicop": "CP00"},
        ),
    }
    for country in decomposition_countries:
        geo = ISO3_TO_EUROSTAT.get(country)
        if geo is None:
            continue
        for value_name, (dataset, filters) in eurostat_specs.items():
            url = build_eurostat_url(
                dataset,
                filters={
                    **filters,
                    "geo": geo,
                    "sinceTimePeriod": start_year,
                    "untilTimePeriod": end_year,
                },
            )
            queries.append(
                SourceQuery(
                    query_id=f"eurostat_{value_name}_{country}",
                    source="Eurostat",
                    purpose=value_name,
                    url=url,
                    expected_raw_path=str(
                        raw_root / f"eurostat_{value_name}_{country}_{start_year}_{end_year}.json"
                    ),
                    dataset=dataset,
                )
            )
    return tuple(queries)


def audit_source_freeze(queries: tuple[SourceQuery, ...]) -> pd.DataFrame:
    """Audit expected query-manifest payloads against the immutable raw snapshot store."""
    from wage_transmission.data.snapshots import metadata_path_for, verify_snapshot

    records: list[dict[str, str | int]] = []
    for query in queries:
        raw_path = Path(query.expected_raw_path)
        metadata_path = metadata_path_for(raw_path)
        status = "missing"
        digest = ""
        byte_count = 0
        message = "raw payload not found"
        if raw_path.exists() and not metadata_path.exists():
            status = "unverified"
            message = "raw payload exists but adjacent metadata is missing"
        elif raw_path.exists() and metadata_path.exists():
            try:
                verified = verify_snapshot(raw_path, metadata_path)
            except (ValueError, FileNotFoundError) as exc:
                status = "invalid"
                message = str(exc)
            else:
                mismatches: list[str] = []
                if verified.url is not None and verified.url != query.url:
                    mismatches.append("url")
                if verified.query_id is not None and verified.query_id != query.query_id:
                    mismatches.append("query_id")
                if (
                    query.dataset is not None
                    and verified.dataset is not None
                    and verified.dataset != query.dataset
                ):
                    mismatches.append("dataset")
                if (
                    query.flow is not None
                    and verified.flow is not None
                    and verified.flow != query.flow
                ):
                    mismatches.append("flow")
                if (
                    query.measure is not None
                    and verified.measure is not None
                    and verified.measure != query.measure
                ):
                    mismatches.append("measure")
                if mismatches:
                    status = "invalid"
                    message = "snapshot metadata does not match manifest: " + ", ".join(mismatches)
                else:
                    status = "verified"
                    digest = verified.sha256
                    byte_count = verified.bytes
                    message = ""
        records.append(
            {
                "query_id": query.query_id,
                "source": query.source,
                "purpose": query.purpose,
                "expected_raw_path": query.expected_raw_path,
                "status": status,
                "sha256": digest,
                "bytes": byte_count,
                "message": message,
            }
        )
    return (
        pd.DataFrame.from_records(records)
        .sort_values(["source", "query_id"])
        .reset_index(drop=True)
    )


def source_queries_from_manifest(payload: dict[str, object]) -> tuple[SourceQuery, ...]:
    """Decode the query list emitted by ``export-source-queries``."""
    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list):
        raise ValueError("Source-query manifest must contain a `queries` list.")
    queries: list[SourceQuery] = []
    for item in raw_queries:
        if not isinstance(item, dict):
            raise ValueError("Each source-query manifest entry must be an object.")
        queries.append(
            SourceQuery(
                query_id=str(item["query_id"]),
                source=str(item["source"]),
                purpose=str(item["purpose"]),
                url=str(item["url"]),
                expected_raw_path=str(item["expected_raw_path"]),
                dataset=str(item["dataset"]) if item.get("dataset") is not None else None,
                flow=str(item["flow"]) if item.get("flow") is not None else None,
                measure=str(item["measure"]) if item.get("measure") is not None else None,
            )
        )
    return tuple(queries)
