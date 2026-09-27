"""File failures carry source paths without changing snapshot integrity checks."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from dataexcept import DataLoadingError, FileReadError, FileWriteError

from wage_transmission.data.common import write_snapshot
from wage_transmission.data.offline import _read_verified_csv, _read_verified_json
from wage_transmission.data.snapshots import verify_snapshot


def test_raw_snapshot_write_failure_keeps_path_and_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_path = tmp_path / "raw.csv"
    failure = PermissionError("cannot write raw payload")

    def fail_write(_path: Path, _content: bytes) -> None:
        raise failure

    monkeypatch.setattr(Path, "write_bytes", fail_write)
    with pytest.raises(FileWriteError) as caught:
        write_snapshot(b"source", raw_path, {"source": "OECD"})

    assert caught.value.path == str(raw_path)
    assert caught.value.original is failure
    assert caught.value.__cause__ is failure


def test_metadata_write_failure_reports_metadata_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_path = tmp_path / "raw.csv"
    metadata_path = raw_path.with_suffix(".csv.metadata.json")
    failure = PermissionError("cannot write metadata")

    def fail_write(_path: Path, _content: str, *, encoding: str, newline: str) -> None:
        raise failure

    monkeypatch.setattr(Path, "write_text", fail_write)
    with pytest.raises(FileWriteError) as caught:
        write_snapshot(b"source", raw_path, {"source": "OECD"})

    assert caught.value.path == str(metadata_path)
    assert caught.value.original is failure
    assert caught.value.__cause__ is failure


def test_malformed_metadata_is_data_loading_error(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.csv"
    _, metadata_path = write_snapshot(b"source", raw_path, {"source": "OECD"})
    metadata_path.write_text("{broken JSON}", encoding="utf-8")

    with pytest.raises(DataLoadingError) as caught:
        verify_snapshot(raw_path)

    assert caught.value.source == str(metadata_path)
    assert isinstance(caught.value.original, json.JSONDecodeError)
    assert caught.value.__cause__ is caught.value.original


def test_missing_offline_csv_reports_file_read_error(tmp_path: Path) -> None:
    raw_path = tmp_path / "missing.csv"

    with pytest.raises(FileReadError) as caught:
        _read_verified_csv(raw_path, require_metadata=False)

    assert caught.value.path == str(raw_path)
    assert isinstance(caught.value.original, FileNotFoundError)
    assert caught.value.__cause__ is caught.value.original


def test_malformed_offline_csv_reports_data_loading_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_path = tmp_path / "malformed.csv"
    failure = pd.errors.ParserError("invalid CSV rows")

    def fail_read(_path: Path, *, low_memory: bool) -> None:
        raise failure

    monkeypatch.setattr(pd, "read_csv", fail_read)
    with pytest.raises(DataLoadingError) as caught:
        _read_verified_csv(raw_path, require_metadata=False)

    assert caught.value.source == str(raw_path)
    assert caught.value.original is failure
    assert caught.value.__cause__ is failure


def test_malformed_offline_json_reports_data_loading_error(tmp_path: Path) -> None:
    raw_path = tmp_path / "malformed.json"
    raw_path.write_text("{broken JSON}", encoding="utf-8")

    with pytest.raises(DataLoadingError) as caught:
        _read_verified_json(raw_path, require_metadata=False)

    assert caught.value.source == str(raw_path)
    assert isinstance(caught.value.original, json.JSONDecodeError)
    assert caught.value.__cause__ is caught.value.original


def test_snapshot_vintage_guard_stays_file_exists_error(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.csv"
    write_snapshot(b"first vintage", raw_path, {"source": "OECD"})

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_snapshot(b"revised vintage", raw_path, {"source": "OECD"})
