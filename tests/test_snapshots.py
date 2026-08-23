from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from wage_transmission.data.common import sha256_bytes, write_snapshot
from wage_transmission.data.snapshots import (
    import_external_snapshot,
    verify_snapshot,
    write_snapshot_registry,
)


def test_verify_snapshot_detects_tampering(tmp_path: Path) -> None:
    raw = tmp_path / "source.csv"
    write_snapshot(b"a,b\n1,2\n", raw, {"source": "TEST", "url": "https://example.test/data"})
    verified = verify_snapshot(raw)
    assert verified.sha256 == sha256_bytes(b"a,b\n1,2\n")

    raw.write_bytes(b"a,b\n1,3\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_snapshot(raw)


def test_external_import_preserves_bytes_and_registry(tmp_path: Path) -> None:
    source = tmp_path / "download.csv"
    payload = b"exact,bytes\n1,2\n"
    source.write_bytes(payload)
    raw_root = tmp_path / "raw"
    destination = raw_root / "2026-08-22" / "official.csv"

    raw_path, metadata_path = import_external_snapshot(
        source,
        destination,
        metadata={
            "source": "OECD",
            "url": "https://sdmx.oecd.org/public/rest/data/example",
            "flow": "TEST_FLOW",
        },
    )
    assert raw_path.read_bytes() == payload
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["retrieval_method"] == "external_import"

    registry = raw_root / "SNAPSHOT_REGISTRY.csv"
    write_snapshot_registry(raw_root, registry)
    table = pd.read_csv(registry)
    assert len(table) == 1
    assert table.loc[0, "sha256"] == sha256_bytes(payload)
    assert table.loc[0, "retrieval_method"] == "external_import"
