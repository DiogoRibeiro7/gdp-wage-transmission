"""Verification, import, and registry utilities for immutable raw source snapshots."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from wage_transmission.data.common import sha256_bytes, write_snapshot


@dataclass(frozen=True)
class SnapshotVerification:
    """Verified raw snapshot and its provenance metadata."""

    raw_path: Path
    metadata_path: Path
    source: str
    sha256: str
    bytes: int
    retrieval_method: str
    retrieved_at_utc: str
    url: str | None = None
    dataset: str | None = None
    flow: str | None = None
    measure: str | None = None
    query_id: str | None = None
    purpose: str | None = None


def metadata_path_for(raw_path: Path) -> Path:
    """Return the adjacent metadata path used by :func:`write_snapshot`."""
    return raw_path.with_suffix(raw_path.suffix + ".metadata.json")


def _load_metadata(metadata_path: Path) -> dict[str, Any]:
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Snapshot metadata must be a JSON object: {metadata_path}")
    return payload


def verify_snapshot(raw_path: Path, metadata_path: Path | None = None) -> SnapshotVerification:
    """Re-hash one raw snapshot and validate its adjacent provenance record."""
    if not raw_path.is_file():
        raise FileNotFoundError(raw_path)
    resolved_metadata = metadata_path_for(raw_path) if metadata_path is None else metadata_path
    if not resolved_metadata.is_file():
        raise FileNotFoundError(resolved_metadata)

    content = raw_path.read_bytes()
    metadata = _load_metadata(resolved_metadata)
    digest = sha256_bytes(content)
    recorded_digest = str(metadata.get("sha256", ""))
    if digest != recorded_digest:
        raise ValueError(
            f"Snapshot SHA-256 mismatch for {raw_path}: computed {digest}, "
            f"metadata records {recorded_digest or '<missing>'}."
        )
    recorded_bytes = metadata.get("bytes")
    if recorded_bytes is None or int(recorded_bytes) != len(content):
        raise ValueError(
            f"Snapshot byte-count mismatch for {raw_path}: computed {len(content)}, "
            f"metadata records {recorded_bytes!r}."
        )

    source = str(metadata.get("source", "")).strip()
    retrieval_method = str(metadata.get("retrieval_method", "")).strip()
    retrieved_at_utc = str(metadata.get("retrieved_at_utc", "")).strip()
    if not source:
        raise ValueError(f"Snapshot metadata has no source: {resolved_metadata}")
    if not retrieval_method:
        raise ValueError(f"Snapshot metadata has no retrieval_method: {resolved_metadata}")
    if not retrieved_at_utc:
        raise ValueError(f"Snapshot metadata has no retrieved_at_utc: {resolved_metadata}")

    return SnapshotVerification(
        raw_path=raw_path,
        metadata_path=resolved_metadata,
        source=source,
        sha256=digest,
        bytes=len(content),
        retrieval_method=retrieval_method,
        retrieved_at_utc=retrieved_at_utc,
        url=str(metadata["url"]) if metadata.get("url") is not None else None,
        dataset=str(metadata["dataset"]) if metadata.get("dataset") is not None else None,
        flow=str(metadata["flow"]) if metadata.get("flow") is not None else None,
        measure=str(metadata["measure"]) if metadata.get("measure") is not None else None,
        query_id=str(metadata["query_id"]) if metadata.get("query_id") is not None else None,
        purpose=str(metadata["purpose"]) if metadata.get("purpose") is not None else None,
    )


def import_external_snapshot(
    source_path: Path,
    destination: Path,
    *,
    metadata: dict[str, Any],
) -> tuple[Path, Path]:
    """Copy an externally downloaded official payload into the immutable raw store.

    The payload bytes are copied without decoding, parsing, newline conversion, or re-serialization.
    The metadata must identify the official source and query URL. This makes browser/curl downloads
    usable in a network-restricted analysis environment without pretending that the package itself
    performed the HTTP request.
    """
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    source = str(metadata.get("source", "")).strip()
    url = str(metadata.get("url", "")).strip()
    if not source:
        raise ValueError("External snapshot metadata must contain a non-empty `source`.")
    if not url.startswith(("https://", "http://")):
        raise ValueError("External snapshot metadata must contain the official HTTP(S) `url`.")

    enriched = {
        **metadata,
        "external_original_filename": source_path.name,
    }
    return write_snapshot(
        source_path.read_bytes(),
        destination,
        enriched,
        retrieval_method="external_import",
    )


def _raw_path_from_metadata(metadata_path: Path) -> Path:
    suffix = ".metadata.json"
    value = str(metadata_path)
    if not value.endswith(suffix):
        raise ValueError(f"Not a snapshot metadata filename: {metadata_path}")
    return Path(value[: -len(suffix)])


def scan_snapshots(raw_root: Path) -> tuple[SnapshotVerification, ...]:
    """Verify every adjacent snapshot metadata record below a raw-data root."""
    if not raw_root.exists():
        return ()
    verified: list[SnapshotVerification] = []
    for metadata_path in sorted(raw_root.rglob("*.metadata.json")):
        raw_path = _raw_path_from_metadata(metadata_path)
        verified.append(verify_snapshot(raw_path, metadata_path))
    return tuple(verified)


def _registry_rows(
    snapshots: Iterable[SnapshotVerification],
    *,
    root: Path,
) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for snapshot in snapshots:
        try:
            raw_display = snapshot.raw_path.relative_to(root).as_posix()
            metadata_display = snapshot.metadata_path.relative_to(root).as_posix()
        except ValueError:
            raw_display = snapshot.raw_path.as_posix()
            metadata_display = snapshot.metadata_path.as_posix()
        relative_parts: tuple[str, ...] = ()
        try:
            relative_parts = snapshot.raw_path.relative_to(root).parts
        except ValueError:
            pass
        rows.append(
            {
                "vintage": relative_parts[0] if len(relative_parts) > 1 else "",
                "source": snapshot.source,
                "dataset": snapshot.dataset or "",
                "flow": snapshot.flow or "",
                "measure": snapshot.measure or "",
                "query_id": snapshot.query_id or "",
                "purpose": snapshot.purpose or "",
                "retrieval_method": snapshot.retrieval_method,
                "retrieved_at_utc": snapshot.retrieved_at_utc,
                "sha256": snapshot.sha256,
                "bytes": snapshot.bytes,
                "raw_path": raw_display,
                "metadata_path": metadata_display,
                "url": snapshot.url or "",
            }
        )
    return rows


def write_snapshot_registry(raw_root: Path, output_path: Path) -> Path:
    """Verify raw snapshots and write a deterministic CSV registry."""
    snapshots = scan_snapshots(raw_root)
    rows = _registry_rows(snapshots, root=raw_root)
    fieldnames = [
        "vintage",
        "source",
        "dataset",
        "flow",
        "measure",
        "query_id",
        "purpose",
        "retrieval_method",
        "retrieved_at_utc",
        "sha256",
        "bytes",
        "raw_path",
        "metadata_path",
        "url",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def verification_to_dict(snapshot: SnapshotVerification) -> dict[str, Any]:
    """Return a JSON-serializable snapshot verification record."""
    payload = asdict(snapshot)
    payload["raw_path"] = str(snapshot.raw_path)
    payload["metadata_path"] = str(snapshot.metadata_path)
    return payload
