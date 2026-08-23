# Portugal endpoint labour-share decomposition: exploratory audit

## Status

This document records a **non-publication exploratory endpoint decomposition** for Portugal. It does
not replace the locked publication workflow. The statistical package remains at v0.6.0 and no file
under `src/wage_transmission` is changed by this exercise.

The publication specification requires Eurostat national-accounts employees in the domestic concept
(`SAL_DC`). The current indexed-web route exposes the required GDP, D.1 compensation, GDP deflator
and HICP endpoints, but it does not expose the 1996 Portugal `SAL_DC` level with enough provenance to
promote it into the locked decomposition. The main decomposition is therefore deliberately left
**incomplete** at the employment term.

A second calculation uses Labour Force Survey (LFS) employees only as a named denominator
sensitivity. It is useful for understanding magnitude but is conceptually different from `SAL_DC`
and is explicitly `publication_eligible: false`.

## Why the interval is 1996–2025

The harmonised consumer-price series used by the locked accounting identity begins in January 1996.
Using 1996 as the initial endpoint allows the decomposition to retain HICP rather than silently
substituting a national CPI. The 2025 HICP index is re-referenced to 2025=100. Annual endpoint values
were reconstructed as the arithmetic average of the twelve published monthly HICP observations.

Because the identity is in log differences, a cumulative two-endpoint decomposition is exact:

\[
\Delta\log w^{D1}
=
\Delta\log Y
+
\Delta\log s_L
-
\Delta\log N
+
\left(\Delta\log P_Y-\Delta\log P_C\right),
\]

where

\[
s_L = \frac{D1}{GDP}.
\]

This telescoping property means every annual observation is not required for the **full-period
contribution totals**. It does *not* mean that a two-endpoint exercise can recover the timing of those
contributions.

## Endpoint inputs

| Series | 1996 | 2025 | Role |
|---|---:|---:|---|
| Nominal GDP, million euro | 94,351.591 | 306,765.485 | National-accounts aggregate |
| D.1 compensation of employees, million euro | 44,760.176 | 147,620.6447 | National-accounts labour compensation |
| GDP deflator, 2021=1 | 0.571002 | 1.233788 | Output-price deflator |
| HICP annual average, 2025=100 | 53.5883 | 100.0008 | Consumer-price deflator |
| LFS employees, thousand | 3,181.7 | 4,474.2 | **Sensitivity only** |

GDP, D.1 and the GDP deflator are current INE/PORDATA values. The HICP endpoint averages are
reconstructed from Eurostat monthly values distributed through FRED. The LFS employee series is from
INE/PORDATA and must not be confused with national-accounts `SAL_DC`.

## Locked decomposition: employee-independent terms

The components that do not depend on the missing `SAL_DC` endpoint are:

| Component | 1996→2025 contribution |
|---|---:|
| Real GDP | **+40.86 log points** |
| Raw D.1/GDP labour share | **+1.43 log points** |
| Employment (`SAL_DC`) | **not available** |
| GDP-deflator minus HICP inflation | **+14.66 log points** |

The raw D.1 compensation share of GDP changes from

\[
47.44\% \rightarrow 48.12\%,
\]

an increase of approximately **0.68 percentage points**. Real GDP itself rises by about **50.47%**
between the two endpoints.

This already rules out one simplistic endpoint explanation: on this unadjusted D.1/GDP measure,
Portugal did **not** experience a collapse in labour's aggregate income share between 1996 and 2025.
That statement is intentionally narrower than saying that wage earners captured all productivity
improvements. The measure includes employers' social contributions, ignores how compensation is
distributed among employees, and does not impute labour income to the self-employed.

## LFS-denominator sensitivity

If the employee term is filled with the LFS employee series solely as a sensitivity, the accounting
identity becomes:

| Component | Log-point contribution |
|---|---:|
| Real GDP | +40.86 |
| Raw D.1/GDP labour share | +1.43 |
| LFS employee growth | **−34.09** |
| Relative prices | +14.66 |
| **Real D.1 compensation per LFS employee** | **+22.86** |

LFS employee counts rise by about **40.62%** over the interval. The resulting +22.86 log-point change
corresponds to approximately **+25.68%** in the level of HICP-deflated D.1 compensation per LFS
employee. The numerical identity residual is about `1e-15`.

This sensitivity suggests an economically useful mechanism to investigate: a large part of aggregate
real-output expansion coexisted with a substantial increase in the number of employees, so aggregate
income growth need not translate one-for-one into compensation *per employee*. It also shows that the
relative movement of the GDP deflator and consumer prices matters for the purchasing-power measure.

It does **not** establish that employment growth caused weaker wage growth, nor can its coefficient
magnitudes be promoted to the paper because the denominator is not the locked national-accounts
concept.

## Why LFS employees cannot replace `SAL_DC`

The locked denominator is Eurostat `nama_10_pe`, `THS_PER`, `SAL_DC`: employees under the domestic
national-accounts concept. That concept covers employment in resident production units and is
consistent with GDP and other national-accounts aggregates.

The Labour Force Survey instead covers resident households and is principally aligned with the
national concept. Cross-border workers and other coverage adjustments create a conceptual bridge
between the two systems. The LFS series is therefore retained only as a sensitivity and never renamed
or presented as `SAL_DC`.

## Interpretation boundary

The strongest conclusion this exploratory endpoint exercise supports is:

> Portugal's raw employee-compensation share of GDP is slightly higher in 2025 than in 1996, so the
> long-run endpoint gap between aggregate output growth and per-employee purchasing power cannot be
> attributed simply to a falling raw labour share. Employee-count growth and the output-price versus
> consumer-price wedge are quantitatively important in the LFS-denominator sensitivity.

That conclusion remains descriptive. Endpoint decomposition hides the path through the euro adoption,
financial crisis, sovereign-debt adjustment, pandemic and subsequent inflation episode. A full annual
series is still needed to say **when** each channel mattered.

## Promotion condition

The main decomposition becomes publication-eligible only when the official source-freeze workflow
provides the untouched Eurostat/official payloads, including Portugal `SAL_DC` for the complete common
sample, and the strict source audit passes. At that point the existing locked decomposition code can be
run without changing the accounting specification.
