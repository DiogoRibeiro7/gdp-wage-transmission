"""Common data-access helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROVENANCE_SCHEMA_VERSION = 3


def sha256_bytes(content: bytes) -> str:
    """Return a SHA-256 digest for downloaded content."""
    return hashlib.sha256(content).hexdigest()


def write_snapshot(
    content: bytes,
    destination: Path,
    metadata: dict[str, Any],
    *,
    retrieval_method: str = "http",
) -> tuple[Path, Path]:
    """Persist an immutable source response and an adjacent provenance record.

    The snapshot writer never rewrites the payload after hashing it. Metadata records the exact
    response digest, retrieval timestamp, byte count and a small provenance schema version. The
    surrounding downloader is responsible for recording the source-specific query definition.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    meta_path = destination.with_suffix(destination.suffix + ".metadata.json")
    digest = sha256_bytes(content)

    if destination.exists():
        existing = destination.read_bytes()
        existing_digest = sha256_bytes(existing)
        if existing_digest != digest:
            raise FileExistsError(
                "Refusing to overwrite an existing raw snapshot with different bytes: "
                f"{destination}. Use a versioned raw directory for a new source vintage."
            )
        if meta_path.exists():
            existing_metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            recorded_digest = existing_metadata.get("sha256")
            if recorded_digest is not None and recorded_digest != digest:
                raise ValueError(
                    f"Existing provenance digest does not match raw snapshot: {meta_path}"
                )
            return destination, meta_path
    else:
        destination.write_bytes(content)

    method = retrieval_method.strip()
    if not method:
        raise ValueError("retrieval_method must be non-empty.")
    enriched = {
        **metadata,
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "retrieval_method": method,
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "sha256": digest,
        "bytes": len(content),
    }
    meta_path.write_text(
        json.dumps(enriched, indent=2, sort_keys=True), encoding="utf-8", newline="\n"
    )
    return destination, meta_path


def canonical_observations(
    frame: pd.DataFrame,
    *,
    value_name: str,
    source: str,
) -> pd.DataFrame:
    """Reduce a labelled SDMX-style frame to canonical country-year observations."""
    required = {"REF_AREA", "TIME_PERIOD", "OBS_VALUE"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Source frame is missing SDMX columns: {sorted(missing)}")

    out = frame.loc[:, ["REF_AREA", "TIME_PERIOD", "OBS_VALUE"]].copy()
    out.columns = ["country", "year", value_name]
    out["year"] = pd.to_numeric(out["year"], errors="raise").astype(int)
    out[value_name] = pd.to_numeric(out[value_name], errors="coerce")
    out = out.dropna(subset=[value_name])
    if out.duplicated(["country", "year"]).any():
        duplicates = out.loc[out.duplicated(["country", "year"], keep=False), ["country", "year"]]
        preview = duplicates.drop_duplicates().head(10).to_dict(orient="records")
        raise ValueError(
            "Source selection is not unique by country-year. "
            f"Refine unit/price-base filters. Example duplicates: {preview}"
        )
    out["source"] = source
    return out.sort_values(["country", "year"]).reset_index(drop=True)
