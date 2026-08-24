# Changelog

## 0.7.0 — 2026-08-24

First tagged release since the repository was reorganised. It collects the two revisions below:
the removal of the manuscript trees and the specification-lock machinery, and the implementation
of the outstanding continuation-prompt milestones.

### Breaking

The specification-lock API is gone. Code importing `SpecificationLock`, `LockedFile`,
`build_specification_lock`, `write_specification_lock`, `read_specification_lock` or
`verify_specification_lock` from `wage_transmission.publication` will fail. The
`lock-publication-spec` CLI command and the `--specification-lock` option of
`build-publication-dossier` are removed, as is `tools/publication_report.py`.

`build_publication_dossier` no longer accepts `specification_lock` or `root`. It still hashes
every input and output into its manifest, so a dossier remains internally auditable, but it is no
longer bound to a pre-results commitment.

### Added

Formal single-break inference with a wild-bootstrap p-value and a bootstrap break-date interval;
block-bootstrap bands for the time-varying elasticity and local projections; a panel
fixed-effects estimator with country-clustered standard errors; a source-schema audit that fails
on mixed units or price bases; coverage-gated median-earnings support; and a release manifest
recording package, interpreter, numerical-library and configuration state alongside raw and
output digests.

### Known limitations

The OECD median-earnings dataflow identifier in `config/data_sources.yml` is marked
`status: unverified` and must be confirmed against the OECD Data Explorer before a live source
freeze. Continuous integration has not run against this release: GitHub Actions is disabled on
the account for billing reasons, so the gates below were verified locally only.

### Validation

- 118 tests pass; coverage 71.53% against a 65% floor.
- `ruff check`, `ruff format --check` and `mypy --strict` clean.
- Release manifest and the exported archive of the tag both verify.


## Continuation milestones implemented — 2026-08-24

Works through the milestone list in the repository's continuation prompt. Six of the eight
milestones needed implementation; the GDP-per-worker robustness series and the
serialized-output-only table generation were already in place.

### Added

- **Formal break inference** (`models/break_inference.py`), separate from the BIC segmentation.
  A sup-F over trimmed candidate dates, a wild-bootstrap p-value under the no-break null that
  re-runs the whole date search per replication, and a bootstrap break-date interval. No
  tabulated critical values are used, and a poorly located date is reported as such.
- **Block-bootstrap bands** (`models/_bootstrap.py`) for the time-varying elasticity and the
  local projections. A circular moving-block resample over the joint growth pairs, re-integrated
  to levels and passed back through the same validated entry points the point estimates use.
  Bands are pointwise, not simultaneous.
- **Panel fixed effects with country-clustered errors** (`estimate_panel_fixed_effects`). The
  existing `fixed_effect_estimate` was a meta-analytic inverse-variance average, not a within
  estimator; this is the panel estimator the milestone asked for. It carries its own caveat: with
  fewer than about 30 clusters the standard errors are optimistic, and the result says so.
- **Source-schema audit** (`data/schema_audit.py`) recording the unit, price base, observation
  status, transformation and revision flag that canonicalisation discards. Mixed units or price
  bases fail loudly; status and revision variation is recorded, since that is what makes a later
  revision visible.
- **Median-earnings support** (`data/median_wages.py`) with per-country coverage gating.
  Countries below the coverage threshold are dropped and reported rather than carried with gaps.
  The dataflow identifier is supplied from configuration and is marked `status: unverified`,
  because a wrong median identifier returns a neighbouring concept rather than failing.
- **Release manifest** (`release.py`) recording package, interpreter and numerical-library
  versions, configuration content and digests, raw snapshot digests and output digests. Keyed by
  source vintage rather than wall-clock time, so it is reproducible.
- An `inference` configuration block governing resampling cost, and the new estimators wired into
  `analyse_country` so their results are serialized alongside the rest.

### Notes and limitations

The median dataflow identifier in `config/data_sources.yml` is **unverified** and must be
confirmed against the OECD Data Explorer before a live source freeze. The coverage gate, the
canonicaliser and their tests are complete and exercised against recorded frames; only the
identifier itself awaits confirmation, and the code refuses to assume a default.

