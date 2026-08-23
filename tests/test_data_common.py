from __future__ import annotations

import json
from pathlib import Path

import pytest

from wage_transmission.data.common import PROVENANCE_SCHEMA_VERSION, sha256_bytes, write_snapshot


def test_snapshot_is_idempotent_for_identical_bytes(tmp_path: Path) -> None:
    payload = b"official-source-payload"
    destination = tmp_path / "raw.json"

    raw_path, metadata_path = write_snapshot(
        payload,
        destination,
        {"source": "TEST", "url": "https://example.invalid/source"},
    )
    first_metadata = metadata_path.read_text(encoding="utf-8")

    second_raw_path, second_metadata_path = write_snapshot(
        payload,
        destination,
        {"source": "TEST", "url": "https://example.invalid/source"},
    )

    assert raw_path == second_raw_path
    assert metadata_path == second_metadata_path
    assert destination.read_bytes() == payload
    assert metadata_path.read_text(encoding="utf-8") == first_metadata
    metadata = json.loads(first_metadata)
    assert metadata["provenance_schema_version"] == PROVENANCE_SCHEMA_VERSION
    assert metadata["sha256"] == sha256_bytes(payload)


def test_snapshot_refuses_to_overwrite_a_different_source_vintage(tmp_path: Path) -> None:
    destination = tmp_path / "raw.json"
    write_snapshot(b"vintage-1", destination, {"source": "TEST"})

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_snapshot(b"vintage-2", destination, {"source": "TEST"})

    assert destination.read_bytes() == b"vintage-1"
