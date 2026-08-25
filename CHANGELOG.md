# Changelog

## v0.8.0 — a panel estimate that answers the paper's question — 2026-08-25

The previous release reported a pooled panel coefficient of 0.327 and placed it beside a median
country multiplier of 0.382 and a random-effects summary of 0.309, close enough that the three
read as agreement. They were not comparable. The pooled regression was **static** — wage growth on
contemporaneous driver growth, no lags, no lagged dependent variable — while the paper's estimand
is a **cumulative multiplier** from a dynamic specification. The sample sizes made the difference
visible and were not read: 389 observations against 363.

This release replaces that number with one that targets the same quantity.

### The specification, and when it was fixed

`wage_transmission.models.dynamic_panel` estimates

```
dlog w_it = a_i + l_t + sum_{j=0..2} b_j dlog p_{i,t-j} + g dlog w_{i,t-1} + u_it
Theta_panel = (b_0 + b_1 + b_2) / (1 - g)
```

with country and year effects as the primary specification and country effects alone as the
sensitivity. The two productivity drivers are estimated separately and never pooled. Two driver
lags and one dependent lag cost three observations per country, giving 12(28) + 27 = 363.

The whole specification — structure, estimator, bootstrap plan and reporting gates — was locked
**before** the source snapshot behind these results was retrieved. The lock artefact stays outside
version control as always, so its digests are recorded in `docs/specification_lock.md`, and the
commit carrying them precedes the commit carrying the snapshot. The ordering can be checked from
the public history rather than taken on trust.

That makes this a **prospectively locked follow-up analysis**. It is not confirmatory and it is
not out-of-sample evidence: the specification was written because of results already seen in
v0.7.1, on the same countries and the same years.

### The snapshot returned no new data

All 63 official queries were re-run on 2026-08-25 under the same query manifest. **Every response
was byte-identical to the 2026-08-24 freeze.** No OECD or Eurostat revision occurred between the
two dates, so the vintage analysed here contains exactly the observations the previous release
analysed. That is recorded in the paper as well as here, because it settles how the new estimate
must be described.

### Bias correction: what was implemented, and what was not

A lagged dependent variable beside fixed effects biases LSDV downward by order `1/T`
(Nickell 1981). Twenty-eight effective years shrink that bias without removing it, and thirteen
countries are far too few for Arellano–Bond or system GMM, whose asymptotics run in the wrong
direction here.

The correction implemented is **simulation-based** (Everaert and Pozzi 2007), **not** the
analytical Kiviet–Bruno expansion, and the substitution is deliberate. Bruno's (2005)
approximation for unbalanced panels is derived for a model with individual effects and strictly
exogenous regressors; it does not accommodate the year effects the primary specification carries.
Using it would have meant dropping the year effects or applying a bias formula outside its
derivation. The simulation correction handles both fixed-effect dimensions and the unbalanced
endpoint directly.

It is verified rather than asserted. On panels generated with known parameters at this sample's
dimensions, the correction removes 88% to 97% of the LSDV bias across true persistence from 0.3
to 0.7. The uncorrected bias is of the sign and order `-(1+g)/T` predicts but does not track it
closely -- it stays near -0.045 as `g` rises, where the approximation moves from -0.046 to
-0.061 -- because the approximation is derived without the exogenous regressors this design has.
That is a reason to measure the correction rather than assume it, and the check runs in the test
suite.

**The correction addresses dynamic fixed-effects bias. It does not solve contemporaneous
endogeneity between productivity and wages.** The coefficient remains a reduced-form conditional
association.

### Inference

Country-clustered normal intervals with thirteen clusters are not reliable, and a delta-method
interval around a ratio is optimistic twice over. Intervals come instead from a circular
moving-block bootstrap in which each drawn block carries the complete thirteen-country
cross-section, so contemporaneous cross-country dependence survives the resampling. The
resampling universe is restricted to years every country observes, and the United Kingdom's
missing endpoint is reinstated by giving it one fewer resampled year, so every replication
reproduces the observed panel shape exactly. Lags are rebuilt after concatenation, the corrected
model is re-estimated in each replication, and `Theta` is computed inside it.

