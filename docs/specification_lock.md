# Pre-results specification lock
> **Where the lock file lives.** The lock *machinery* is part of this repository; the lock
> *artefact* is not. `paper/` and `papers/` are untracked, so `paper/specification_lock.json`
> stays on the machine that wrote it and is never published. Two consequences follow: the lock
> is a **local** gate rather than one CI can enforce, and a clean checkout has no lock to verify,
> which is why `build-publication-dossier` treats `--specification-lock` as optional and records
> `specification_lock_verified` in its manifest either way. A dossier built without a lock is
> still fully auditable; it simply is not evidence of a pre-results commitment.


The publication workflow separates **analysis choices fixed before promotion of a live source
freeze** from results generated afterwards. This is intended to make specification changes visible
rather than pretending that every model in the repository has equal evidential status.

## Locked objects

`paper/specification_lock.json` binds four things:

1. `config/project.yml` — sample scope, countries, years and economic definitions;
2. `config/models.yml` — lag choices and reliability thresholds;
3. `config/publication.yml` — hierarchy of estimands and interpretation policy;
4. the complete `src/wage_transmission/**/*.py` analysis source tree.

The lock also records the package version that created it. The source-tree digest includes each
Python file's relative path and bytes, so renaming, adding, deleting or editing estimator code changes
the digest.

The publication workflow fails if any locked hash changes. A genuinely necessary post-lock code or
specification correction therefore requires a new lock and should be described as such in the
changelog or paper revision history.

## Registered locks

The lock artefact stays outside version control, so its digests are recorded here instead. A
reader can recompute every one of them from a checkout at the tagged commit and confirm that the
specification was fixed *before* the source snapshot it was used to analyse:

```bash
poetry run python - <<'EOF'
from pathlib import Path
from wage_transmission.publication import build_specification_lock
lock = build_specification_lock(
    project_config=Path("config/project.yml"),
    models_config=Path("config/models.yml"),
    publication_config=Path("config/publication.yml"),
    label="pre-source-freeze-2026-08-25-v0.8.0",
)
print(lock.analysis_code_sha256)
EOF
```

| Lock label | Package | Analysis-tree SHA-256 | `models.yml` SHA-256 |
| --- | --- | --- | --- |
| `pre-source-freeze-2026-08-24` | 0.7.1 | `be29de1c5857f7ddf513e7ba32d3b1b2b26a124d04c02a3b657db86a3e8dd850` | `c3d925c1601d56fc467cb60a9cb6d6dbcbaef23ce1e0d4b18799e0a07582201a` |
| `pre-source-freeze-2026-08-25-v0.8.0` | 0.8.0 | `0b14fbe21152bf884f948cefb71ca225d8b821de67495c43e7ec96ee6602b559` | `a47f74591aaa43a897055b77e3b7e84b8fea84c00d199bd7f9a5c6ffb3687bf8` |

`config/project.yml` and `config/publication.yml` are unchanged between the two locks
(`1586d98cf6598bc3f7ff302f6885c41e215e9365dbf466360def76c31443f848` and
`aa745bf7d490cee24f679d7682fa51dbc8c657040d53b649c2db3d7d01a93554`).

### What the v0.8.0 lock is, and is not

The v0.8.0 specification -- the dynamic panel, its bias correction, its bootstrap plan and its
reporting gates -- was written and locked before the 2026-08-25 source snapshot was retrieved. The
commit that carries this table precedes the commit that carries the snapshot, so the ordering is
checkable rather than asserted.

That makes the follow-up analysis **prospectively locked**. It does not make it confirmatory, and it
does not make it out-of-sample evidence. The specification was motivated by results already seen in
v0.7.1, on a sample that overlaps this one almost completely; a new data vintage does not erase that
history. The correct description is a prospectively locked follow-up analysis of a previously
analysed sample.

### v0.8.1 deliberately has no lock of its own

