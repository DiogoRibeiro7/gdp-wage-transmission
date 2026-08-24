# Model notes

## Distributed lag

\[
\Delta \log w_t = \alpha + \sum_{j=0}^{q}\beta_j \Delta\log p_{t-j}
+ \sum_{k=1}^{r}\gamma_k\Delta\log w_{t-k} + \varepsilon_t.
\]

The cumulative short-run transmission is \(\sum_j \beta_j\). Its standard error uses the full HAC covariance matrix of the productivity-lag coefficients, including their covariances; it is not obtained by adding individual standard errors.

## Error-correction model

First estimate the long-run relation

\[
\log w_t = a + \theta \log p_t + u_t.
\]

Then estimate

\[
\Delta \log w_t = \lambda u_{t-1}
+ \sum_k \phi_k\Delta\log w_{t-k}
+ \sum_j \beta_j\Delta\log p_{t-j} + \varepsilon_t.
\]

A stable equilibrium-adjustment interpretation generally requires \(\lambda < 0\).

## Structural breaks

The current implementation uses dynamic programming to minimise total piecewise OLS RSS and selects the number of segments by BIC. It intentionally does not call itself a Bai–Perron test because the inferential apparatus for Bai–Perron critical values is not implemented yet.

## State-space elasticity

\[
\Delta\log w_t = \alpha + \beta_t\Delta\log p_t + \varepsilon_t,
\]

\[
\beta_t = \beta_{t-1} + \eta_t.
\]

The observation and state variances are estimated by maximum likelihood and the coefficient path is filtered by a Kalman recursion.

## Local projections

For each horizon \(h\):

\[
\log w_{t+h} - \log w_{t-1}
= \alpha_h + \beta_h\Delta\log p_t + \Gamma_h X_t + u_{t+h}.
\]

The response path is descriptive unless the regressor is independently identified as an exogenous shock.

## Asymmetry

Productivity growth is split into

\[
g_t^+ = \max(g_t,0),\qquad g_t^- = \min(g_t,0).
\]

Separate cumulative coefficients measure transmission during expansions and contractions.

## Cross-country aggregation

The cross-country layer estimates the distributed-lag model separately for each country and retains the cumulative coefficient and its HAC standard error. Only after the country table is written does the pipeline compute descriptive fixed- and random-effects summaries, Cochran's \(Q\), \(\tau^2\), and \(I^2\). The random-effects calculation uses the DerSimonian-Laird moment estimator and is a robustness summary rather than a claim of a common European structural parameter.

## Accounting decomposition

For compensation of employees \(D.1\), the denominator is the number of employees, not total employment. The implementation uses the domestic-concept employee count so that the remuneration concept and production boundary remain aligned. Positive and negative annual contributions are stacked separately in the diagnostic plot; the numerical identity is checked independently and must close to floating-point tolerance.

## Formal break inference

The BIC segmentation above answers *how many regimes fit best*. It does not answer *whether a
break exists*, because the segmentation always returns a partition. `models/break_inference.py`
addresses the second question separately.

The statistic is the sup-F: the largest Chow F over candidate break dates, after trimming 15% of
the sample from each end so that a segment is never estimated from a handful of observations. A
break is allowed in both the intercept and the slope, since a shift in the transmission rate and
a shift in the level of wage growth are different events.

Two deliberate choices. The null distribution of a sup-statistic is non-standard and depends on
the trimming fraction, so no tabulated critical values are used; the p-value is a wild-bootstrap
tail probability under the no-break null, computed by re-running the entire date search on each
replication. Because the search is inside the bootstrap, the p-value already accounts for having
looked at every candidate date, and needs no further multiplicity correction. The Rademacher
wild bootstrap is used rather than an i.i.d. residual bootstrap because annual growth residuals
are heteroskedastic.

The break-date interval is the percentile interval of the bootstrap arg-max under the estimated
break model. It measures how stably the date is located, and a wide interval is reported as
`break_detected_date_poorly_located` rather than being presented as a precise date. A located
break says when the relationship changed; it never says why.

## Bootstrap bands

Local projections and the state-space elasticity both report asymptotic standard errors that are
optimistic in short annual samples. Local-projection windows overlap, so the effective sample at
long horizons is far smaller than the nominal one; the Kalman standard errors condition on the
estimated variance parameters and ignore the uncertainty in estimating them, which matters
because the state variance is what governs how much the elasticity may move.

`models/_bootstrap.py` implements a circular moving-block bootstrap over the *joint* growth
pairs, preserving both the contemporaneous wage-productivity relationship and short-run
persistence within a block. Resampled growth is re-integrated to levels and passed back through
the same validated entry points the point estimates use, so the bootstrap cannot drift from the
estimator it describes.

The bands are pointwise percentile intervals, not simultaneous ones. They do not license a claim
about the path as a whole, such as a decline between two particular years.

## Panel fixed effects

`estimate_panel_fixed_effects` reports one pooled within-country elasticity with standard errors
clustered by country. It is a robustness check and never a replacement for the country-specific
estimates: pooling imposes homogeneous transmission dynamics, and where the country estimates are
heterogeneous the pooled number is a weighted average of genuinely different processes rather
than a common parameter.

Cluster-robust inference is asymptotic in the *number of clusters*. With the country counts
available here -- well below the conventional threshold of about 30 -- the clustered standard
errors are downward-biased, and the result carries that caveat in its `interpretation` field so
the warning travels with the number rather than living only in this document.

Optional year effects absorb common annual shocks, at the cost of discarding the cross-country
common component that a global productivity slowdown would show up in.