Block length four with 4,999 replications is primary; block lengths three and five are frozen
sensitivity checks. Driscoll–Kraay standard errors are recorded as a secondary diagnostic only.

One property of resampling data rather than residuals is reported rather than buried: gluing
blocks breaks the dynamic relation at each boundary, so persistence within a replication is
attenuated. The median replication is therefore reported beside every point estimate, so the
displacement between them is visible.

### Results

All six gates passed for every specification: `|g| < 1`, at least 25 effective years, a finite
multiplier in at least 95% of replications, at least 95% convergence, no rank deficiency, and all
4,999 replications requested and completed. 4,999 of 4,999 completed, with 100% convergence and a
finite multiplier in 100%, on both drivers.

| Driver | Fixed effects | Corrected Theta | Bootstrap 95% CI |
| --- | --- | ---: | --- |
| GDP per person employed | country + year | 0.551 | [0.322, 0.744] |
| GDP per person employed | country | 0.424 | [0.032, 0.658] |
| GDP per hour | country + year | 0.251 | [-0.058, 0.633] |
| GDP per hour | country | 0.282 | [-0.082, 0.592] |

The primary interval is the only one in the paper excluding both zero and one. The paper says
plainly why that is not a stronger finding than the country estimates: it uses the same
country-years, it reaches its precision by imposing dynamics the country estimates argue against,
it falls to [0.032, 0.658] once the year effects come out, and it contains zero on the secondary
driver.

### Bootstrap replications raised

`band_replications` and `break_bootstrap_replications` rise from 199 and 499 to 1,999. This was
deferred from the previous vintage because it changes a hashed configuration file and so requires
a new lock. At 199 replications the 2.5th percentile fell on roughly the fifth ordered value; at
1,999 it falls on the fiftieth. The break test's p-values move from 0.072 to 0.069 on the primary
driver and 0.182 to 0.170 on the secondary; neither changes a verdict.

### Manuscript

- The contemporaneous panel appendix is removed. `tools/panel_robustness.py` and its artefact stay
  in the repository as a historical record, with a docstring saying not to wire it back in.
- The residual ADF description was wrong. It said "a constant and no trend"; the code runs the
  residual test with **no deterministic term** and caps the AIC lag search at
  `min(ceil(12(n/100)^(1/4)), floor(n/2) - 1)`, which is nine here. The AIC selects zero lags in
  eight of thirteen countries and six in Spain, so the test's power varies across the panel — now
  stated.
- The break-test table, the GDP-per-hour local projections, the covariance/`I²` corrections, the
  limitation numbering and the removal of every unconditional "optimistic" are carried forward
  from the previous round and verified again here.
- Section numbers typed by hand are replaced by real cross-references. They happened to be right,
  which is the problem.
- Nine references added, each checked against Crossref before being written: Nickell, Kiviet,
  Bruno (both papers), Everaert–Pozzi, Judson–Owen, Arellano–Bond, Blundell–Bond, Driscoll–Kraay.
  33 entries, all cited, no undefined citations.

### Guards

- `preflight` gains regression tests for the exact malformed reference that once printed
  `efsec:panel-appendix` on a compiled page, for damage inside a generated fragment, and for the
  intact `\ref{sec:...}` that must not trip the same check.
- A new repository-wide test reads every tracked text file as **bytes** and rejects stray control
  characters. A lost backslash turns `\alpha` into a bell character followed by `lpha`, which
  renders as nothing and survives review. It caught two such defects in this release's own
  documentation while it was being written.

### Validation

- **166 tests pass**, up from 144.
- `ruff check`, `ruff format --check` and `mypy --strict` clean.
- Manuscript: 24 pages, preflight clean, packet audit clean, 0 undefined references or citations.
- A full vintage build takes roughly 30 minutes on an unloaded machine, dominated by the eight
  bootstrap runs of 4,999 replications.