The pooled panel estimate is a robustness check, never a replacement for the country-specific
estimates. None of the new estimators licenses causal language: the break test locates a date
without explaining it, and the bands describe sampling uncertainty only.

### Validation

- **118 tests pass**, up from 84; coverage 71.53% against a 65% floor.
- `ruff check`, `ruff format --check` and `mypy --strict` are clean.
- The suite now takes about 75 seconds, dominated by the bootstrap replications in the pipeline
  test. `inference.enabled: false` skips them for a fast exploratory run.


## Manuscript trees removed from version control — 2026-08-24

The `paper/` and `papers/` trees are no longer tracked, and were purged from the git history
rather than merely deleted going forward. Manuscripts, their generated fragments and the
specification locks that bound them to a source freeze are now maintained outside this repository.

### Removed

- `paper/` and `papers/` in full, including both manuscripts, the compiled PDF, the generated
  LaTeX fragments, `paper/specification_lock.json` and
  `papers/wage_distribution_breaks/analysis_lock.json`.
- The specification-lock machinery in `wage_transmission.publication`: `SpecificationLock`,
  `LockedFile`, `build_specification_lock`, `write_specification_lock`,
  `read_specification_lock`, `verify_specification_lock` and the analysis source-tree hash.
- The `lock-publication-spec` CLI command, and `--specification-lock` from
  `build-publication-dossier`.
- `tools/publication_report.py`, the paper-facing packet builder, and its tests.
- The analysis-lock half of `tools/integrity.py`, along with `combined_sha256`.
- `docs/specification_lock.md` and `docs/paper_generation.md`.
- The lock-verification and paper-packet steps of the publication source-freeze workflow, and the
  `spec-lock`, `paper-packet`, `paper-audit`, `paper2-lock`, `paper2-lock-verify` and `paper2-pdf`
  Makefile targets.

### What this costs

The repository no longer verifies that estimator code and configuration are unchanged since a
specification was fixed. `build-publication-dossier` still hashes every input and output into its
manifest, so a dossier remains internally auditable, but nothing now binds it to a pre-results
commitment. Reinstating that guarantee means restoring the lock machinery from this commit's
parent.

The dossier is now the handover point to a manuscript: its tables and manifest are what a paper
consumes, and the paper itself lives elsewhere.

### Retained

`tools/wage_distribution_breaks.py` stays, since it estimates rather than typesets; its
`--paper-dir` flag can still write fragments to a local, untracked manuscript tree.
`RELEASE_MANIFEST.sha256` and the archive verifier are unaffected and still run under
`make integrity`.

### Validation

- **72 tests pass** (down from 84; twelve covered the removed lock machinery and paper packet).
- `ruff check`, `ruff format --check` and `mypy --strict` are clean.
- The release manifest and the exported archive of `HEAD` both verify.


## Repository engineering revision — 2026-08-23

An infrastructure-only revision. It changes **no estimator, no specification and no estimated
number**; it makes the repository's quality gates, packaging and integrity artefacts reproducible.

### Added

- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue forms (including a dedicated
  data-and-reproducibility form), a pull-request template and `CODEOWNERS`.
- `tools/integrity.py`, which writes and verifies the Paper 2 analysis lock and
  `RELEASE_MANIFEST.sha256`. Both artefacts previously existed without a generator, so their
  digests could not be recomputed by a reader.
- Dependabot updates, grouped so the scientific stack is reviewed separately from dev tooling.
- `.gitattributes`, `poetry.lock`, and `make` targets for `format`, `coverage`, `build` and `clean`.

### Changed

- Project metadata moved to PEP 621 with an SPDX licence, classifiers and project URLs.
- CI split into a quality job, a 3.11–3.13 test matrix and a build job that installs the wheel and
  checks the console entry point; runs are cached, concurrency-limited and read-only by default.
- `ruff format` applied across the tree (29 files); ruff now knows that Typer declares CLI metadata
  in argument defaults and that en dashes in economic notation are intentional.
