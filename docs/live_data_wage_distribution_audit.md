# Exploratory Portugal wage-distribution audit, 2002–2024

## Status

This layer is **exploratory and not publication-eligible**. It is intentionally implemented under
`tools/` and `results/exploratory_live/`, outside the preregistered analysis source tree.

The goal is to test a mechanism that aggregate labour compensation cannot identify: whether the
mean employee gain can remain healthy while the typical or lower-paid worker falls behind.

## Population and wage concept

The primary source is the official **Quadros de Pessoal** chronological series from GEP/MTSSS
(and DGCP/MTSSS in the latest release). The observations refer to mainland Portugal (`Continente`)
and to employees who:

- work full time;
- received complete remuneration in the reference period;
- are observed in October.

The wage concept is **monthly gain (`ganho mensal`)**, not base pay, net household income, OECD
annual-average wages, or national-accounts D.1 compensation per employee. Those concepts are not
merged as though they were interchangeable.

Two official chronological releases are transcribed separately:

- 2002–2014 historical table: GEP/MTSSS, *Séries Cronológicas Quadros de Pessoal 2002–2014*;
- 2014–2024 current table: DGCP/MTSSS, *Séries Cronológicas Quadros de Pessoal 2014–2024*.

The duplicated 2014 bridge year is treated as a data contract. Mean gain, median gain, TCO count,
and every decile-average gain must match exactly before the series is stitched.

## Price treatment

Because the remuneration observation is an October cross-section, nominal monthly gains are
deflated with **October HICP**, not the annual-average HICP used in the national-accounts
accounting decomposition. The HICP series is the already-frozen exploratory Eurostat-through-FRED
monthly index, re-referenced to 2025=100.

For nominal gain \(g_t\), the exploratory real measure is

\[
  g_t^{2025} = g_t\frac{100}{HICP_{t,Oct}}.
\]

## Main result

Between 2002 and 2024:

| Measure | Nominal growth | Real growth (October HICP) |
| --- | ---: | ---: |
| Mean gain | +93.10% | **+25.01%** |
| Median gain | +102.21% | **+30.90%** |
| D1 average gain | +139.72% | **+55.19%** |
| D5 average gain | +104.68% | **+32.50%** |
| D10 average gain | +75.19% | **+13.41%** |

The distribution ratios move in the same direction:

\[
\frac{D10}{D1}: 6.83 \rightarrow 4.99,
\]

\[
\frac{D10}{D5}: 4.36 \rightarrow 3.73,
\]

and

\[
\frac{\text{mean}}{\text{median}}: 1.392 \rightarrow 1.329.
\]

Equivalently, the median rises from 71.86% of the mean to 75.25%.

This is not consistent with a simple post-2002 story in which the aggregate mean was increasingly
pulled away from the typical worker. Within this covered employee population, the long-run pattern
is **distributional compression**, with particularly strong gains near the bottom.

## Timing

The compression is not uniform. Real D1 and D10 gains both rise modestly between 2002 and 2008,
and the D10/D1 ratio actually increases from 6.83 to 6.99. Most of the compression occurs later:

| Period | Mean real gain | Median real gain | D1 real gain | D10 real gain | D10/D1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2002→2008 | +5.94% | +5.36% | +5.32% | +7.70% | 6.83→6.99 |
| 2008→2014 | +0.99% | +1.74% | +11.15% | −1.93% | 6.99→6.17 |
| 2014→2019 | +5.95% | +8.50% | +13.66% | +1.25% | 6.17→5.49 |
| 2019→2024 | +10.27% | +12.55% | +16.64% | +6.05% | 5.49→4.99 |

These are descriptive windows, not estimated structural regimes.

## Connection back to productivity

The existing exploratory OECD GDP-per-employed-person panel overlaps this wage-distribution panel
from 2002 through 2023. Comparing endpoints only, without treating the source concepts as
identical, gives:

| Measure, 2002→2023 | Real growth | Difference from GDP/person employed |
| --- | ---: | ---: |
| GDP per employed person | **+19.12%** | — |
| Mean monthly gain | **+18.89%** | −0.22 pp |
| Median monthly gain | **+24.09%** | +4.98 pp |
| D1 average monthly gain | **+47.12%** | +28.00 pp |
| D5 average monthly gain | **+25.48%** | +6.37 pp |
| D10 average monthly gain | **+8.41%** | −10.71 pp |

Thus aggregate endpoint co-movement can be almost exact while the distributional incidence differs
substantially. The mean gain and GDP/person employed grow by nearly the same amount, but that fact
does not imply a one-for-one gain for every worker or wage position. This endpoint comparison is
descriptive and is stored separately from the locked distributed-lag result.

## Interpretation boundary

The result answers a narrower question than household inequality:

- it excludes self-employed workers;
- it is mainland Portugal, not a fully harmonised national population;
- it covers full-time employees with complete October remuneration;
- monthly `ganho` includes components beyond base pay;
- decile values are **mean gain within each decile**, not decile thresholds;
- the panel does not identify causal effects of the minimum wage, collective bargaining, taxes,
  composition changes, or productivity.

The result therefore should not be presented as “inequality in Portugal fell” without qualification.
It says that **monthly employee gain dispersion within the covered Quadros de Pessoal population
compressed substantially from 2002 to 2024**.

## Files

- `results/exploratory_live/portugal_qp_distribution_historical_2002_2014.csv`
- `results/exploratory_live/portugal_qp_distribution_current_2014_2024.csv`
- `results/exploratory_live/wage_distribution/portugal_wage_distribution_2002_2024.csv`
- `results/exploratory_live/wage_distribution/portugal_wage_distribution_growth_2002_2024.csv`
- `results/exploratory_live/wage_distribution/portugal_wage_distribution_summary_2002_2024.json`
- `results/exploratory_live/wage_distribution/WAGE_DISTRIBUTION_PROVENANCE.json`

The provenance file hashes both transcribed official tables, the HICP input, and every generated
machine-readable output. None of these values are promoted into the locked publication dossier.
