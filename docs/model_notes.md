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
