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

## Dynamic panel

`models/dynamic_panel.py` estimates the panel version of the paper's own estimand:

```
dlog w_it = a_i + l_t + sum_{j=0..2} b_j dlog p_{i,t-j} + g dlog w_{i,t-1} + u_it
Theta_panel = (b_0 + b_1 + b_2) / (1 - g)
```

The structure deliberately matches the country-level distributed lag, so the pooled quantity is
the same cumulative multiplier rather than a contemporaneous slope. Country and year effects are
the primary specification; country effects alone are the pre-specified sensitivity. The two
productivity drivers are estimated separately and never pooled. Two driver lags and one dependent
lag cost three observations per country, so the effective sample is 12(28) + 27 = 363.

**Bias.** A lagged dependent variable beside fixed effects makes LSDV inconsistent, with a bias of
order `1/T` (Nickell 1981). Twenty-eight effective years shrink it without removing it, and
thirteen countries are far too few for Arellano-Bond or system GMM, whose asymptotics run in the
wrong direction here. Estimation is bias-corrected, with the uncorrected estimate reported beside
it so the size of the correction is visible; only the corrected estimator is substantive.

The correction is **simulation-based** (Everaert and Pozzi 2007), not the analytical
Kiviet-Bruno expansion. That expansion is derived for a model with individual effects and strictly
exogenous regressors and does not accommodate the year effects the primary specification carries.
The implementation simulates the panel from a candidate parameter -- holding the driver path, the
estimated fixed effects, the initial conditions and the missing-cell pattern at their observed
values, resampling errors as whole cross-sectional vectors so contemporaneous dependence survives
-- re-estimates LSDV on each simulated panel, and solves for the parameter whose simulated mean
reproduces the observed estimate. `tests/test_dynamic_panel.py` checks it against panels with
known parameters: uncorrected LSDV reproduces the textbook `-(1+g)/T` bias and the correction
removes better than nine tenths of it.

The bias correction addresses dynamic fixed-effects bias. It does **not** solve contemporaneous
endogeneity between productivity and wages. The coefficient remains a reduced-form conditional
association.

**Inference.** Thirteen clusters cannot support country-clustered normal intervals, and the
multiplier is a ratio, so a delta-method interval around it is optimistic twice over. Intervals
come from a circular moving-block bootstrap in which each drawn block carries the complete
thirteen-country cross-section, preserving contemporaneous cross-country dependence. The
resampling universe is restricted to years every country observes, so every drawn cross-section is
complete; the short country's missing endpoint is reinstated by giving it one fewer resampled
year, so every replication reproduces the observed panel shape exactly. Lags are rebuilt after
concatenation, the corrected model is re-estimated in each replication, and `Theta` is computed
inside it, so the interval is a percentile interval for the ratio itself.

Resampling the data rather than the residuals breaks the dynamic relation at each block boundary,
which attenuates persistence within a replication. The median replication is therefore reported
beside every point estimate, so the displacement between the two is visible rather than buried.

Driscoll-Kraay standard errors are a **secondary diagnostic** only: their justification is
asymptotic in the time dimension, and about twenty-eight effective years is not enough for them to
replace the bootstrap.

**Gates**, all frozen in `config/models.yml` before retrieval: `|g| < 1`, at least 25 effective
years, a finite multiplier in at least 95% of replications, at least 95% convergence, no rank
deficiency after the fixed effects, and all requested replications completed. A specification
failing any of them is reported and labelled ineligible, never dropped.

## Panel fixed effects (superseded)

`estimate_panel_fixed_effects` reports one pooled within-country elasticity with country-clustered
standard errors. It is **static**: wage growth on contemporaneous driver growth, no lags and no
lagged dependent variable, so its coefficient is not the cumulative multiplier the paper reports
and the two must not be compared. It also uses every available first difference, 389 observations,
against 363 for the dynamic specification. It remains in the package as the estimator behind an
earlier release's appendix; new work should use `dynamic_panel` instead.
