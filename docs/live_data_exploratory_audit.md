# Portugal live-data exploratory audit

## Status

This audit is a **non-publication exploratory check**. It uses values visible in current OECD Data Explorer indexed output on 2026-08-23, while keeping the v0.6 locked statistical specification unchanged. It does **not** satisfy the raw SDMX source-freeze requirement, so none of the estimates in this document may be promoted into `paper/generated/` or the publication dossier.

The common sample available through the indexed official tables is 1995–2023 (`n = 29` level observations).

## Primary locked estimand

The pre-specified primary model is the distributed-lag wage-growth regression with GDP per person employed as the driver:

\[
\Delta \log w_t = \alpha + \sum_{j=0}^{2}\beta_j\Delta\log p_{t-j}
+ \gamma\Delta\log w_{t-1}+\varepsilon_t,
\]

with HAC(2) covariance. The locked primary estimand is

\[
\Theta=\beta_0+\beta_1+\beta_2.
\]

On the 1995–2023 exploratory series:

| Driver | Total driver growth | Annual growth correlation with wages | \(\hat\Theta\) | HAC SE | 95% CI | p-value |
|---|---:|---:|---:|---:|---:|---:|
| GDP per person employed | 29.26% | 0.129 | 0.222 | 0.543 | [-0.844, 1.287] | 0.684 |
| GDP per hour worked | 31.11% | 0.016 | -0.698 | 0.780 | [-2.227, 0.831] | 0.371 |

Real annual wages rose 23.82% over the same common sample.

The main point is therefore not the sign of either point estimate. Both intervals are very wide and both estimates are statistically compatible with zero. Switching from GDP/hour to the denominator-matched GDP/person-employed series does not produce evidence of a strong short-run wage-transmission coefficient in this sample.

## Reliability gates

Engle–Granger cointegration is unsupported in both specifications:

- GDP/person employed: `p = 0.565`;
- GDP/hour: `p = 0.562`.

Accordingly, the ECM long-run coefficients remain **not eligible** for substantive interpretation. The latest state-space slopes are also not distinguishable from zero at the configured threshold. Only local-projection horizons 0 and 1 meet the minimum effective sample size in this shorter common sample, and the asymmetry comparison remains underpowered because the rarer productivity-shock sign has only five observations.

## Interpretation boundary

This exploratory result is useful because it tests the locked model before the publication freeze without changing the specification in response to the result. It is not sufficient for the paper because the values were transcribed from official indexed tables rather than reconstructed from untouched source-response bytes.

The correct next promotion condition remains:

\[
\text{verified source freeze}
\rightarrow
\text{offline rebuild}
\rightarrow
\text{locked model rerun}
\rightarrow
\text{publication dossier}.
\]
