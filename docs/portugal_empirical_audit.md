# Portugal empirical audit — v0.2

## Scope

This document records the **first frozen empirical run** of the repository. It is a diagnostic release, not a final paper result.

The run uses Portugal, 1995–2025, with:

- OECD average annual wage at constant 2025 prices, PPP-converted USD;
- OECD Productivity Database v2.0 GDP per hour worked, PPP-converted USD/hour.

The frozen input is `data/reference/portugal_oecd_1995_2025.csv` with SHA-256:

```text
d52ed713593550b8625fc0e291d006f25b3efd71398f10860cf13d68c4d2646a
```

The reference CSV is a transcription of the official OECD Data Explorer snapshot visible on 2026-08-22 because the execution environment could not make Python HTTP requests. It is **not** an untouched SDMX payload. Publication work must regenerate and archive the raw OECD response.

## Denominator warning

The current frozen specification compares an **annual wage** concept with **GDP per hour worked**. That is a useful hourly-productivity transmission specification, but it is not a denominator-matched wage/productivity pair.

For that reason v0.2 adds a separate OECD downloader for GDP per person employed (`GDPEMP`) and preserves it as `productivity_per_worker`. The intended robustness specification is:

\[
\text{average annual real wage}
\quad\leftrightarrow\quad
\text{real GDP per employed person}.
\]

That series is not fabricated into the frozen reference snapshot. It must be downloaded from the official API in a network-enabled environment.

## Descriptive evidence

Over the full 1995–2025 window:

| Quantity | Change |
|---|---:|
| Real average annual wage | +31.36% |
| GDP per hour worked | +34.57% |
| Annualised real wage growth | +0.91% |
| Annualised GDP/hour growth | +0.99% |
| Correlation of annual log growth rates | 0.087 |

The similar full-period cumulative growth rates hide substantial subperiod divergence. Using the **estimated exploratory break dates** as descriptive boundaries:

| Window | Real wage | GDP/hour | Wage minus productivity |
|---|---:|---:|---:|
| 1995–2004 | +13.11% | +13.29% | -0.18 pp |
| 2004–2013 | -3.98% | +12.71% | -16.69 pp |
| 2013–2025 | +20.94% | +5.39% | +15.56 pp |

These windows are descriptive. They do not establish that a structural regime changed exactly in 2004 or 2013.

## Integration and long-run relation

The Engle–Granger statistic is:

\[
-2.233,
\]

with

\[
p=0.407.
\]

The 5% critical value is approximately \(-3.547\). The current sample therefore **does not support cointegration at 5%**.

The estimated ECM long-run elasticity, approximately \(0.375\), is consequently retained as a conditional model output but is explicitly marked:

```text
unsupported_without_cointegration
```

It must not be quoted as an established long-run wage/productivity elasticity.

## Short-run distributed-lag model

With two productivity-growth lags and one wage-growth lag, the cumulative productivity coefficient is approximately:

\[
-0.607.
\]

The first productivity lag is negative and individually significant in the current HAC regression, but the model has only 28 effective observations and \(R^2\approx0.142\). This is a reduced-form association, not a causal productivity shock estimate.

## Structural-break search

The dynamic-programming/BIC segmentation selects candidate boundaries at **2004** and **2013**. The resulting segment sizes are 8, 9 and 13 annual growth observations.

Because the smallest segment is below the configured interpretation threshold of 10 observations, the run labels the result:

```text
small_regime_segments
```

The break search is not a formal Bai–Perron test and does not provide Bai–Perron confidence intervals or critical-value inference.

## Time-varying elasticity

The state-space model converges. Its latest filtered elasticity is approximately:

\[
\widehat\beta_{2025}=0.196,
\]

with approximate standard error

\[
SE=0.424.
\]

Hence the normal-approximation 95% interval is roughly

\[
[-0.635,\ 1.028].
\]

The latest coefficient is therefore **not distinguishable from zero** at the configured 1.96 z threshold. The repository labels it `latest_slope_imprecise` rather than narrating the point estimate as a substantive decline or recovery.

## Local projections

The effective sample falls from 28 observations at horizon 0 to 20 at horizon 8. With the pre-specified minimum of 25 observations:

- horizons 0–3 are retained as the relatively supported descriptive range;
- horizons 4–8 are labelled exploratory.

Some long-horizon confidence intervals exclude zero, but those estimates are based on only 20–24 observations and are not independently identified shocks. They should not be promoted above the short-horizon evidence merely because they look statistically sharper.

## Asymmetry

There are only:

- 23 positive productivity changes;
- 5 negative productivity changes;
- 2 changes that are effectively zero.

The configured minimum is eight observations of each sign. The positive-versus-negative transmission model is therefore labelled:

```text
underpowered_shock_balance
```

Its large asymmetric cumulative coefficients are not treated as reliable evidence.

## Current conclusion

The first run does **not** support a simple statement that annual wage growth mechanically follows annual hourly-productivity growth in Portugal. The full-period levels grow by broadly similar amounts, but annual growth correlation is weak and subperiod paths differ considerably.

More importantly, the current 31-year annual sample is too small to justify strong claims from the most flexible models. The next empirical priority is therefore not to add another estimator. It is to:

1. retrieve and archive the raw official OECD responses;
2. run the denominator-matched GDP-per-employed-person specification;
3. construct the national-accounts decomposition of GDP, labour share, employment and prices;
4. extend the same pre-specified analysis to the cross-country panel;
5. use the larger panel to distinguish Portugal-specific behaviour from common macroeconomic dynamics.
