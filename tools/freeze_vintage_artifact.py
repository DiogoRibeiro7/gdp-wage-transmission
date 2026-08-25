"""Assemble the self-contained reproducibility bundle for one source vintage.

`data/raw/`, `data/processed/` and `results/` are all outside version control, so a released
tag carries the code that produced a result but not the bytes it consumed or produced. This
script copies both into one directory under `results/vintages/<vintage>-artifact/` and writes a
`sha256sum`-format manifest over everything in it.

The previous vintage's bundle was assembled by hand, which is why this exists: a bundle nobody
can regenerate is a bundle nobody can check.

Usage::

    poetry run python tools/freeze_vintage_artifact.py --vintage 2026-08-25
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_tree(source: Path, destination: Path) -> int:
    """Copy a directory verbatim, returning the number of files copied."""
    if not source.exists():
        return 0
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return sum(1 for path in destination.rglob("*") if path.is_file())


def build_artifact(*, vintage: str, root: Path) -> Path:
    """Copy the vintage's inputs and outputs into one directory and hash the result."""
    artifact = root / "results" / "vintages" / f"{vintage}-artifact"
    if artifact.exists():
        raise FileExistsError(
            f"{artifact} already exists. A frozen bundle is not rewritten in place; "
            "remove it deliberately if it must be rebuilt."
        )
    artifact.mkdir(parents=True)

    copied = 0
    copied += copy_tree(root / "data" / "raw" / vintage, artifact / "data" / "raw" / vintage)
    copied += copy_tree(
        root / "data" / "processed" / vintage, artifact / "data" / "processed" / vintage
    )
    copied += copy_tree(
        root / "results" / "vintages" / vintage,
        artifact / "results" / "vintages" / vintage,
    )
    registry = root / "data" / "raw" / "SNAPSHOT_REGISTRY.csv"
    if registry.is_file():
        shutil.copy2(registry, artifact / "data" / "raw" / "SNAPSHOT_REGISTRY.csv")
    manifests = artifact / "data" / "query_manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    for path in sorted((root / "data" / "query_manifests").glob(f"{vintage}.*")):
        shutil.copy2(path, manifests / path.name)

    checksums = artifact / f"publication-freeze-{vintage}.sha256"
    entries = {
        path.relative_to(artifact).as_posix(): sha256_file(path)
        for path in sorted(artifact.rglob("*"))
        if path.is_file() and path != checksums
    }
    # LF explicitly: this manifest is the reference copy and must not depend on the platform.
    checksums.write_text(
        "".join(f"{entries[name]}  {name}\n" for name in sorted(entries)),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Froze {len(entries)} files into {artifact} ({copied} copied).")
    return artifact


def verify_artifact(artifact: Path) -> int:
    """Re-hash a frozen bundle against the manifest it carries."""
    candidates = sorted(artifact.glob("publication-freeze-*.sha256"))
    if len(candidates) != 1:
        print(f"Expected exactly one checksum file in {artifact}; found {len(candidates)}.")
        return 1
    checksums = candidates[0]
    recorded: dict[str, str] = {}
    for line in checksums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        recorded[name] = digest

    missing = [name for name in sorted(recorded) if not (artifact / name).is_file()]
    mismatched = [
        name
        for name in sorted(recorded)
        if (artifact / name).is_file() and sha256_file(artifact / name) != recorded[name]
    ]
    extra = sorted(
        path.relative_to(artifact).as_posix()
        for path in artifact.rglob("*")
        if path.is_file()
        and path != checksums
        and path.relative_to(artifact).as_posix() not in recorded
    )
    for name in missing:
        print(f"missing:  {name}")
    for name in mismatched:
        print(f"MISMATCH: {name}")
    for name in extra:
        print(f"UNRECORDED: {name}")
    if mismatched or extra:
        return 1
    print(f"{len(recorded) - len(missing)} of {len(recorded)} files match the frozen digests.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vintage", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--verify", action="store_true", help="check an existing bundle instead")
    args = parser.parse_args(argv)

    artifact = args.root / "results" / "vintages" / f"{args.vintage}-artifact"
    if args.verify:
        return verify_artifact(artifact)
    build_artifact(vintage=args.vintage, root=args.root)
    return verify_artifact(artifact)


if __name__ == "__main__":
    raise SystemExit(main())