- pytest resolves the repository root, so the `tools/` suites no longer need a `PYTHONPATH` prefix.

### Fixed

- **Hashed artefacts were platform-dependent in two ways.** `write_specification_lock` serialised
  `str(path)`, so a lock written on Windows recorded backslash paths and failed verification on
  Linux CI; and the specification lock, snapshot provenance metadata, model result JSON and the
  dossier summary were all written with the platform's line ending, so the same results hashed
  differently on Windows and Linux. Paths are now stored in POSIX form and every hashed artefact is
  written with LF, both covered by regression tests.
- `_json_default` passed dataclass *types* to `asdict`, which only accepts instances.
- Three lint-level defects: a swallowed `ValueError`, a manual successive-pair `zip`, and a
  bootstrap quantile whose `int(round(...))` cast depended on numpy scalar rounding.

### Specification locks re-issued

Formatting the package changed the bytes both locks hash, so both were re-issued. The previous
digests are recorded here so the transition stays auditable:

| Artefact | Before | After |
| --- | --- | --- |
| `paper/specification_lock.json` label | `pre-source-freeze-2026-08-22` | `post-tooling-relock-2026-08-23` |
| `analysis_code_sha256` (`src/wage_transmission`) | `c71ac9313e45242a8ecd9c7bce5b6d7e0b84c8c8ecb07b17c5c0df20d9e3b2a2` | `cbad65d0947e9a2974d4299468936a4da95ac61466b6200f37aba32ce49cdb2b` |
| `tools/wage_distribution_breaks.py` | `68c18ca853985d778e7a3e0d939764b89c47c3436cd069de45dbdf77e193043f` | `d278b06eae6882ccab0977d04fae3dafef7d07a8b335129d56a18c926cc90d3f` |
| Paper 2 `combined_sha256` | `c1c00f2db2a9a9cf5903c020495edab53d4d0be1bd96509fb94906208d653199` | recomputed by `tools/integrity.py` |

The previous Paper 2 `combined_sha256` is **not reproducible** from the repository: no generator
existed, and it does not follow from the recorded per-file digests under any tested derivation. The
three per-file digests it recorded do verify exactly against the pre-revision bytes. The combined
digest is now defined explicitly as SHA-256 over sorted `sha256  path` lines, matching `sha256sum`
output, and is recomputable with `make paper2-lock-verify`.

This re-lock is **not** a new pre-registration. Paper 1's original lock was created before its
source freeze; this one records the same specification after a numerically inert tooling pass, and
the label says so.

### Validation

- **77 tests pass**: the 67 existing tests, regression tests for POSIX lock paths and LF-only artefact bytes, and eight covering the new integrity tool.
- `ruff check`, `ruff format --check` and `mypy --strict` are clean; coverage is 68% against a 65%
  floor (67.78% measured).
- Equivalence evidence for the re-lock: regenerating Paper 2's LaTeX fragments from the unchanged,
  hash-verified input CSV with the seeded bootstrap reproduces **byte-identical** output, and
  Paper 1's dossier and paper-integrity gates in the test suite pass unchanged.


## Exploratory live-data revision 5 — 2026-08-23

This revision adds a **second paper to the same repository** while preserving Paper 1's locked
analysis package at `0.6.0`. No file under `src/wage_transmission` is changed.

### Added

- `papers/wage_distribution_breaks/` with a complete second-paper scaffold, LaTeX manuscript,
  methods/analysis protocol, generated result fragments and a compiled PDF.
- `tools/wage_distribution_breaks.py` for continuous one-kink segmented trends in log D10/D1,
  D9/D1, D10/D5 and mean/median ratios.
- Endogenous break selection with a sup-F statistic and 5,000-repetition circular moving-block
  residual bootstrap.
- Separate historically specified 2008 and 2009 break models with Newey-West HAC uncertainty.
- A post-hoc analysis lock that is explicitly **not** labelled a preregistration.
- Machine-readable break-search, historical-break, summary, provenance and figure outputs.
- Three tests covering selected break dates and the forced-2008/2009 compression results.

### Exploratory finding

