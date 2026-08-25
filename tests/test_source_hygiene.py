"""Repository-wide guards against damage that reads as ordinary text.

A lost backslash in an authoring pipeline turns ``\\alpha`` into a bell character followed by
``lpha``. Editors and terminals render the bell as nothing at all, so the corruption survives
review, survives a diff read on screen, and only shows up in the built artefact. The check below
reads bytes rather than decoded text, which is the only way to see it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Tab, newline and carriage return are legitimate; every other C0 control is damage.
ALLOWED_CONTROL_BYTES = frozenset({0x09, 0x0A, 0x0D})

TEXT_SUFFIXES = frozenset(
    {
        ".py",
        ".md",
        ".yml",
        ".yaml",
        ".toml",
        ".cff",
        ".json",
        ".tex",
        ".bib",
        ".txt",
        ".cfg",
        ".csv",
        ".sha256",
        ".lock",
    }
)


def _tracked_text_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True, cwd=Path.cwd()
    )
    return [
        path
        for line in result.stdout.splitlines()
        if line and (path := Path(line)).suffix in TEXT_SUFFIXES and path.is_file()
    ]


def test_no_tracked_text_file_contains_a_stray_control_character() -> None:
    offenders: list[str] = []
    for path in _tracked_text_files():
        content = path.read_bytes()
        found = sorted(
            {byte for byte in content if byte < 0x20 and byte not in ALLOWED_CONTROL_BYTES}
        )
        if found:
            offenders.append(f"{path.as_posix()}: {[hex(byte) for byte in found]}")
    assert not offenders, "stray control characters (a lost backslash?): " + "; ".join(offenders)


@pytest.mark.parametrize(
    ("fragment", "expected"),
    [
        (b"\x07lpha", "0x7"),
        (b"\x08eta", "0x8"),
        (b"\x0crac", "0xc"),
    ],
)
def test_the_control_character_scan_sees_a_lost_backslash(
    tmp_path: Path, fragment: bytes, expected: str
) -> None:
    """The three escapes an authoring pipeline eats most often: \\a, \\b and \\f."""
    damaged = tmp_path / "damaged.md"
    damaged.write_bytes(b"text " + fragment + b" more\n")

    found = sorted(
        {byte for byte in damaged.read_bytes() if byte < 0x20 and byte not in ALLOWED_CONTROL_BYTES}
    )

    assert [hex(byte) for byte in found] == [expected]


def test_no_tracked_text_file_uses_crlf() -> None:
    """Git normalises to LF on commit, so a CRLF working tree hashes differently from the archive.

    That gap is exactly what `release-archive verify` catches after the fact. Catching it here
    means a release is never cut with a manifest that disagrees with what a downloader gets.
    """
    offenders = [
        f"{path.as_posix()} ({count} lines)"
        for path in _tracked_text_files()
        if (count := path.read_bytes().count(b"\r\n"))
    ]
    assert not offenders, "tracked text files using CRLF: " + "; ".join(offenders)
