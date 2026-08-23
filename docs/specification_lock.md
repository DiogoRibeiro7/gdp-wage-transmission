# Pre-results specification lock

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