The data do not identify one common 2008 break. D10/D1 and D9/D1 select 2006, with a bootstrap
break-date interval reaching roughly 2008; D10/D5 selects 2013 and mean/median selects 2014.
Forced 2008 and 2009 models nevertheless imply markedly negative post-break compression slopes.
The coherent interpretation is therefore **staggered wage compression**, with the GFC retained as
a historically motivated candidate transition rather than imposed as the unique endogenous date.

### Validation

- **67 tests pass** under `PYTHONPATH=.:src pytest -q`.
- `compileall` succeeds for `src`, `tools` and `tests`.
- Paper 1's pre-results specification lock verifies unchanged.
- Paper 2 compiles successfully with `pdflatex`.

## Exploratory live-data revision 4 — 2026-08-23

This is a **reporting/results-only exploratory revision**. The analysis package remains at `0.6.0`;
no file under `src/wage_transmission` is changed, so the pre-results specification lock remains
intact.

### Added

- Exploratory 2002–2024 mainland-Portugal wage-distribution panel from official GEP/MTSSS
  `Quadros de Pessoal` chronological tables, covering the mean, median and mean monthly gain in
  each decile.
- Separate historical (2002–2014) and current (2014–2024) source transcriptions with a strict
  exact-match audit at the duplicated 2014 bridge year.
- October-HICP deflation to align the price reference month with the October remuneration
  observation rather than using annual-average inflation.
- Real cumulative growth by mean, median and all ten decile-average gains; mean/median, D10/D1,
  D9/D1 and D10/D5 dispersion ratios; and two exploratory figures.
- A common-endpoint 2002–2023 comparison with the existing exploratory OECD GDP/person-employed
  panel, kept separate from the locked distributed-lag inference.
- `docs/live_data_wage_distribution_audit.md` and machine-readable provenance/hashes.
- Tests for bridge-year disagreement, HICP month alignment, decile-to-mean reconstruction,
  non-publication status and distribution-growth output completeness.

### Exploratory finding

For the covered full-time employee population, 2002–2024 real monthly gain rises about 25.0% at
the mean, 30.9% at the median, 55.2% in the bottom decile and 13.4% in the top decile. The D10/D1
average-gain ratio falls from 6.83 to 4.99. On the common 2002–2023 productivity endpoint,
GDP/person employed grows 19.12% and the real mean gain 18.89%, while D1 grows 47.12% and D10 only
8.41%. Aggregate matching therefore does not imply uniform incidence.

### Validation

- **64 tests pass** under `PYTHONPATH=.:src pytest -q`.
- Python `compileall` succeeds for `src`, `tools` and `tests`.
- The pre-results v0.6 specification lock remains unchanged because no locked analysis source is modified.

## Exploratory live-data revision 3 — 2026-08-23

This is a **reporting/results-only exploratory revision**. The analysis package remains at `0.6.0`;
no file under `src/wage_transmission` is changed, so the pre-results specification lock remains
intact.

### Added

- `tools/exploratory_annual_decomposition.py`, which applies the already-locked accounting identity
  year by year without changing the analysis package.
- A complete 1996–2025 annual Portugal input table for nominal GDP, D.1 compensation, the GDP
  deflator, annual-average HICP and LFS employees.
- A frozen 360-row Eurostat/FRED monthly HICP table used to construct the 30 annual HICP averages.
- Annual employee-independent locked contributions, a separately labelled LFS-denominator
  sensitivity, a machine-readable annual summary and provenance record.
- `docs/live_data_annual_decomposition_audit.md` and five tests covering missing/complete `SAL_DC`,
  exact accounting closure, concept labelling and annual-input contracts.

### Exploratory finding

- The cumulative employee-independent terms still telescope to the endpoint result: `+0.4086` log
  points from real GDP, `+0.0143` from the raw D.1/GDP labour share and `+0.1466` from relative
  prices.
- The near-flat endpoint labour share masks sizeable annual movements. In the LFS sensitivity, 2011
  and 2012 are the clearest compression years (`-0.0581` and `-0.0591` log points overall), whereas
  2020 combines a large real-output fall (`-0.0856`) with a large positive labour-share contribution
  (`+0.0641`) and still produces a small positive accounting total (`+0.0230`).
