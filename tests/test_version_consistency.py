"""A release publishes one version number; every file that states it must agree."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml

from wage_transmission.version import __version__


def test_pyproject_version_matches_package() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert payload["project"]["version"] == __version__


def test_citation_version_matches_package() -> None:
    payload = yaml.safe_load(Path("CITATION.cff").read_text(encoding="utf-8"))
    assert str(payload["version"]) == __version__


def test_zenodo_metadata_version_matches_package() -> None:
    payload = json.loads(Path(".zenodo.json").read_text(encoding="utf-8"))
    assert payload["version"] == __version__


def test_zenodo_and_citation_agree_on_licence() -> None:
    zenodo = json.loads(Path(".zenodo.json").read_text(encoding="utf-8"))
    citation = yaml.safe_load(Path("CITATION.cff").read_text(encoding="utf-8"))
    assert zenodo["license"].lower() == str(citation["license"]).lower()


def test_zenodo_and_citation_agree_on_authorship() -> None:
    """The ORCID and affiliation are cited metadata; the two files must not drift."""
    zenodo = json.loads(Path(".zenodo.json").read_text(encoding="utf-8"))
    citation = yaml.safe_load(Path("CITATION.cff").read_text(encoding="utf-8"))
    assert len(zenodo["creators"]) == len(citation["authors"])
    for creator, author in zip(zenodo["creators"], citation["authors"], strict=True):
        assert creator["name"] == f"{author['family-names']}, {author['given-names']}"
        assert creator.get("affiliation") == author.get("affiliation")
        # CFF records the ORCID as a URL; Zenodo wants the bare identifier.
        cff_orcid = str(author.get("orcid", "")).rsplit("/", 1)[-1]
        assert creator.get("orcid", "") == cff_orcid
