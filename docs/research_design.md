# Research design

## Primary estimand

The central quantity is the elasticity of real wages with respect to labour productivity:

\[
\beta_t = \frac{\partial \log w_t}{\partial \log p_t}.
\]

The project treats \(\beta_t\) as an empirical object rather than assuming one-for-one transmission.

## Primary hypotheses

### H1 — incomplete transmission

The long-run elasticity is positive but may be below one:

\[
0 < \theta < 1.
\]

This is not imposed during estimation.

### H2 — parameter instability

The wage-productivity relation is not necessarily constant over the sample. Break dates are estimated endogenously and a time-varying coefficient model provides a continuous alternative.

### H3 — asymmetric transmission

Positive and negative productivity changes may have different wage coefficients:

\[
\beta_+ \neq \beta_-.
\]

A particularly relevant empirical possibility is that wage losses during contractions are larger in magnitude than wage gains during expansions.

### H4 — distribution within labour income

Mean compensation and median earnings need not have the same productivity elasticity. A larger mean-wage elasticity than median-wage elasticity would be consistent with unequal transmission within labour income, though causal attribution requires additional evidence.

## Denominator discipline

The repository treats productivity definitions as separate empirical objects rather than aliases.

- GDP per hour worked is the primary measure of hourly labour productivity.
- GDP per person employed is the denominator-matched annual robustness measure for average annual wages.
- Aggregate real GDP is a macro-output robustness driver, not a labour-productivity substitute.

A result is never described generically as the “GDP–wage elasticity” without naming the denominator used on the GDP/productivity side.

## Pre-specified interpretation gates

Flexible models can look persuasive in short annual samples. The pipeline therefore reports machine-readable reliability flags alongside coefficients. The current defaults require:

- Engle–Granger p-value below 0.05 before an ECM long-run elasticity is treated as supported;
- at least 8 positive and 8 negative driver changes before interpreting asymmetry;
- at least 25 effective observations at a local-projection horizon for the supported descriptive range;
- at least 10 observations in every estimated break segment for regime interpretation;
- absolute state-space z-score of at least 1.96 before the latest filtered elasticity is described as distinguishable from zero.

These are interpretation rules, not guarantees of identification or truth. They are intended to prevent specification flexibility from silently outrunning the information in the sample.

## Sequence of inference

1. Audit units, coverage, revisions and missingness.
2. Plot levels and growth rates.
3. Test integration properties with ADF and KPSS diagnostics.
4. Test bivariate cointegration.
5. Estimate a growth distributed-lag model.
6. Estimate an ECM if the long-run relationship is empirically defensible.
7. Search for unknown structural breaks.
8. Estimate a state-space time-varying elasticity.
9. Estimate local-projection dynamic responses.
10. Test asymmetric responses.
11. Repeat across alternative wage and productivity definitions.
12. Run the Eurostat accounting decomposition as a separate compensation concept.
13. Extend the harmonised OECD design country by country.
14. Summarise country estimates only after inspecting heterogeneity.

## Interpretation discipline

No reduced-form coefficient is described as causal merely because one variable precedes another. A causal design requires an explicit source of exogenous productivity variation or another defensible identification strategy.

## Accounting-identification boundary

The labour-share decomposition is an **identity**, not an identified causal model:

\[
\Delta\log w^{D1}_t = \Delta\log Y_t + \Delta\log s_{L,t} - \Delta\log N_t + (\pi^Y_t-\pi^C_t).
\]

It shows which accounting margins coincide with changes in real compensation per employee. It does not, by itself, explain why the labour share, employment or relative prices changed. Causal interpretation of those components requires a separate design.

## Cross-country hierarchy

The primary cross-country object is a table of separately estimated national coefficients with HAC uncertainty. A fixed/random-effects meta-analytic summary is secondary. The repository reports Cochran's Q and I-squared so a pooled-looking number cannot be presented without the corresponding heterogeneity diagnostic.

## Pre-results specification lock

Before a live official source vintage is promoted into publication evidence, the repository locks
`project.yml`, `models.yml`, `publication.yml`, the package version and the complete Python analysis
source tree. The primary estimand is therefore fixed before the publication source-freeze result is
observed. The publication hierarchy is recorded in `config/publication.yml`.

The denominator-matched GDP-per-employed-person specification is primary; GDP per hour is the
secondary productivity definition. The cumulative distributed-lag coefficient is the primary
inferential estimand. Flexible models remain reliability-gated supporting analyses.