- In 2022, real GDP contributes `+0.0675` log points, but the labour-share, employment and relative-
  price terms are all negative; the LFS-sensitivity total is `-0.0247`.
- These are accounting decompositions, not causal mechanisms. The LFS denominator remains a
  concept-mismatched sensitivity and is not publication-eligible.
- The exact annual `SAL_DC` vector is still unavailable through the indexed-web surface, so the
  locked annual employment and total terms remain deliberately missing until the verified raw
  source freeze supplies them.

### Validation

- **58 tests pass** under `PYTHONPATH=.:src pytest -q`.
- Python `compileall` succeeds for `src`, `tools` and `tests`.
- The pre-results v0.6 specification lock remains unchanged because no locked analysis source is modified.

## Exploratory live-data revision 2 — 2026-08-23

This is a **reporting/results-only exploratory revision**. The analysis package remains at `0.6.0`;
no file under `src/wage_transmission` is changed, so the pre-results specification lock remains
intact.

### Added

- `tools/exploratory_endpoint_decomposition.py`, a no-network reporting helper that applies the
  already-locked accounting identity to two endpoint observations.
- Portugal 1996–2025 endpoint inputs, employee-independent locked decomposition output, a separately
  labelled LFS-denominator sensitivity, machine-readable summary and decomposition provenance.
- `docs/live_data_decomposition_audit.md`, including the conceptual mismatch between LFS employees
  and Eurostat national-accounts `SAL_DC`.
- Four tests covering exact identity closure, locked missing-denominator behaviour, sensitivity
  labelling and invalid endpoint inputs.

### Exploratory finding

- Raw D.1 compensation share of GDP rises from about `47.44%` in 1996 to `48.12%` in 2025
  (`+0.68` percentage points).
- Employee-independent endpoint contributions are `+40.86` log points from real GDP, `+1.43` from
  the raw labour share and `+14.66` from the GDP-deflator/HICP price wedge.
- The locked `SAL_DC` employment contribution remains **incomplete** because the indexed-web route
  does not expose the 1996 Portugal national-accounts employee endpoint with sufficient provenance.
- A non-publication LFS sensitivity gives `-34.09` log points from employee growth and `+22.86` log
  points overall, equivalent to about `+25.68%` in HICP-deflated D.1 compensation per LFS employee.
- The endpoint exercise is descriptive, non-causal and cannot reveal when the contributions occurred.

### Validation

- **53 tests pass** under `PYTHONPATH=.:src pytest -q`.
- Python `compileall` succeeds for `src`, `tools` and `tests`.
- The pre-results v0.6 specification lock remains unchanged because no locked analysis source is modified.

## Exploratory live-data revision 1 — 2026-08-23

This is a **reporting/results-only exploratory revision**. The analysis package remains at `0.6.0`, and no file under `src/wage_transmission` is changed. The pre-results specification lock therefore remains intact.

### Added

- `results/exploratory_live/`, containing a non-publication Portugal run on OECD Data Explorer indexed values for the common 1995–2023 sample.
- A side-by-side locked-model comparison of GDP per person employed and GDP per hour.
- `PROVENANCE.json` with exact official page references, artifact hashes, `publication_eligible: false`, and the explicit exclusion reason.
- `docs/live_data_exploratory_audit.md`.

### Exploratory finding

- GDP/person-employed cumulative distributed-lag estimate: `0.222` (HAC SE `0.543`, p = `0.684`).
- GDP/hour cumulative distributed-lag estimate on the same 1995–2023 sample: `-0.698` (HAC SE `0.780`, p = `0.371`).
- Neither specification supports Engle–Granger cointegration at 5%.
- These estimates cannot enter the publication dossier until reproduced from a verified raw source freeze.

## Reporting revision 1 — 2026-08-22

This is intentionally a **reporting-only revision**. The analysis package remains at `0.6.0` because
`paper/specification_lock.json` binds that package version and the full analysis source tree. No file
under `src/wage_transmission` is changed by this revision.

