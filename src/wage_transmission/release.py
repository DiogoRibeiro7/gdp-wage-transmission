"""Release manifest binding a set of results to the environment that produced them.

A digest list proves that files did not change. It does not say what produced them, and two runs
of the same code on different numpy versions can differ in the last decimal places of an
estimate. This manifest records the rest of what a reader needs to reproduce a number: the
package version, the interpreter, the versions of the numerical libraries that actually do the
arithmetic, the model configuration in force, and the digest of every raw source snapshot the
run consumed.

The manifest carries no wall-clock timestamp. It is keyed by the source vintage instead, so
building it twice from the same inputs produces identical bytes and any difference is a real
difference rather than the clock moving.
"""

from __future__ import annotations

import platform
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import yaml

from wage_transmission.data.common import sha256_bytes
from wage_transmission.data.snapshots import scan_snapshots
from wage_transmission.version import __version__

MANIFEST_SCHEMA_VERSION = 1

# Libraries whose version can move an estimate, not merely an interface.
NUMERICAL_DEPENDENCIES = ("numpy", "pandas", "scipy", "statsmodels")


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in NUMERICAL_DEPENDENCIES:
        try:
            versions[name] = package_version(name)
        except PackageNotFoundError:  # pragma: no cover - only if an install is broken
            versions[name] = "not-installed"
    return versions


def _config_record(path: Path) -> dict[str, Any]:
    """Digest and parsed content of one configuration file."""
    if not path.is_file():
        raise FileNotFoundError(path)
    content = path.read_bytes()
    parsed = yaml.safe_load(content.decode("utf-8"))
    return {
        "path": path.as_posix(),
        "sha256": sha256_bytes(content),
        "content": parsed,
    }


def _raw_digests(raw_root: Path) -> dict[str, dict[str, Any]]:
    """Digest, size and provenance of every verified raw snapshot under ``raw_root``."""
    digests: dict[str, dict[str, Any]] = {}
    for snapshot in scan_snapshots(raw_root):
        key = snapshot.raw_path.relative_to(raw_root).as_posix()
        digests[key] = {
            "sha256": snapshot.sha256,
            "bytes": snapshot.bytes,
            "source": snapshot.source,
            "retrieved_at_utc": snapshot.retrieved_at_utc,
            "retrieval_method": snapshot.retrieval_method,
            "url": snapshot.url,
        }
    return dict(sorted(digests.items()))


def build_release_manifest(
    *,
    vintage: str,
    raw_root: Path | None = None,
    model_config: Path = Path("config/models.yml"),
    project_config: Path = Path("config/project.yml"),
    publication_config: Path = Path("config/publication.yml"),
    outputs: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Assemble the release manifest for one source vintage.

    ``outputs`` maps a label to a produced artefact; each is digested so that the manifest ties
    the environment, the configuration and the results together in one record.
    """
    if not vintage.strip():
        raise ValueError("A release manifest must be keyed by a non-empty source vintage.")

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "vintage": vintage.strip(),
        "package_version": __version__,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "numerical_dependencies": _dependency_versions(),
        "configuration": {
            "models": _config_record(model_config),
            "project": _config_record(project_config),
            "publication": _config_record(publication_config),
        },
        "raw_snapshots": _raw_digests(raw_root) if raw_root is not None else {},
        "outputs": {},
        "causal_claims_authorized": False,
    }

    if outputs:
        digested: dict[str, dict[str, Any]] = {}
        for label, path in sorted(outputs.items()):
            if not path.is_file():
                raise FileNotFoundError(path)
            content = path.read_bytes()
            digested[label] = {
                "path": path.as_posix(),
                "sha256": sha256_bytes(content),
                "bytes": len(content),
            }
        manifest["outputs"] = digested

    return manifest


def write_release_manifest(manifest: dict[str, Any], output: Path) -> Path:
    """Write the manifest as deterministic, diffable JSON."""
    from wage_transmission.reporting import write_json

    return write_json(manifest, output)
