# Paper generation from the locked dossier
> **Where the lock file lives.** The lock *machinery* is part of this repository; the lock
> *artefact* is not. `paper/` and `papers/` are untracked, so `paper/specification_lock.json`
> stays on the machine that wrote it and is never published. Two consequences follow: the lock
> is a **local** gate rather than one CI can enforce, and a clean checkout has no lock to verify,
> which is why `build-publication-dossier` treats `--specification-lock` as optional and records
> `specification_lock_verified` in its manifest either way. A dossier built without a lock is
> still fully auditable; it simply is not evidence of a pre-results commitment.


The paper layer is intentionally outside `src/wage_transmission`. The v0.6 specification
lock hashes the complete analysis package and package version, so publication formatting must
not mutate that locked analysis code after the pre-results lock was created.

## Contract

`tools/publication_report.py` is a formatter, not an estimator. It is allowed to read only the
machine-generated publication dossier and transform those values into LaTeX/Markdown fragments.
It cannot promote an ineligible supporting model into the main result and it never authorizes
causal language.

The required sequence is:

```bash
poetry run wage-transmission build-publication-dossier \
  --results-root results/vintages/<VINTAGE> \
  --specification-lock paper/specification_lock.json \
  --publication-config config/publication.yml \
  --output results/vintages/<VINTAGE>/publication_dossier

poetry run python tools/publication_report.py build \
  --dossier results/vintages/<VINTAGE>/publication_dossier \
  --paper-dir paper

poetry run python tools/publication_report.py audit \
  --paper-dir paper \
  --manifest paper/generated/paper_packet_manifest.json
```

The first command verifies the locked empirical specification. The second verifies the dossier
hashes before writing report fragments. The third verifies the generated fragment hashes and
fails if a hand-written `table`, `tabular`, or `longtable` environment appears in a non-generated
paper source file.

## Generated files

A successful build creates:

- `paper/generated/results_primary.tex`
- `paper/generated/table_core_estimates.tex`
- `paper/generated/table_reliability.tex`
- `paper/generated/table_cross_country.tex`
- `paper/generated/table_decomposition.tex` when decomposition evidence exists
- `paper/generated/results_summary.md`
- `paper/generated/paper_packet_manifest.json`

The generated manifest binds the dossier manifest and every report fragment with SHA-256.

## Reliability behaviour

Supporting-model results are always visible, but the report labels them `eligible` or
`not eligible` from `reliability_gates.csv`. A non-eligible ECM, state-space, break,
asymmetry, or local-projection result cannot be silently omitted or described as established
evidence.

No empirical coefficient should be typed manually into `paper/main.tex`. The paper source
contains only conceptual text and `\input{generated/...}` directives for empirical results.