### Known limitation carried forward

Processed CSVs and dossier tables are written with the platform's line ending, so the same inputs
produce different bytes on Windows and Linux, and repeated runs can differ in the last floating-
point digit of a reduction. Neither affects any reported figure. Fixing it changes locked source,
so it waits for the next lock rather than being slipped in after results were seen.


## First live source freeze, and what it found — 2026-08-24

The publication source freeze ran for the first time. Continuous integration had been blocked
until the repository became public, and before that the local environment could not make outbound
requests, so this path had never executed end to end.

**All 63 official OECD and Eurostat queries fetched and verified.** The freeze then failed while
rebuilding the analytical panels, with:

```
ValueError: Eurostat semantic contract failed for 'geo': expected only 'UK', got [].
```

### What that revealed

The guard was right to stop, but it was describing the wrong problem. `validate_jsonstat_filters`
treated two very different situations identically:

- the response carries the **wrong** series — a substituted country or unit, which must never be
  canonicalised under the right name;
- the response is **correct and empty** — the requested country simply has no observations in that
  dataset.

The United Kingdom is the second case. It is configured in `decomposition_countries`, and Eurostat
returns a valid national-accounts payload for it that contains no data. Reporting that as a
semantic contract failure sent an operator looking for a broken query when the truth was a fact
about the source.

### Fixed

- `EurostatCoverageError`, a `ValueError` subclass, is raised when a requested dimension comes back
  empty. Callers that do not care about the distinction are unaffected, since it is still a
  `ValueError`.
- `build_decomposition_from_snapshots` catches it, leaves the country in the configured list, and
  lets the existing coverage report record the gap. The absence stays explicit, which is what
  `config/project.yml` asks for, rather than becoming a silent drop or a fatal error.
- A series where **every** requested country comes back empty now raises. That is a broken query
  rather than a coverage gap, and the two should not be confused in the other direction either.

### Validation

- **138 tests pass**, up from 134. Four cover the new distinction, including that a substituted
  country is still fatal and that the coverage error remains catchable as a `ValueError`.
- `ruff check`, `ruff format --check` and `mypy --strict` clean.


## Specification locked before the first source freeze — 2026-08-24

A specification lock was written immediately before the first publication source freeze was
requested. The artefact lives at `paper/specification_lock.json`, which is untracked, so its
digests are recorded here instead: this makes the lock auditable from the repository without
publishing the manuscript tree.

| Field | Value |
| --- | --- |
| Label | `pre-source-freeze-2026-08-24` |
| Package version | 0.7.1 |
| `analysis_code_sha256` (`src/wage_transmission`) | `7018759ff13c55949733b8ace9840ef2d2aa25fc24308f6771a53fd496ca6b20` |
| `config/publication.yml` | `aa745bf7d490cee24f679d7682fa51dbc8c657040d53b649c2db3d7d01a93554` |
| `config/project.yml` | `1586d98cf6598bc3f7ff302f6885c41e215e9365dbf466360def76c31443f848` |
| `config/models.yml` | `c3d925c1601d56fc467cb60a9cb6d6dbcbaef23ce1e0d4b18799e0a07582201a` |

### What this lock does and does not claim

The publication and project configuration digests are **byte-identical** to those in the original
`pre-source-freeze-2026-08-22` lock, and `git log` shows `config/publication.yml` unchanged since
the initial commit. The primary specification — GDP per person employed against real annual
wages, with the cumulative distributed-lag coefficient as the primary estimand — therefore
provably predates every result anyone has seen.

Two things this lock does **not** claim. `config/models.yml` differs from the original, because
0.7.0 added the `inference` block governing bootstrap replications; that is an addition of
resampling settings, not a change to any existing estimator parameter. And the analysis source
tree has changed substantially since 0.6.0, since 0.7.0 added the break test, the bootstrap bands
and the panel estimator.

