# Archiving a release on Zenodo

Zenodo mints a **Digital Object Identifier (DOI)** for an archived snapshot of this repository, so a
paper can cite the exact code and frozen inputs that produced its numbers.

Zenodo issues two DOIs:

- a **concept DOI**, which always resolves to the newest version — cite this in prose and put it in
  the README badge;
- a **version DOI**, which resolves to one specific archived release — cite this in a paper, because
  it never changes.

## The route this project uses

The repository is public, so Zenodo's GitHub integration applies: publishing a GitHub
Release archives the source tarball and mints a DOI automatically, with no manual upload.
Records are **open access**, matching the visibility of the code itself.

Route B below is retained for the case where a deposit must contain something the public
repository does not -- a frozen data vintage, for instance -- since the webhook only ever
archives what `git archive` exports.

One ordering constraint matters: Zenodo only archives releases published **after** the
repository switch is turned on. Enabling the integration does not retroactively capture an
existing release, so link the account first and publish the release second.

## Route A — GitHub integration (public repository)

Once, to link the accounts:

1. Sign in at [zenodo.org](https://zenodo.org) with GitHub and grant the requested permissions.
2. Open **GitHub** in the Zenodo account menu, find `DiogoRibeiro7/gdp-wage-transmission`, and
   switch it **On**. Zenodo installs a release webhook.

Then, for every release:

1. Work through the release checklist below.
2. Publish a GitHub release: `gh release create v0.7.0 --title "v0.7.0" --notes-file <notes>`.
3. Zenodo receives the webhook, archives the source tarball, and mints the DOI within a few minutes.
4. Copy the concept DOI into the README badge and `CITATION.cff`.

Zenodo reads [`.zenodo.json`](../.zenodo.json) for the deposit metadata: title, creators, licence,
keywords and description. Keep it in step with `CITATION.cff`; a test enforces that the version and
licence agree.

## Route B -- manual deposit (for deposits the repository cannot produce)

This produces the same DOI, but nothing is automated: each new version must be uploaded by hand
through **New version** on the existing record, which preserves the concept DOI.

1. Work through the release checklist below and tag the release locally.
2. Build a source archive from the tag, so the upload contains exactly the committed tree:

   ```bash
   git archive --format=tar.gz --prefix=gdp-wage-transmission-0.7.0/ \
     -o gdp-wage-transmission-0.7.0.tar.gz v0.7.0
   sha256sum gdp-wage-transmission-0.7.0.tar.gz
   ```

3. Upload it at [zenodo.org/uploads/new](https://zenodo.org/uploads/new), then copy the metadata
   from `.zenodo.json` into the form: upload type *Software*, licence *MIT*, the version, the
   creators and the description.
4. Under **Related identifiers**, add the repository URL with relation *is supplement to*.
5. Set **Access** to *Open*, matching the public repository. A deposit that must stay
   closed for a time should use *Embargoed* with a date rather than indefinite
   restriction, so the files open automatically.
6. Reserve the DOI, publish, and record the concept DOI in the README and `CITATION.cff`.

Publishing is **permanent**: a Zenodo record cannot be deleted once published, and its DOI is
minted for good. Check the metadata and the access level before pressing publish.

Note that `git archive` exports only tracked files. The untracked working artefacts under
`results/` and `data/raw/` are therefore **not** in the archive; they are reproducible from the
query manifests, which are tracked. If a deposit is meant to include a frozen data vintage, add
that vintage directory to the upload explicitly and say so in the deposit description.

## Release checklist

Run before tagging:

```bash
make check          # ruff, ruff format, mypy, pytest
make integrity      # release manifest and exported archive
```

`make integrity` includes `make release-archive`, which hashes what `git archive` actually exports
and checks it against the manifest carried inside that archive. This is the check that matters for
a deposit: the manifest is generated from the working tree, and on Windows a file can differ
between the working tree and the bytes git exports, so a manifest that verifies locally can still
fail for whoever downloads the archive.

and confirm:

- [ ] The version is identical in `pyproject.toml`, `src/wage_transmission/version.py`,
      `CITATION.cff` and `.zenodo.json`. `tests/test_version_consistency.py` checks this.
- [ ] `CHANGELOG.md` has an entry for the release, including its validation status.
- [ ] `RELEASE_MANIFEST.sha256` was regenerated after the final content change
      (`make release-manifest`).
- [ ] No data, credentials or large binaries were added to the tracked tree.

## Verifying an archived release

Anyone can check that a Zenodo archive matches what this repository recorded:

```bash
tar -xzf gdp-wage-transmission-0.7.0.tar.gz
cd gdp-wage-transmission-0.7.0
poetry run python tools/integrity.py release-manifest verify
```

Files listed in the manifest but absent from the archive — the untracked `results/` tree, for
instance — are reported as missing rather than as mismatches. Any *mismatch* means the archived
bytes differ from the bytes the manifest recorded, and the archive should not be trusted as the
source of a published number.

## After the first DOI exists

Add the concept DOI badge to the top of `README.md`:

```markdown
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
```

and the identifier to `CITATION.cff`, so GitHub's **Cite this repository** panel offers it:

```yaml
doi: 10.5281/zenodo.XXXXXXX
identifiers:
  - type: doi
    value: 10.5281/zenodo.XXXXXXX
    description: Concept DOI for all versions
```
