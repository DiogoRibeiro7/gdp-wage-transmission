"""Recompute and verify the repository's integrity artefacts.

Two artefacts pin repository state outside the analysis package:

``papers/wage_distribution_breaks/analysis_lock.json``
    The Paper 2 post-hoc analysis lock, binding the protocol, the wage
    distribution input and the estimation script.

``RELEASE_MANIFEST.sha256``
    A ``sha256sum``-compatible manifest of the release tree.

Both previously existed without a generator, so their digests could not be
recomputed by a reader. This module makes them reproducible.

The combined digest is defined explicitly: SHA-256 over the UTF-8 encoding of
``"{sha256}  {path}\n"`` lines, one per file, sorted by path. That is the same
line format ``sha256sum`` writes, so the combined digest of a lock equals the
digest of the equivalent manifest fragment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

ANALYSIS_LOCK = Path("papers/wage_distribution_breaks/analysis_lock.json")
RELEASE_MANIFEST = Path("RELEASE_MANIFEST.sha256")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_lines(digests: Mapping[str, str]) -> str:
    """Render digests in sha256sum line format, sorted by path."""
    return "".join(f"{digests[path]}  {path}\n" for path in sorted(digests))


def combined_sha256(digests: Mapping[str, str]) -> str:
    """Return the digest binding a set of per-file digests together."""
    return hashlib.sha256(manifest_lines(digests).encode("utf-8")).hexdigest()


def parse_manifest(text: str) -> dict[str, str]:
    """Parse a sha256sum-format manifest into a path -> digest mapping."""
    digests: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        digest, _, path = line.partition("  ")
        if not path:
            raise ValueError(f"Malformed manifest line: {line!r}")
        digests[path] = digest
    return digests


def tracked_files() -> list[str]:
    """Return every path tracked by git, as forward-slash relative paths."""
    result = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    return [line for line in result.stdout.splitlines() if line]


def manifest_scope(existing: Mapping[str, str]) -> list[str]:
    """Resolve which paths the release manifest covers.

    The scope is every git-tracked file, plus any path already listed in the
    manifest that still exists. The second term preserves coverage of working
    artefacts such as ``results/`` that are deliberately not tracked, without
    silently dropping them on regeneration.
    """
    scope = {path for path in tracked_files() if Path(path).is_file()}
    scope.update(path for path in existing if Path(path).is_file())
    return sorted(scope)


def report(missing: Iterable[str], mismatched: Iterable[str]) -> int:
    """Print a verification report and return a process exit code."""
    missing = list(missing)
    mismatched = list(mismatched)
    for path in missing:
        print(f"missing:  {path}")
    for path in mismatched:
        print(f"MISMATCH: {path}")
    if mismatched:
        print(f"\n{len(mismatched)} file(s) do not match the recorded digest.")
        return 1
    if missing:
        print(
            f"\nAll present files match. {len(missing)} listed file(s) absent from this checkout."
        )
        return 0
    print("All files match the recorded digests.")
    return 0


def write_analysis_lock(lock_path: Path) -> dict[str, object]:
    """Recompute the per-file and combined digests of the Paper 2 lock."""
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    files = {path: sha256_file(Path(path)) for path in sorted(payload["files"])}
    payload["files"] = files
    payload["combined_sha256"] = combined_sha256(files)
    lock_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return payload


def verify_analysis_lock(lock_path: Path) -> int:
    """Verify the Paper 2 lock against the current working tree."""
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    recorded: dict[str, str] = payload["files"]
    missing = [path for path in sorted(recorded) if not Path(path).is_file()]
    mismatched = [
        path
        for path in sorted(recorded)
        if Path(path).is_file() and sha256_file(Path(path)) != recorded[path]
    ]
    expected_combined = combined_sha256(recorded)
    status = report(missing, mismatched)
    if payload.get("combined_sha256") != expected_combined:
        print(
            "MISMATCH: combined_sha256 does not bind the recorded per-file digests\n"
            f"  recorded: {payload.get('combined_sha256')}\n"
            f"  expected: {expected_combined}"
        )
        return 1
    return status


def write_release_manifest(manifest_path: Path) -> int:
    """Regenerate the release manifest over its resolved scope."""
    existing = (
        parse_manifest(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    )
    # A manifest cannot record its own digest: writing it would invalidate the entry.
    own = manifest_path.as_posix()
    digests = {path: sha256_file(Path(path)) for path in manifest_scope(existing) if path != own}
    manifest_path.write_text(manifest_lines(digests), encoding="utf-8", newline="\n")
    print(f"Wrote {len(digests)} entries to {manifest_path}.")
    return 0


def verify_release_manifest(manifest_path: Path) -> int:
    """Verify the release manifest against the current working tree."""
    recorded = parse_manifest(manifest_path.read_text(encoding="utf-8"))
    missing = [path for path in sorted(recorded) if not Path(path).is_file()]
    mismatched = [
        path
        for path in sorted(recorded)
        if Path(path).is_file() and sha256_file(Path(path)) != recorded[path]
    ]
    return report(missing, mismatched)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    lock = sub.add_parser("analysis-lock", help="Paper 2 post-hoc analysis lock")
    lock.add_argument("action", choices=["write", "verify"])
    lock.add_argument("--path", type=Path, default=ANALYSIS_LOCK)

    manifest = sub.add_parser("release-manifest", help="repository release manifest")
    manifest.add_argument("action", choices=["write", "verify"])
    manifest.add_argument("--path", type=Path, default=RELEASE_MANIFEST)

    args = parser.parse_args(argv)
    if args.command == "analysis-lock":
        if args.action == "write":
            payload = write_analysis_lock(args.path)
            print(f"combined_sha256: {payload['combined_sha256']}")
            return 0
        return verify_analysis_lock(args.path)
    if args.action == "write":
        return write_release_manifest(args.path)
    return verify_release_manifest(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
