from __future__ import annotations

from pathlib import Path

from wage_transmission.data.source_queries import build_source_queries


def test_query_manifest_uses_explicit_constant_price_wage_code(tmp_path: Path) -> None:
    queries = build_source_queries(
        countries=["PRT", "ESP"],
        decomposition_countries=["PRT"],
        start_year=1995,
        end_year=2025,
        raw_root=tmp_path,
    )
    wage = next(query for query in queries if query.query_id == "oecd_average_wages")
    assert "..USD_PPP..Q.." in wage.url
    assert "startPeriod=1995" in wage.url
    assert "endPeriod=2025" in wage.url
    assert any(query.query_id == "oecd_gdpemp" for query in queries)
    employee_query = next(query for query in queries if query.query_id == "eurostat_employees_PRT")
    assert "sinceTimePeriod=1995" in employee_query.url
    assert "untilTimePeriod=2025" in employee_query.url


def test_source_freeze_audit_reports_verified_and_missing(tmp_path: Path) -> None:
    from wage_transmission.data.common import write_snapshot
    from wage_transmission.data.source_queries import SourceQuery, audit_source_freeze

    present = tmp_path / "present.csv"
    write_snapshot(
        b"a,b\n1,2\n",
        present,
        {"source": "OECD", "url": "https://example.test/present"},
    )
    queries = (
        SourceQuery(
            query_id="present",
            source="OECD",
            purpose="test",
            url="https://example.test/present",
            expected_raw_path=str(present),
        ),
        SourceQuery(
            query_id="missing",
            source="Eurostat",
            purpose="test",
            url="https://example.test/missing",
            expected_raw_path=str(tmp_path / "missing.json"),
        ),
    )
    audit = audit_source_freeze(queries)
    status = dict(zip(audit["query_id"], audit["status"], strict=True))
    assert status == {"missing": "missing", "present": "verified"}


def test_source_freeze_audit_rejects_manifest_metadata_mismatch(tmp_path: Path) -> None:
    from wage_transmission.data.common import write_snapshot
    from wage_transmission.data.source_queries import SourceQuery, audit_source_freeze

    raw = tmp_path / "payload.csv"
    write_snapshot(
        b"TIME_PERIOD,OBS_VALUE\n2024,1\n",
        raw,
        {
            "source": "OECD",
            "url": "https://example.test/wrong",
            "query_id": "wrong-id",
        },
    )
    query = SourceQuery(
        query_id="expected-id",
        source="OECD",
        purpose="test",
        url="https://example.test/right",
        expected_raw_path=str(raw),
    )
    audit = audit_source_freeze((query,))
    assert audit.loc[0, "status"] == "invalid"
    assert "url" in str(audit.loc[0, "message"])
    assert "query_id" in str(audit.loc[0, "message"])