v0.8.1 corrects the manuscript and the formatter. It changes no file under `src/wage_transmission`
and no configuration file, so the analysis-tree digest is unchanged at
`0b14fbe21152bf884f948cefb71ca225d8b821de67495c43e7ec96ee6602b559` and no estimate moves.

No new lock was written, and that is deliberate. A lock is evidence of a commitment made *before*
results were seen; one written now would be evidence of nothing. The v0.8.0 lock remains the
record of what produced the estimates. It binds the package version, so it verifies against a
v0.8.0 checkout and not against a later one — which is the behaviour a version-binding lock should
have, and the reason a reproduction should check out the tag rather than the branch.

## Primary estimand

The pre-specified primary Portugal specification pairs annual real average wages with GDP per person
employed. The primary inferential quantity is the cumulative coefficient from the short-run
distributed-lag model:

\[
\Theta = \sum_{j=0}^{2}\beta_j.
\]

Its uncertainty uses the full HAC covariance matrix of the current and lagged productivity-growth
coefficients.

GDP per hour is the secondary productivity definition. It is important economic evidence, but it is
not allowed to displace the denominator-matched annual specification merely because it produces a
more attractive coefficient.

## Dynamic panel (locked for v0.8.0)

The panel estimand is the *same* cumulative multiplier, from the same dynamic structure:

\[
\Delta\log w_{it} = \alpha_i + \lambda_t + \sum_{j=0}^{2}\beta_j\,\Delta\log p_{i,t-j}
+ \gamma\,\Delta\log w_{i,t-1} + u_{it},
\qquad
\Theta_{\mathrm{panel}} = \frac{\beta_0+\beta_1+\beta_2}{1-\gamma}.
\]

Frozen before retrieval, in `config/models.yml` under `dynamic_panel`:

- **Primary** specification carries country *and* year effects; the **sensitivity** drops the year
  effects. The two drivers are estimated separately and never pooled.
- Estimation is bias-corrected LSDV. Uncorrected LSDV is reported beside it to show the size of the
  correction, and only the corrected estimator is treated as substantive.
- Inference is a circular moving-block bootstrap over time that resamples the complete
  thirteen-country cross-section jointly, with block length four and 4,999 replications; block
  lengths three and five are frozen sensitivity checks. Lags are rebuilt after concatenation and the
  corrected model is re-estimated in every replication, so the interval is a percentile interval for
  the nonlinear multiplier itself.
- Driscoll--Kraay standard errors are a **secondary diagnostic** only. Their justification is
  asymptotic in the time dimension, and roughly 28 effective years is not enough for them to replace
  the bootstrap.
- Reporting gates: |gamma| < 1, at least 25 effective years, a finite multiplier in at least 95% of
  replications, at least 95% estimator convergence, no rank deficiency after the fixed effects, and
  all 4,999 replications requested with the completed count reported. **A primary result that fails
  any gate is ineligible** and is labelled as such rather than dropped.

The bias correction addresses dynamic fixed-effects bias. It does not solve contemporaneous
endogeneity between productivity and wages; the coefficient remains a reduced-form conditional
association.

## Reliability-gated models

The repository still estimates ECM, time-varying state-space slopes, endogenous break regimes,
local projections and asymmetric responses. They are not co-equal headline estimands.

- ECM long-run elasticities require the pre-specified cointegration gate.
- The latest state-space slope requires the pre-specified precision gate.
- Break-regime interpretation requires every estimated segment to meet the minimum-length gate.
- Asymmetry requires enough positive and negative driver changes.
- Only local-projection horizons meeting the effective-sample threshold are publication-eligible.

The generated `reliability_gates.csv` records those decisions mechanically.

## Cross-country hierarchy

Country-specific distributed-lag estimates with HAC uncertainty are the primary cross-country
object. Fixed/random-effects summaries are secondary summaries. The publication dossier reports the
random-effects estimate together with I-squared, but the country table must remain available so
heterogeneity is visible.

## Causal language

No reduced-form estimate in this workflow is authorized as causal. The generated publication
manifest contains:

```text
causal_claims_authorized = false
```

A causal claim would require a separate identification design and a new specification lock.