### Added

- `tools/publication_report.py`, a formatter that verifies the locked publication dossier before
  generating paper-facing LaTeX and Markdown fragments.
- `paper/main.tex`, which contains conceptual prose and imports empirical values only from
  `paper/generated/`.
- `paper/generated/paper_packet_manifest.json`, binding the dossier manifest and every generated
  report fragment with SHA-256.
- Paper-source audit that rejects manual `table`, `tabular`, or `longtable` environments outside the
  generated directory and rejects edits to generated fragments after manifest creation.
- `docs/paper_generation.md` plus `make paper-packet` and `make paper-audit`.

### Changed

- The GitHub publication-freeze workflow now builds and audits the paper packet after the locked
  publication dossier, includes it in the checksum manifest, and uploads it with the source freeze.
- Generated supporting-model tables show both eligible and non-eligible reliability-gated results;
  non-eligible estimates are not silently dropped.

### Validation

- **49 tests pass**.
- New tests reject dossier tampering, generated-fragment tampering, and manually assembled paper
  tables.
- The pre-results `paper/specification_lock.json` still verifies because the locked analysis package
  is unchanged.

## 0.6.0 — 2026-08-22

### Added

- Pre-results publication specification hierarchy in `config/publication.yml`.
- Immutable `paper/specification_lock.json` binding project/model/publication configuration,
  package version and the complete Python analysis source tree.
- `lock-publication-spec` CLI command that refuses to overwrite a different lock.
- `build-publication-dossier` CLI command that mechanically produces primary-estimate,
  reliability-gate, cross-country and decomposition tables from one verified result vintage.
- `publication_manifest.json` with input/output hashes and an explicit
  `causal_claims_authorized: false` field.
- `docs/specification_lock.md` documenting the pre-results hierarchy and claim gates.

### Changed

- GDP per person employed is formally locked as the primary denominator-matched annual driver;
  GDP per hour remains the secondary productivity definition.
- The cumulative distributed-lag transmission coefficient is formally locked as the primary
  inferential estimand.
- GitHub's publication source-freeze workflow verifies the specification lock before fetching data
  and builds the locked publication dossier after the empirical pipeline succeeds.

### Validation

- **45 tests pass** under the source-tree test environment.
- New tests cover immutable specification-lock behaviour, configuration-hash changes, analysis-code
  hash changes and reliability-gated publication dossier generation.
- Package and test modules compile successfully with Python `compileall`.

### Empirical boundary

No new official empirical claim is introduced by v0.6. The lock is intentionally created before a
live internet-enabled source freeze is promoted, so the publication hierarchy cannot be chosen in
response to the eventual GDP-per-employed-person or decomposition results.

## 0.5.0 — 2026-08-22

### Added

- A typed publication-freeze HTTP fetcher that consumes the exact source-query manifest rather than reconstructing URLs independently.
- Bounded exponential retries for transport failures, HTTP 429 and HTTP 5xx responses; permanent failures are not retried.
- Transport-shape validation before immutable storage: OECD responses must be labelled SDMX CSV and Eurostat responses must be JSON-stat data.
- Fetch-status tables separating newly downloaded, reused verified, and failed source requests.
- HTTP provenance fields (status, content type, ETag and Last-Modified when supplied) in snapshot metadata.
- A manually triggered GitHub Actions `Publication source freeze` workflow that can fetch the complete official vintage on an internet-enabled runner, rebuild panels from frozen bytes, run the empirical pipeline and upload a checksummed artifact.
- `make freeze-fetch VINTAGE=YYYY-MM-DD` and `docs/github_source_freeze.md`.

### Changed

- Source-freeze audits now check manifest provenance metadata (URL, query id, dataset, flow and measure when present) in addition to byte/hash integrity.
- Snapshot registries now expose `query_id` and `purpose`.
- Existing valid snapshots are reused idempotently; inconsistent or tampered existing snapshots are failed rather than overwritten.

### Validation