Development results have been seen: the frozen Portugal reference extract, which the repository
labels a transcription rather than a publication-grade source, produces a cumulative transmission
estimate of -0.61 with a standard error of 0.71, no supported cointegration, and no detected
break. Those results informed nothing in the locked specification, which is unchanged, but the
honest statement is that this lock precedes the **publication vintage**, not that it precedes all
observation.


## Specification-lock machinery restored — 2026-08-24

Reverses the code removal in 0.7.0 while keeping the outcome that was actually wanted: the
manuscript trees stay out of version control, and the integrity machinery stays in the package.

The 0.7.0 change conflated two separable things. Keeping `paper/` and `papers/` off GitHub does
not require deleting the code that reads them, because the code is generic and the artefacts it
writes are just files on a path. Only the artefacts needed to leave.

### Restored

- `SpecificationLock`, `LockedFile`, `build_specification_lock`, `write_specification_lock`,
  `read_specification_lock` and `verify_specification_lock` in `wage_transmission.publication`.
- The `lock-publication-spec` CLI command and `--specification-lock` on
  `build-publication-dossier`.
- `tools/publication_report.py`, the paper-facing packet builder, and its tests.
- The analysis-lock half of `tools/integrity.py`, including `combined_sha256`, and its tests.
- `docs/specification_lock.md` and `docs/paper_generation.md`.
- The `spec-lock`, `paper-packet`, `paper-audit`, `paper2-lock` and `paper2-lock-verify` Makefile
  targets.

### Changed

`--specification-lock` is now **optional**. The lock artefact lives under the untracked `paper/`
tree, so a clean checkout does not carry one; requiring it would make the dossier unbuildable
anywhere but the author's machine. When a lock is supplied it is verified exactly as before, and
the dossier manifest records `specification_lock_verified` either way. A dossier without a
verified lock is still fully auditable — every input and output is hashed — it simply is not
evidence of a pre-results commitment, and the manifest no longer lets those two states be
confused.

### What this arrangement costs

CI cannot enforce the lock, because the artefact is not in the repository. Verifying a lock
before promoting a run is a manual discipline. That is the price of keeping the manuscripts
private, and it is a reasonable one: the lock's purpose is to make specification drift visible to
the author, not to gate a public build.

### Validation

- **134 tests pass**, up from 122; the twelve restored tests cover the lock machinery and the
  paper packet.
- `ruff check`, `ruff format --check` and `mypy --strict` clean.
- The Paper 2 analysis lock verifies against the local untracked artefact.


## 0.7.1 — 2026-08-24

A patch release. No estimator or public interface changes; the package API is identical to
0.7.0.

### Fixed

- Three wage-distribution tests read the exploratory panel under `results/`, which is not
  tracked. They passed locally and failed on every clean checkout. They now skip with an
  explicit reason when the panel is absent, and four synthetic tests were added so the
  estimator stays covered where the data does not exist. This was the first defect caught by
  continuous integration, which had been blocked until the repository became public.
- Both notebook writers emit LF explicitly. `nbformat` otherwise writes the platform line
  ending, and notebook bytes are recorded in the release manifest.

### Changed

- The four notebooks are rebuilt from `tools/build_notebooks.py`, run, and committed with their
  outputs. Two of them previously could not execute at all outside the author's machine.
  Notebooks 01 and 02 now run on the tracked Portugal reference extract; 03 and 04 fall back to
  clearly labelled simulated frames when the processed panels are absent.
- Zenodo archiving moves to the GitHub integration now that the repository is public, and
  `.zenodo.json` declares open access rather than restricted.

### Notes

Continuous integration passes for the first time in this repository's history: build, lint,
format, types, and the test suite on Python 3.11, 3.12 and 3.13.

The OECD median-earnings dataflow identifier remains `status: unverified` and must be confirmed
before a live source freeze.

### Validation

- 122 tests pass; coverage 71.5% against a 65% floor.
- `ruff check`, `ruff format --check` and `mypy --strict` clean, locally and in CI.
- Release manifest and the exported archive of the tag both verify.


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
