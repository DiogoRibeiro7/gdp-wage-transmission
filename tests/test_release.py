from __future__ import annotations

import json
import platform
from pathlib import Path

import pytest

from wage_transmission.release import (
    MANIFEST_SCHEMA_VERSION,
    NUMERICAL_DEPENDENCIES,
    build_release_manifest,
    write_release_manifest,
)
from wage_transmission.version import __version__

CONFIGS = {
    "model_config": Path("config/models.yml"),
    "project_config": Path("config/project.yml"),
    "publication_config": Path("config/publication.yml"),
}


def test_manifest_records_the_environment_that_produced_the_numbers() -> None:
    manifest = build_release_manifest(vintage="2026-08-22", **CONFIGS)

    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["package_version"] == __version__
    assert manifest["python_version"] == platform.python_version()
    assert manifest["causal_claims_authorized"] is False
    for name in NUMERICAL_DEPENDENCIES:
        assert manifest["numerical_dependencies"][name] != "not-installed"


def test_manifest_carries_configuration_content_and_digests() -> None:
    manifest = build_release_manifest(vintage="2026-08-22", **CONFIGS)
    models = manifest["configuration"]["models"]

    assert models["path"] == "config/models.yml"
    assert len(models["sha256"]) == 64
    # The content is embedded, so the manifest stays readable without the repository.
    assert "distributed_lag" in models["content"]


def test_manifest_is_reproducible_from_the_same_inputs() -> None:
    """No wall-clock timestamp: two builds of one vintage must be byte-identical."""
    first = build_release_manifest(vintage="2026-08-22", **CONFIGS)
    second = build_release_manifest(vintage="2026-08-22", **CONFIGS)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_manifest_digests_named_outputs(tmp_path: Path) -> None:
    produced = tmp_path / "core_estimates.csv"
    produced.write_text("driver,estimate\nproductivity,0.5\n", encoding="utf-8")

    manifest = build_release_manifest(
        vintage="2026-08-22", outputs={"core_estimates": produced}, **CONFIGS
    )

    entry = manifest["outputs"]["core_estimates"]
    assert len(entry["sha256"]) == 64
    assert entry["bytes"] == produced.stat().st_size


def test_manifest_fails_on_a_missing_output(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_release_manifest(
            vintage="2026-08-22", outputs={"absent": tmp_path / "nope.csv"}, **CONFIGS
        )


def test_manifest_requires_a_vintage() -> None:
    with pytest.raises(ValueError, match="non-empty source vintage"):
        build_release_manifest(vintage="   ", **CONFIGS)


def test_manifest_writes_lf_only_json(tmp_path: Path) -> None:
    manifest = build_release_manifest(vintage="2026-08-22", **CONFIGS)
    output = write_release_manifest(manifest, tmp_path / "release_manifest.json")

    assert b"\r\n" not in output.read_bytes()
    assert json.loads(output.read_text(encoding="utf-8"))["vintage"] == "2026-08-22"