- **40 tests pass** under the source-tree test environment.
- New tests cover transient retry, idempotent verified reuse, HTTP-200 error-page rejection and manifest-metadata mismatch detection.
- Package and test modules compile successfully with Python `compileall`.

### Empirical boundary

The local execution container remains unable to resolve the OECD/Eurostat hosts, so v0.5 does not claim that the 63-response publication vintage was downloaded here. The new GitHub Actions workflow is the reproducible internet-enabled execution path for closing that gap.

## 0.4.0 — 2026-08-22

### Added

- Deterministic source-query manifests covering every OECD and Eurostat request required by the configured empirical release.
- A 63-query `2026-08-22` publication-freeze manifest and an explicit source-freeze audit.
- Byte-preserving import of externally downloaded official responses with `external_import` provenance rather than false HTTP provenance.
- SHA-256/byte-count verification for individual raw snapshots and a deterministic `SNAPSHOT_REGISTRY.csv` builder.
- Offline reconstruction of the OECD GDP-per-hour or GDP-per-employed-person panels from already-frozen CSV responses.
- Offline reconstruction of the complete Eurostat decomposition panel from already-frozen JSON-stat responses.
- Semantic source contracts that reject hash-valid but conceptually wrong OECD/Eurostat payloads (for example GDP/hour passed as GDP/person-employed, or D.1 passed as GDP).
- A processed-vintage comparison tool that distinguishes revisions, additions, deletions and unchanged observations and summarises revision magnitudes.
- Explicit source-vintage directories for the network download commands via `--vintage`.
- Publication workflow documentation in `docs/source_vintages.md`.

### Changed

- OECD average-wage requests now pin the current constant-price code (`Q`) directly in the SDMX key and retain the response-label check as a second data-contract guard.
- Eurostat requests now include `sinceTimePeriod` and `untilTimePeriod`; raw files named for a requested range contain that range directly.
- Provenance schema is version 3 and supports an explicit retrieval method (`http` or `external_import`).
- Raw snapshot registries expose the source-vintage directory when one is used.

### Validation

- **36 tests pass**.
- Package and test modules compile successfully with Python `compileall`.
- CLI discovery succeeds with all source-freeze/offline/vintage commands registered.
- The configured release manifest contains 63 source queries.

### Empirical boundary

The execution container has no outbound DNS. Therefore the current `2026-08-22` source-freeze audit correctly reports all 63 official responses as missing. The release does not convert indexed Data Explorer output or manually transcribed reference data into fake raw API snapshots.

## 0.3.0 — 2026-08-22

### Added

- Exact Eurostat national-accounts decomposition of real compensation per employee growth into real GDP, labour share, employee-count and relative-price components.
- Eurostat inputs for nominal GDP, real GDP, compensation of employees (`D1`), domestic-concept employees (`SAL_DC`) and all-items annual-average HICP (`CP00`, `INX_A_AVG`).
- Pre-merge decomposition coverage audit by country and source series.
- Annual and cumulative decomposition figures and a dedicated decomposition notebook.
- HAC uncertainty for the cumulative distributed-lag transmission coefficient.
- Country-first cross-country summaries with inverse-variance fixed effects, DerSimonian-Laird random effects, Cochran's Q and I-squared.
- Provenance schema v2 with UTC retrieval time, query filters, byte count and SHA-256 metadata.
- Immutable raw-snapshot behaviour: identical downloads are idempotent; different bytes cannot overwrite an existing raw path.

### Changed

- GDP per person employed is retained as a denominator-explicit matched annual productivity driver rather than being conflated with GDP per hour.
- Cross-country aggregation is secondary to the country-level estimate table.
- Decomposition plots stack positive and negative contributions separately.

### Validation

- 26 unit/integration tests pass.
- Package and test modules compile successfully with Python `compileall`.
- Synthetic CLI smoke tests complete for both the one-country decomposition and four-country cross-country workflows.

### Empirical boundary

No fresh OECD or Eurostat HTTP payload is claimed as frozen by this release because the current execution environment cannot retrieve and archive the raw responses. Existing frozen Portugal reference evidence remains explicitly distinguished from untouched API snapshots.
