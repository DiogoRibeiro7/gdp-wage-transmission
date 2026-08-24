from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from tools.integrity import (
    manifest_lines,
    parse_manifest,
    sha256_file,
    verify_release_archive,
)

# sha256 of an empty input, used as a known-answer check.
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha256_file_matches_known_answer(tmp_path: Path) -> None:
    target = tmp_path / "empty.txt"
    target.write_bytes(b"")
    assert sha256_file(target) == EMPTY_SHA256


def test_manifest_lines_are_sha256sum_compatible_and_sorted() -> None:
    digests = {"b.txt": "b" * 64, "a.txt": "a" * 64}
    rendered = manifest_lines(digests)
    assert rendered == f"{'a' * 64}  a.txt\n{'b' * 64}  b.txt\n"
    assert parse_manifest(rendered) == digests


def test_parse_manifest_rejects_malformed_lines() -> None:
    with pytest.raises(ValueError, match="Malformed manifest line"):
        parse_manifest("deadbeef nospacer.txt\n")


def _init_repo(root: Path) -> None:
    """Create a deterministic throwaway git repository."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for key, value in (
        ("user.email", "t@example.com"),
        ("user.name", "T"),
        ("core.autocrlf", "false"),
        ("commit.gpgsign", "false"),
    ):
        subprocess.run(["git", "config", key, value], cwd=root, check=True)


def _commit_all(root: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "snapshot", "--no-verify"], cwd=root, check=True)


def test_archive_verification_passes_for_a_consistent_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init_repo(tmp_path)
    tracked = tmp_path / "a.txt"
    tracked.write_bytes(b"content\n")
    manifest = tmp_path / "RELEASE_MANIFEST.sha256"
    manifest.write_text(manifest_lines({"a.txt": sha256_file(tracked)}), encoding="utf-8")
    _commit_all(tmp_path)

    assert verify_release_archive("HEAD") == 0


def test_archive_verification_catches_content_git_exports_differently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest that verifies against the working tree can still fail for a downloader."""
    monkeypatch.chdir(tmp_path)
    _init_repo(tmp_path)
    tracked = tmp_path / "a.txt"
    tracked.write_bytes(b"content\n")
    manifest = tmp_path / "RELEASE_MANIFEST.sha256"
    manifest.write_text(manifest_lines({"a.txt": sha256_file(tracked)}), encoding="utf-8")
    _commit_all(tmp_path)

    # The working tree keeps the digest the manifest recorded, but the committed
    # bytes differ -- exactly the drift that reached the first v0.6.0 archive.
    tracked.write_bytes(b"tampered\n")
    _commit_all(tmp_path)
    tracked.write_bytes(b"content\n")

    assert verify_release_archive("HEAD") == 1
