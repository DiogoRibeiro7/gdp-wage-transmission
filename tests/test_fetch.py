from __future__ import annotations

import json
from pathlib import Path

import httpx

from wage_transmission.data.fetch import FetchPolicy, fetch_source_freeze, fetch_source_query
from wage_transmission.data.source_queries import SourceQuery, audit_source_freeze


def _oecd_csv() -> bytes:
    return b"REF_AREA,TIME_PERIOD,OBS_VALUE,MEASURE\nPRT,2024,100.0,GDPEMP\n"


def _eurostat_json() -> bytes:
    payload = {
        "id": ["freq", "unit", "na_item", "geo", "time"],
        "size": [1, 1, 1, 1, 1],
        "dimension": {
            "freq": {"category": {"index": {"A": 0}}},
            "unit": {"category": {"index": {"CP_MEUR": 0}}},
            "na_item": {"category": {"index": {"B1GQ": 0}}},
            "geo": {"category": {"index": {"PT": 0}}},
            "time": {"category": {"index": {"2024": 0}}},
        },
        "value": {"0": 1.0},
    }
    return json.dumps(payload).encode()


def test_fetch_source_query_retries_transient_response_and_freezes_bytes(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, content=_oecd_csv(), request=request)

    query = SourceQuery(
        query_id="oecd_gdpemp",
        source="OECD",
        purpose="GDP per person employed",
        url="https://example.test/oecd.csv",
        expected_raw_path=str(tmp_path / "raw.csv"),
        flow="FLOW",
        measure="GDPEMP",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_source_query(
        query,
        client=client,
        policy=FetchPolicy(retries=2, backoff_seconds=0),
        sleeper=lambda _: None,
    )
    client.close()

    assert result.status == "downloaded"
    assert result.attempts == 2
    assert calls == 2
    assert Path(query.expected_raw_path).read_bytes() == _oecd_csv()
    audit = audit_source_freeze((query,))
    assert audit.loc[0, "status"] == "verified"


def test_fetch_source_freeze_reuses_verified_snapshot(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_eurostat_json(), request=request)

    query = SourceQuery(
        query_id="eurostat_nominal_gdp_PRT",
        source="Eurostat",
        purpose="nominal_gdp",
        url="https://example.test/eurostat.json",
        expected_raw_path=str(tmp_path / "raw.json"),
        dataset="nama_10_gdp",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    first = fetch_source_freeze(
        (query,),
        client=client,
        policy=FetchPolicy(retries=0),
        sleeper=lambda _: None,
    )
    second = fetch_source_freeze(
        (query,),
        client=client,
        policy=FetchPolicy(retries=0),
        sleeper=lambda _: None,
    )
    client.close()

    assert first.loc[0, "status"] == "downloaded"
    assert second.loc[0, "status"] == "reused_verified"
    assert calls == 1


def test_fetch_rejects_html_error_page_with_http_200(tmp_path: Path) -> None:
    query = SourceQuery(
        query_id="oecd_bad",
        source="OECD",
        purpose="test",
        url="https://example.test/bad",
        expected_raw_path=str(tmp_path / "bad.csv"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>error</html>", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_source_query(
        query,
        client=client,
        policy=FetchPolicy(retries=0),
        sleeper=lambda _: None,
    )
    client.close()

    assert result.status == "failed"
    assert not Path(query.expected_raw_path).exists()
    assert "missing columns" in result.message
