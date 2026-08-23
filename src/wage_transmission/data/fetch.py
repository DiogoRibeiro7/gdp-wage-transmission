"""Network retrieval for deterministic publication source freezes.

The analytical container used to build releases may be offline. This module therefore keeps
network retrieval separate from canonicalisation: an internet-enabled runner fetches the exact
URLs from a source-query manifest, freezes the response bytes unchanged, and records provenance.
Downstream builders consume only verified local snapshots.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Callable

import httpx
import pandas as pd

from wage_transmission.data.common import sha256_bytes, write_snapshot
from wage_transmission.data.snapshots import metadata_path_for, verify_snapshot
from wage_transmission.data.source_queries import SourceQuery


@dataclass(frozen=True)
class FetchPolicy:
    """HTTP behaviour for one source-freeze run."""

    timeout_seconds: float = 60.0
    retries: int = 3
    backoff_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if self.retries < 0:
            raise ValueError("retries must be non-negative.")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be non-negative.")


@dataclass(frozen=True)
class FetchResult:
    """Outcome of fetching or reusing one manifest query."""

    query_id: str
    source: str
    status: str
    attempts: int
    raw_path: str
    sha256: str = ""
    bytes: int = 0
    message: str = ""

    def to_dict(self) -> dict[str, str | int]:
        """Return a tabular representation of the result."""
        return {
            "query_id": self.query_id,
            "source": self.source,
            "status": self.status,
            "attempts": self.attempts,
            "raw_path": self.raw_path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "message": self.message,
        }


def _validate_payload_shape(query: SourceQuery, content: bytes) -> None:
    """Reject obvious transport/error pages before immutable storage.

    This is intentionally a *transport* contract only. Detailed economic-concept validation stays
    in the offline OECD/Eurostat builders, where dimensions and measure codes are checked.
    """
    if not content:
        raise ValueError(f"Empty response for {query.query_id}.")

    if query.source == "OECD":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"OECD response is not UTF-8 CSV for {query.query_id}.") from exc
        reader = csv.reader(StringIO(text))
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"OECD response has no CSV header for {query.query_id}.") from exc
        required = {"TIME_PERIOD", "OBS_VALUE"}
        if not required.issubset(set(header)):
            raise ValueError(
                f"OECD response for {query.query_id} is not the expected labelled SDMX CSV; "
                f"missing columns {sorted(required.difference(header))}."
            )
        return

    if query.source == "Eurostat":
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Eurostat response is not JSON for {query.query_id}.") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Eurostat response is not a JSON object for {query.query_id}.")
        required_keys = {"id", "size", "dimension", "value"}
        missing = required_keys.difference(payload)
        if missing:
            raise ValueError(
                f"Eurostat response for {query.query_id} is not JSON-stat data; "
                f"missing keys {sorted(missing)}."
            )
        return

    raise ValueError(f"Unsupported source {query.source!r} for query {query.query_id}.")


def _is_transient_status(status_code: int) -> bool:
    """Return whether an HTTP response is reasonable to retry."""
    return status_code == 429 or 500 <= status_code <= 599


def _existing_verified(query: SourceQuery) -> FetchResult | None:
    """Return a reuse result when the exact expected snapshot is already verified."""
    raw_path = Path(query.expected_raw_path)
    metadata_path = metadata_path_for(raw_path)
    if not raw_path.exists() or not metadata_path.exists():
        return None
    verified = verify_snapshot(raw_path, metadata_path)
    if verified.url is not None and verified.url != query.url:
        raise ValueError(
            f"Existing snapshot URL mismatch for {query.query_id}: "
            f"metadata has {verified.url!r}, manifest has {query.url!r}."
        )
    if query.flow is not None and verified.flow is not None and verified.flow != query.flow:
        raise ValueError(
            f"Existing snapshot flow mismatch for {query.query_id}: "
            f"metadata has {verified.flow!r}, manifest has {query.flow!r}."
        )
    if query.dataset is not None and verified.dataset is not None and verified.dataset != query.dataset:
        raise ValueError(
            f"Existing snapshot dataset mismatch for {query.query_id}: "
            f"metadata has {verified.dataset!r}, manifest has {query.dataset!r}."
        )
    if query.measure is not None and verified.measure is not None and verified.measure != query.measure:
        raise ValueError(
            f"Existing snapshot measure mismatch for {query.query_id}: "
            f"metadata has {verified.measure!r}, manifest has {query.measure!r}."
        )
    return FetchResult(
        query_id=query.query_id,
        source=query.source,
        status="reused_verified",
        attempts=0,
        raw_path=str(raw_path),
        sha256=verified.sha256,
        bytes=verified.bytes,
    )


def fetch_source_query(
    query: SourceQuery,
    *,
    client: httpx.Client,
    policy: FetchPolicy,
    manifest_path: Path | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """Fetch and freeze one source query, retrying only transient failures."""
    try:
        reused = _existing_verified(query)
    except (ValueError, FileNotFoundError) as exc:
        return FetchResult(
            query_id=query.query_id,
            source=query.source,
            status="failed",
            attempts=0,
            raw_path=query.expected_raw_path,
            message=str(exc),
        )
    if reused is not None:
        return reused

    attempts = 0
    last_error = ""
    max_attempts = policy.retries + 1
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        try:
            response = client.get(
                query.url,
                timeout=policy.timeout_seconds,
                headers={"Accept-Encoding": "identity"},
            )
            if _is_transient_status(response.status_code) and attempt < max_attempts:
                last_error = f"HTTP {response.status_code}"
                sleeper(policy.backoff_seconds * (2 ** (attempt - 1)))
                continue
            response.raise_for_status()
            content = response.content
            _validate_payload_shape(query, content)
            metadata: dict[str, object] = {
                "source": query.source,
                "url": query.url,
                "query_id": query.query_id,
                "purpose": query.purpose,
                "dataset": query.dataset,
                "flow": query.flow,
                "measure": query.measure,
                "http_status": response.status_code,
                "final_url": str(response.url),
                "content_type": response.headers.get("content-type"),
                "content_encoding": response.headers.get("content-encoding"),
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
            }
            if manifest_path is not None:
                metadata["query_manifest"] = str(manifest_path)
                metadata["query_manifest_sha256"] = sha256_bytes(manifest_path.read_bytes())
            raw_path, metadata_path = write_snapshot(
                content,
                Path(query.expected_raw_path),
                metadata,
                retrieval_method="http",
            )
            verified = verify_snapshot(raw_path, metadata_path)
            return FetchResult(
                query_id=query.query_id,
                source=query.source,
                status="downloaded",
                attempts=attempts,
                raw_path=str(raw_path),
                sha256=verified.sha256,
                bytes=verified.bytes,
            )
        except (httpx.HTTPError, ValueError, FileExistsError) as exc:
            last_error = str(exc)
            retryable = isinstance(exc, httpx.TransportError)
            if isinstance(exc, httpx.HTTPStatusError):
                retryable = _is_transient_status(exc.response.status_code)
            if retryable and attempt < max_attempts:
                sleeper(policy.backoff_seconds * (2 ** (attempt - 1)))
                continue
            break

    return FetchResult(
        query_id=query.query_id,
        source=query.source,
        status="failed",
        attempts=attempts,
        raw_path=query.expected_raw_path,
        message=last_error or "unknown fetch failure",
    )


def fetch_source_freeze(
    queries: tuple[SourceQuery, ...],
    *,
    policy: FetchPolicy | None = None,
    manifest_path: Path | None = None,
    client: httpx.Client | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> pd.DataFrame:
    """Fetch all source-manifest queries and return a deterministic status table."""
    if not queries:
        raise ValueError("At least one source query is required.")
    resolved_policy = policy or FetchPolicy()
    owns_client = client is None
    resolved_client = client or httpx.Client(follow_redirects=True)
    try:
        results = [
            fetch_source_query(
                query,
                client=resolved_client,
                policy=resolved_policy,
                manifest_path=manifest_path,
                sleeper=sleeper,
            )
            for query in queries
        ]
    finally:
        if owns_client:
            resolved_client.close()
    return (
        pd.DataFrame.from_records([result.to_dict() for result in results])
        .sort_values(["source", "query_id"])
        .reset_index(drop=True)
    )
