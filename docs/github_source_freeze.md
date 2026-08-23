# GitHub Actions publication source freeze

The local analysis container may be network-restricted. The repository therefore includes
`.github/workflows/source-freeze.yml`, a manually triggered GitHub Actions workflow that performs
network retrieval on an internet-enabled runner while preserving the repository's immutable raw-data
contract.

## What the workflow does

For a source vintage `YYYY-MM-DD`, the workflow:

1. exports the exact OECD/Eurostat query manifest from `config/project.yml`;
2. fetches every manifest URL with bounded retries for transient HTTP/network failures;
3. rejects obvious transport error pages before freezing them;
4. stores response bytes unchanged under `data/raw/<vintage>/`;
5. records SHA-256, byte count, URL, source identifiers, HTTP metadata and retrieval timestamp;
6. verifies the complete source freeze against the manifest;
7. rebuilds GDP/hour, GDP/person-employed and decomposition panels **from frozen bytes only**;
8. runs Portugal and country-first cross-country analyses;
9. executes Ruff, mypy and pytest; and
10. uploads the raw freeze, processed panels, empirical outputs and a SHA-256 file manifest as one
    GitHub Actions artifact.

The workflow does not commit downloaded statistical data back to the repository. A completed
artifact is an explicit data vintage that can be downloaded, archived or imported into a release.

## Manual run

Open **Actions → Publication source freeze → Run workflow**. `vintage` may be left blank, in which
case the runner uses the current UTC date. `run_analysis=false` produces only the source freeze and
quality gates.

The same retrieval can be run on any network-enabled machine:

```bash
poetry run wage-transmission export-source-queries \
  --vintage 2026-08-22 \
  --output data/query_manifests/2026-08-22.json

poetry run wage-transmission fetch-source-freeze \
  --query-manifest data/query_manifests/2026-08-22.json \
  --output data/query_manifests/2026-08-22.fetch.csv \
  --audit-output data/query_manifests/2026-08-22.audit.csv \
  --registry data/raw/SNAPSHOT_REGISTRY.csv \
  --strict
```

## Failure semantics

A request is retried only for transport errors, HTTP 429, and HTTP 5xx responses. Permanent HTTP
errors and payload-shape failures fail immediately. Existing verified snapshots are reused without a
second network request. Existing snapshots with invalid hashes or metadata inconsistent with the
query manifest are not overwritten.

The `--strict` gate exits non-zero unless every query in the manifest is present and verified.

## Locked publication dossier (v0.6)

Before any source request is made, the workflow verifies `paper/specification_lock.json`. The lock
binds the project/model/publication configurations, package version and complete Python analysis
source tree. If any estimator or locked configuration has changed, the workflow fails before
fetching a publication vintage.

After the verified raw freeze is rebuilt and all empirical analyses complete, the workflow runs:

```bash
poetry run wage-transmission build-publication-dossier \
  --results-root results/vintages/${VINTAGE} \
  --specification-lock paper/specification_lock.json \
  --output results/vintages/${VINTAGE}/publication_dossier
```

The dossier contains the pre-specified primary coefficient and uncertainty, reliability eligibility
for flexible models, cross-country heterogeneity summaries, the accounting decomposition summary,
and a manifest hashing all inputs and outputs. It does not authorize causal language.

## Paper-facing packet

After `build-publication-dossier`, the workflow runs `tools/publication_report.py build` and
`tools/publication_report.py audit`. The formatter is outside the locked analysis package, so report
formatting can evolve without changing the pre-results estimator hash. The uploaded artifact includes
`paper/main.tex`, `paper/generated/`, and hashes for every generated fragment.
