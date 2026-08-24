"""Dynamic panel estimation of the cumulative wage-transmission multiplier.

The country-specific estimators in this package answer "how much of a productivity change
shows up in wages once the dynamics have played out" for one country at a time. This module
asks the same question of the panel, using the *same* dynamic structure::

    dlog w_it = a_i + l_t + sum_{j=0..2} beta_j dlog p_{i,t-j} + gamma dlog w_{i,t-1} + u_it

so that the panel estimand is the same cumulative multiplier::

    Theta = (beta_0 + beta_1 + beta_2) / (1 - gamma)

and not a contemporaneous slope. A static pooled regression of wage growth on contemporaneous
driver growth answers a different question and is not comparable with it; that distinction is
the reason this module exists.

Three properties of the estimator matter enough to state here rather than in an appendix.

**Dynamic fixed-effects bias.** Least-squares dummy variables (LSDV) is inconsistent when a
lagged dependent variable sits beside fixed effects, because the within transformation
correlates the transformed regressor with the transformed error. The bias is of order
``1/T`` (Nickell 1981). With ``T`` of about thirty it is smaller than in a short panel but it
does not disappear, and with thirteen countries the cross-section is far too small to lean on
Arellano--Bond or system GMM, whose asymptotics run in the wrong direction here.

The correction implemented below is a **simulation-based (iterated) bias correction** in the
spirit of Everaert and Pozzi (2007), *not* the analytical Kiviet/Bruno expansion. That is a
deliberate substitution and the reason is specific: Bruno's (2005) approximation for
unbalanced panels is derived for a model with individual effects and strictly exogenous
regressors, and it does not accommodate the time effects that the primary specification here
requires. Applying it to the primary specification would mean either dropping the year effects
or using a bias formula outside the conditions it was derived under. The simulation correction
handles both fixed-effect dimensions and the unbalanced endpoint directly, at the cost of
being computational rather than closed-form. Every step of it is in this file.

**What the correction does not do.** The bias correction addresses dynamic fixed-effects bias.
It does not solve contemporaneous endogeneity between productivity and wages. The corrected
coefficient remains a reduced-form conditional association.

**Inference.** Country-clustered normal intervals with thirteen clusters are not reliable, and
the multiplier is a ratio, so a delta-method interval around it is optimistic twice over.
:func:`bootstrap_dynamic_panel` instead resamples circular moving blocks of *complete
cross-sections* over time -- the whole country vector moves together, which preserves
contemporaneous cross-country dependence -- reconstructs the lag structure after
concatenation, re-estimates the corrected model in every replication, and forms percentile
intervals for ``Theta`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from wage_transmission.config import DynamicPanelConfig
from wage_transmission.validation import add_log_growth_columns, validate_level_frame

FixedEffects = Literal["country", "country_and_year"]

#: Distance from one below which ``1 - gamma`` is treated as numerically degenerate.
MULTIPLIER_TOLERANCE = 1e-6


@dataclass(frozen=True)
class GrowthPanel:
    """Aligned annual log-growth rates for every country, on a common year grid.

    ``wage_growth`` and ``driver_growth`` are ``(n_countries, n_years)`` arrays holding NaN
    where a country does not observe that year. The grid is shared, so one column is one
    calendar year across the whole cross-section -- which is the object the block bootstrap
    resamples.
    """

    countries: tuple[str, ...]
    years: tuple[int, ...]
    wage_growth: np.ndarray
    driver_growth: np.ndarray

    @property
    def observed(self) -> np.ndarray:
        """Boolean mask of cells where both growth rates are available."""
        return np.asarray(
            np.isfinite(self.wage_growth) & np.isfinite(self.driver_growth), dtype=bool
        )

    @property
    def complete_year_mask(self) -> np.ndarray:
        """Boolean mask of years observed by every country."""
        return np.asarray(np.all(self.observed, axis=0), dtype=bool)


def build_growth_panel(
    panel: pd.DataFrame,
    *,
    driver_column: str = "productivity",
) -> GrowthPanel:
    """Validate each country's levels and align their log growth on a common year grid."""
    if "country" not in panel.columns:
        raise ValueError("Panel input must contain a `country` column.")
    if driver_column not in panel.columns:
        raise ValueError(f"Driver column not found: {driver_column}")

    series: dict[str, pd.DataFrame] = {}
    for country, raw in panel.groupby("country", sort=True):
        prepared = raw.copy()
        prepared["productivity"] = pd.to_numeric(prepared[driver_column], errors="coerce")
        levels = validate_level_frame(prepared)
        growth = add_log_growth_columns(levels).dropna(subset=["dlog_wage", "dlog_productivity"])
        if growth.empty:
            continue
        series[str(country)] = growth.loc[:, ["year", "dlog_wage", "dlog_productivity"]]

    if len(series) < 2:
        raise ValueError("A dynamic panel estimate needs at least two countries.")

    countries = tuple(sorted(series))
    years = tuple(sorted({int(year) for frame in series.values() for year in frame["year"]}))
    index = {year: position for position, year in enumerate(years)}

    wage = np.full((len(countries), len(years)), np.nan, dtype=float)
    driver = np.full((len(countries), len(years)), np.nan, dtype=float)
    for row, country in enumerate(countries):
        frame = series[country]
        positions = [index[int(year)] for year in frame["year"]]
        wage[row, positions] = frame["dlog_wage"].to_numpy(dtype=float)
        driver[row, positions] = frame["dlog_productivity"].to_numpy(dtype=float)
    return GrowthPanel(countries=countries, years=years, wage_growth=wage, driver_growth=driver)


@dataclass(frozen=True)
class PanelDesign:
    """Stacked regression design for one dynamic panel specification.

    ``position[c, j]`` maps country ``c`` and its ``j``-th usable period to a row of the
    stacked design, or -1 where that country has no such period. Keeping the design in this
    rectangular form is what makes the recursive simulation below vectorisable.
    """

    outcome: np.ndarray
    driver: np.ndarray
    lagged_outcome: np.ndarray
    country_index: np.ndarray
    period_index: np.ndarray
    position: np.ndarray
    initial_lag: np.ndarray
    countries: tuple[str, ...]
    n_periods: int

    @property
    def nobs(self) -> int:
        """Number of stacked regression observations."""
        return int(self.outcome.size)

    @property
    def n_countries(self) -> int:
        """Number of countries contributing at least one observation."""
        return len(self.countries)

    @property
    def regressors(self) -> np.ndarray:
        """Driver lags followed by the lagged dependent variable."""
        return np.column_stack([self.driver, self.lagged_outcome])


def build_panel_design(
    wage_growth: np.ndarray,
    driver_growth: np.ndarray,
    countries: tuple[str, ...],
    *,
    driver_lags: int = 2,
) -> PanelDesign:
    """Reconstruct the lag structure column by column and stack it into a design.

    Lags are read off the *ordered columns supplied*, not off calendar years. On the observed
    panel those coincide; after a block resample they do not, which is exactly why the lag
    reconstruction has to happen here rather than upstream.

    A country's usable columns must form one contiguous run. An interior gap would silently
    splice two non-adjacent years into a lag, so it is rejected rather than tolerated.
    """
    if driver_lags < 0:
        raise ValueError("driver_lags must be non-negative.")
    if wage_growth.shape != driver_growth.shape:
        raise ValueError("Wage and driver growth arrays must have the same shape.")
    if wage_growth.shape[0] != len(countries):
        raise ValueError("Growth arrays must have one row per country.")

    max_lag = max(driver_lags, 1)
    observed = np.isfinite(wage_growth) & np.isfinite(driver_growth)
    n_countries = wage_growth.shape[0]

    runs: list[tuple[int, int]] = []
    for row in range(n_countries):
        present = np.flatnonzero(observed[row])
        if present.size == 0:
            runs.append((0, 0))
            continue
        first, last = int(present[0]), int(present[-1]) + 1
        if present.size != last - first:
            raise ValueError(
                f"Country {countries[row]} has an interior gap in its growth series; "
                "lag reconstruction would splice non-adjacent years."
            )
        runs.append((first + max_lag, last))

    lengths = [max(stop - start, 0) for start, stop in runs]
    if sum(lengths) == 0:
        raise ValueError("No country has enough consecutive observations to build lags.")
    width = max(lengths)

    position = np.full((n_countries, width), -1, dtype=int)
    outcome: list[float] = []
    driver_rows: list[np.ndarray] = []
    lagged: list[float] = []
    country_index: list[int] = []
    period_index: list[int] = []
    initial_lag = np.full(n_countries, np.nan, dtype=float)

    for row, (start, stop) in enumerate(runs):
        if stop - start <= 0:
            continue
        initial_lag[row] = wage_growth[row, start - 1]
        for offset, column in enumerate(range(start, stop)):
            position[row, offset] = len(outcome)
            outcome.append(float(wage_growth[row, column]))
            driver_rows.append(
                np.array(
                    [driver_growth[row, column - lag] for lag in range(driver_lags + 1)],
                    dtype=float,
                )
            )
            lagged.append(float(wage_growth[row, column - 1]))
            country_index.append(row)
            period_index.append(offset)

    active = tuple(countries[row] for row, length in enumerate(lengths) if length > 0)
    return PanelDesign(
        outcome=np.asarray(outcome, dtype=float),
        driver=np.vstack(driver_rows),
        lagged_outcome=np.asarray(lagged, dtype=float),
        country_index=np.asarray(country_index, dtype=int),
        period_index=np.asarray(period_index, dtype=int),
        position=position,
        initial_lag=initial_lag,
        countries=active,
        n_periods=width,
    )


def _indicator(index: np.ndarray, size: int) -> np.ndarray:
    matrix = np.zeros((index.size, size), dtype=float)
    matrix[np.arange(index.size), index] = 1.0
    return matrix


class WithinProjector:
    """Annihilator for the fixed effects of one specification.

    The dummy pattern is a property of *which cells are observed*, not of their values, so it
    is identical in every bootstrap replication and can be built once and reused. Projecting
    through the pseudo-inverse rather than an explicit ``n x n`` matrix keeps each application
    linear in the number of dummies.
    """

    def __init__(self, design: PanelDesign, *, fixed_effects: FixedEffects) -> None:
        blocks = [_indicator(design.country_index, design.position.shape[0])]
        if fixed_effects == "country_and_year":
            # One period is absorbed by the country dummies; dropping it keeps D full rank.
            blocks.append(_indicator(design.period_index, design.n_periods)[:, 1:])
        matrix = np.hstack(blocks)
        # Columns for countries that contribute no observation are structurally empty.
        keep = np.flatnonzero(matrix.any(axis=0))
        matrix = matrix[:, keep]
        self.matrix = matrix
        self.pseudo_inverse = np.linalg.pinv(matrix)
        self.rank = int(np.linalg.matrix_rank(matrix))
        self.n_columns = int(matrix.shape[1])
        self.country_index = design.country_index
        self.period_index = design.period_index
        self.fixed_effects: FixedEffects = fixed_effects

    def matches(self, design: PanelDesign) -> bool:
        """True when ``design`` has the same observation pattern this projector was built on."""
        return bool(
            design.country_index.shape == self.country_index.shape
            and np.array_equal(design.country_index, self.country_index)
            and np.array_equal(design.period_index, self.period_index)
        )

    def annihilate(self, values: np.ndarray) -> np.ndarray:
        """Remove the fixed-effect projection from a column vector or a matrix of columns."""
        return np.asarray(values - self.matrix @ (self.pseudo_inverse @ values), dtype=float)

    def projection(self, values: np.ndarray) -> np.ndarray:
        """Return only the fixed-effect projection of a column vector."""
        return np.asarray(self.matrix @ (self.pseudo_inverse @ values), dtype=float)


@dataclass(frozen=True)
class WithinFit:
    """Least-squares dummy-variable fit of one dynamic panel specification."""

    coefficients: np.ndarray
    residuals: np.ndarray
    fixed_effect_part: np.ndarray
    nobs: int
    n_parameters: int
    rank_deficient: bool

    @property
    def driver_sum(self) -> float:
        """Sum of the current and lagged driver coefficients."""
        return float(np.sum(self.coefficients[:-1]))

    @property
    def persistence(self) -> float:
        """Coefficient on the lagged dependent variable."""
        return float(self.coefficients[-1])

    @property
    def multiplier(self) -> float:
        """Cumulative transmission ``sum(beta) / (1 - gamma)``."""
        return cumulative_multiplier(self.coefficients)


def cumulative_multiplier(coefficients: np.ndarray) -> float:
    """Cumulative transmission implied by driver coefficients and one persistence term."""
    denominator = 1.0 - float(coefficients[-1])
    if abs(denominator) < MULTIPLIER_TOLERANCE:
        return float("nan")
    return float(np.sum(coefficients[:-1])) / denominator


def fit_lsdv(
    design: PanelDesign,
    projector: WithinProjector,
    *,
    check_rank: bool = True,
) -> WithinFit:
    """Fit the dynamic specification by least-squares dummy variables.

    ``check_rank`` runs a full rank test of the regressors stacked beside the dummies. It is a
    pre-specified gate on the observed sample; inside the bootstrap the pattern is unchanged,
    so repeating the singular-value decomposition every replication would cost time and prove
    nothing new.
    """
    x = design.regressors
    transformed = projector.annihilate(x)
    outcome = projector.annihilate(design.outcome)
    rank_deficient = False
    if check_rank:
        combined = int(np.linalg.matrix_rank(np.hstack([x, projector.matrix])))
        rank_deficient = combined < x.shape[1] + projector.n_columns
    coefficients = np.asarray(
        np.linalg.solve(transformed.T @ transformed, transformed.T @ outcome), dtype=float
    )
    residuals = outcome - transformed @ coefficients
    fixed_effect_part = projector.projection(design.outcome - x @ coefficients)
    return WithinFit(
        coefficients=coefficients,
        residuals=residuals,
        fixed_effect_part=fixed_effect_part,
        nobs=design.nobs,
        n_parameters=int(x.shape[1]) + projector.rank,
        rank_deficient=rank_deficient,
    )


@dataclass(frozen=True)
class BiasCorrection:
    """Outcome of the simulation-based bias correction."""

    coefficients: np.ndarray
    bias: np.ndarray
    iterations: int
    converged: bool

    @property
    def driver_sum(self) -> float:
        """Sum of the corrected driver coefficients."""
        return float(np.sum(self.coefficients[:-1]))

    @property
    def persistence(self) -> float:
        """Corrected coefficient on the lagged dependent variable."""
        return float(self.coefficients[-1])

    @property
    def multiplier(self) -> float:
        """Corrected cumulative transmission."""
        return cumulative_multiplier(self.coefficients)


class BiasCorrector:
    """Simulation-based bias correction for the dynamic fixed-effects estimator.

    The bias of LSDV at a parameter vector ``theta`` is estimated by simulating the panel from
    ``theta`` -- holding the driver path, the estimated fixed effects, the initial conditions
    and the missing-cell pattern at their observed values -- re-estimating LSDV on each
    simulated panel, and averaging. The correction then solves ``theta + bias(theta) = LSDV``
    by fixed-point iteration.

    Errors are resampled as whole cross-sectional vectors, so contemporaneous dependence across
    countries survives into the simulated panels. Only periods observed by every country enter
    that pool, which keeps every simulated draw complete.

    The same random draws are reused across iterations. That is not an economy: it makes the
    simulated bias a smooth function of ``theta``, so the fixed point is well defined rather
    than chasing simulation noise.
    """

    def __init__(
        self,
        design: PanelDesign,
        projector: WithinProjector,
        *,
        draws: int,
        iterations: int,
        rng: np.random.Generator,
    ) -> None:
        if draws < 1:
            raise ValueError("draws must be positive.")
        if iterations < 1:
            raise ValueError("iterations must be positive.")
        self.design = design
        self.projector = projector
        self.draws = int(draws)
        self.iterations = int(iterations)
        self._valid = design.position >= 0
        self._rows = design.position[self._valid]
        complete = np.all(self._valid, axis=0)
        self._complete_periods = np.flatnonzero(complete)
        if self._complete_periods.size == 0:
            raise ValueError("No period is observed by every country; cannot resample errors.")
        self._error_draws = rng.integers(
            0, self._complete_periods.size, size=(self.draws, design.n_periods)
        )
        self._driver_within = projector.annihilate(design.driver)
        self._driver_gram = self._driver_within.T @ self._driver_within

    def _residual_matrix(self, residuals: np.ndarray) -> np.ndarray:
        matrix = np.zeros(self.design.position.shape, dtype=float)
        matrix[self._valid] = residuals[self._rows]
        return matrix

    def _simulate(
        self,
        coefficients: np.ndarray,
        fixed_effect_part: np.ndarray,
        residual_matrix: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        design = self.design
        gamma = float(coefficients[-1])
        deterministic = fixed_effect_part + design.driver @ coefficients[:-1]

        effects = np.zeros(design.position.shape, dtype=float)
        effects[self._valid] = deterministic[self._rows]
        pool = residual_matrix[:, self._complete_periods]
        errors = np.transpose(pool[:, self._error_draws], (1, 0, 2))

        simulated = np.zeros((self.draws, *design.position.shape), dtype=float)
        lagged = np.zeros_like(simulated)
        previous = np.tile(np.nan_to_num(design.initial_lag, nan=0.0), (self.draws, 1))
        for period in range(design.n_periods):
            lagged[:, :, period] = previous
            previous = effects[:, period] + gamma * previous + errors[:, :, period]
            simulated[:, :, period] = previous

        outcome = np.zeros((self.draws, design.nobs), dtype=float)
        lag_column = np.zeros((self.draws, design.nobs), dtype=float)
        outcome[:, self._rows] = simulated[:, self._valid]
        lag_column[:, self._rows] = lagged[:, self._valid]
        return outcome, lag_column

    def _estimate_simulated(self, outcome: np.ndarray, lag_column: np.ndarray) -> np.ndarray:
        outcome_within = self.projector.annihilate(outcome.T)
        lag_within = self.projector.annihilate(lag_column.T)

        k = self._driver_within.shape[1]
        draws = outcome.shape[0]
        gram = np.zeros((draws, k + 1, k + 1), dtype=float)
        gram[:, :k, :k] = self._driver_gram
        cross = (self._driver_within.T @ lag_within).T
        gram[:, :k, k] = cross
        gram[:, k, :k] = cross
        gram[:, k, k] = np.einsum("nd,nd->d", lag_within, lag_within)

        moment = np.zeros((draws, k + 1), dtype=float)
        moment[:, :k] = (self._driver_within.T @ outcome_within).T
        moment[:, k] = np.einsum("nd,nd->d", lag_within, outcome_within)
        # numpy treats a trailing 1-d operand as a matrix, so solve column by column.
        solved = np.linalg.solve(gram, moment[:, :, None])
        return np.asarray(solved[:, :, 0], dtype=float)

    def correct(self, fit: WithinFit, *, tolerance: float = 1e-7) -> BiasCorrection:
        """Solve for the parameter whose simulated LSDV mean reproduces the observed fit."""
        residual_matrix = self._residual_matrix(fit.residuals)
        target = fit.coefficients
        candidate = target.copy()
        bias = np.zeros_like(target)
        converged = False
        used = 0
        for step in range(self.iterations):
            used = step + 1
            if not abs(float(candidate[-1])) < 1.0:
                break
            outcome, lag_column = self._simulate(candidate, fit.fixed_effect_part, residual_matrix)
            bias = np.mean(self._estimate_simulated(outcome, lag_column), axis=0) - candidate
            updated = target - bias
            if not bool(np.all(np.isfinite(updated))):
                break
            change = float(np.max(np.abs(updated - candidate)))
            candidate = updated
            if change < tolerance:
                converged = True
                break
        return BiasCorrection(
            coefficients=candidate,
            bias=bias,
            iterations=used,
            converged=bool(converged and abs(float(candidate[-1])) < 1.0),
        )


def driscoll_kraay_covariance(
    design: PanelDesign,
    projector: WithinProjector,
    fit: WithinFit,
    *,
    lags: int,
) -> np.ndarray:
    """Driscoll--Kraay covariance of the within coefficients.

    Scores are aggregated across the cross-section within each period and then given a
    Newey--West weighting over periods, which permits general spatial dependence as well as
    serial correlation. Its justification is asymptotic in the *time* dimension; with roughly
    thirty annual periods it is a diagnostic, not a substitute for the block bootstrap.
    """
    if lags < 0:
        raise ValueError("lags must be non-negative.")
    transformed = projector.annihilate(design.regressors)
    scores = transformed * fit.residuals[:, None]
    aggregated = np.zeros((design.n_periods, transformed.shape[1]), dtype=float)
    np.add.at(aggregated, design.period_index, scores)

    meat = aggregated.T @ aggregated
    for lag in range(1, min(lags, design.n_periods - 1) + 1):
        weight = 1.0 - lag / (lags + 1.0)
        cross = aggregated[lag:].T @ aggregated[:-lag]
        meat += weight * (cross + cross.T)

    bread = np.linalg.inv(transformed.T @ transformed)
    return np.asarray(bread @ meat @ bread, dtype=float)


def multiplier_gradient(coefficients: np.ndarray) -> np.ndarray:
    """Gradient of ``sum(beta) / (1 - gamma)`` with respect to the coefficient vector."""
    denominator = 1.0 - float(coefficients[-1])
    if abs(denominator) < MULTIPLIER_TOLERANCE:
        return np.full(coefficients.size, np.nan, dtype=float)
    gradient = np.empty(coefficients.size, dtype=float)
    gradient[:-1] = 1.0 / denominator
    gradient[-1] = float(np.sum(coefficients[:-1])) / denominator**2
    return gradient


def circular_block_columns(
    universe: np.ndarray,
    length: int,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw ``length`` column indices as circular moving blocks from ``universe``."""
    size = int(universe.size)
    if size < 1:
        raise ValueError("The resampling universe is empty.")
    if not 1 <= block_length <= size:
        raise ValueError(f"block_length must lie in [1, {size}]; got {block_length}")
    n_blocks = int(np.ceil(length / block_length))
    starts = rng.integers(0, size, size=n_blocks)
    offsets = np.arange(block_length)
    positions = ((starts[:, None] + offsets[None, :]) % size).ravel()[:length]
    return np.asarray(universe[positions], dtype=int)


@dataclass(frozen=True)
class DynamicPanelGates:
    """Conditions under which the dynamic panel estimate may be reported as substantive.

    Every threshold is frozen before the source snapshot is retrieved. A result that fails any
    of them is still reported, and labelled ineligible, rather than quietly dropped.
    """

    max_abs_persistence: float = 1.0
    min_effective_years: int = 25
    min_finite_multiplier_share: float = 0.95
    min_convergence_share: float = 0.95


@dataclass(frozen=True)
class BootstrapDraws:
    """Per-replication quantities from the moving-block panel bootstrap."""

    lsdv_multiplier: np.ndarray
    corrected_multiplier: np.ndarray
    corrected_persistence: np.ndarray
    converged: np.ndarray


def bootstrap_dynamic_panel(
    growth: GrowthPanel,
    projector: WithinProjector,
    *,
    driver_lags: int,
    block_length: int,
    replications: int,
    bias_correction_draws: int,
    bias_correction_iterations: int,
    rng: np.random.Generator,
) -> BootstrapDraws:
    """Circular moving-block bootstrap over complete cross-sections.

    Each replication draws blocks of *years*, and every drawn year carries the whole country
    vector, so contemporaneous cross-country dependence is preserved rather than destroyed.
    The resampling universe is restricted to years observed by every country, which keeps every
    drawn cross-section complete; the unbalanced endpoint is reinstated by giving the short
    country one fewer resampled year, so each replication reproduces the observed panel shape
    exactly. Lags are rebuilt from the concatenated series, never from calendar time.

    One property of resampling the *data* rather than the residuals has to be stated. Gluing
    blocks together breaks the dynamic relation at each block boundary, so the persistence
    estimated within a replication is attenuated toward zero relative to the point estimate,
    and the multiplier with it. The distortion grows with persistence and shrinks with block
    length. The caller therefore receives the median of the replications alongside the interval,
    so the displacement between the point estimate and the resampling distribution is visible
    rather than buried: these are intervals for sampling variability, not bias corrections.
    """
    if replications < 1:
        raise ValueError("replications must be positive.")
    universe = np.flatnonzero(growth.complete_year_mask)
    if universe.size < block_length:
        raise ValueError("Too few complete cross-sections for the requested block length.")
    lengths = growth.observed.sum(axis=1).astype(int)
    full_length = int(lengths.max())

    lsdv: list[float] = []
    corrected: list[float] = []
    persistence: list[float] = []
    converged: list[bool] = []
    wage = np.empty((len(growth.countries), full_length), dtype=float)
    driver = np.empty_like(wage)
    for _ in range(replications):
        columns = circular_block_columns(universe, full_length, block_length, rng)
        wage.fill(np.nan)
        driver.fill(np.nan)
        for row in range(len(growth.countries)):
            take = columns[: lengths[row]]
            wage[row, : take.size] = growth.wage_growth[row, take]
            driver[row, : take.size] = growth.driver_growth[row, take]
        try:
            design = build_panel_design(wage, driver, growth.countries, driver_lags=driver_lags)
            if not projector.matches(design):
                raise ValueError("Resampled design does not match the observed panel shape.")
            fit = fit_lsdv(design, projector, check_rank=False)
            correction = BiasCorrector(
                design,
                projector,
                draws=bias_correction_draws,
                iterations=bias_correction_iterations,
                rng=np.random.default_rng(int(rng.integers(0, 2**63 - 1))),
            ).correct(fit)
        except (ValueError, np.linalg.LinAlgError):
            lsdv.append(float("nan"))
            corrected.append(float("nan"))
            persistence.append(float("nan"))
            converged.append(False)
            continue
        lsdv.append(fit.multiplier)
        corrected.append(correction.multiplier)
        persistence.append(correction.persistence)
        converged.append(correction.converged)

    return BootstrapDraws(
        lsdv_multiplier=np.asarray(lsdv, dtype=float),
        corrected_multiplier=np.asarray(corrected, dtype=float),
        corrected_persistence=np.asarray(persistence, dtype=float),
        converged=np.asarray(converged, dtype=bool),
    )


@dataclass(frozen=True)
class DynamicPanelResult:
    """One dynamic panel specification, its bias correction, and its bootstrap interval."""

    driver: str
    fixed_effects: FixedEffects
    role: str
    n_countries: int
    nobs: int
    n_effective_years: int
    driver_lags: int
    lsdv_coefficients: tuple[float, ...]
    lsdv_driver_sum: float
    lsdv_persistence: float
    lsdv_multiplier: float
    corrected_coefficients: tuple[float, ...]
    corrected_driver_sum: float
    corrected_persistence: float
    corrected_multiplier: float
    correction_bias: tuple[float, ...]
    correction_converged: bool
    correction_iterations: int
    correction_draws: int
    driscoll_kraay_std_errors: tuple[float, ...]
    driscoll_kraay_driver_sum_std_error: float
    driscoll_kraay_persistence_std_error: float
    driscoll_kraay_multiplier_std_error: float
    driscoll_kraay_lags: int
    block_length: int
    seed: int
    replications_requested: int
    replications_completed: int
    convergence_share: float
    finite_multiplier_share: float
    lsdv_multiplier_ci: tuple[float, float]
    corrected_multiplier_ci: tuple[float, float]
    corrected_persistence_ci: tuple[float, float]
    lsdv_multiplier_bootstrap_median: float
    corrected_multiplier_bootstrap_median: float
    corrected_persistence_bootstrap_median: float
    one_minus_persistence_quantiles: dict[str, float]
    one_minus_persistence_min_abs: float
    rank_deficient: bool
    gate_failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def claim_eligible(self) -> bool:
        """True when no pre-specified gate failed."""
        return not self.gate_failures


def _quantile_map(values: np.ndarray) -> dict[str, float]:
    probabilities = (0.01, 0.025, 0.05, 0.25, 0.5, 0.75, 0.95, 0.975, 0.99)
    if values.size == 0:
        return {f"p{probability * 100:g}": float("nan") for probability in probabilities}
    return {
        f"p{probability * 100:g}": float(np.quantile(values, probability))
        for probability in probabilities
    }


def _finite_median(draws: np.ndarray) -> float:
    finite = draws[np.isfinite(draws)]
    return float(np.median(finite)) if finite.size else float("nan")


def _percentile_interval(draws: np.ndarray, alpha: float) -> tuple[float, float]:
    finite = draws[np.isfinite(draws)]
    if finite.size == 0:
        return (float("nan"), float("nan"))
    return (
        float(np.quantile(finite, alpha / 2.0)),
        float(np.quantile(finite, 1.0 - alpha / 2.0)),
    )


def estimate_dynamic_panel(
    panel: pd.DataFrame,
    *,
    driver_column: str = "productivity",
    fixed_effects: FixedEffects = "country_and_year",
    role: str = "primary",
    driver_lags: int = 2,
    block_length: int = 4,
    replications: int = 4999,
    bias_correction_draws: int = 200,
    bias_correction_iterations: int = 12,
    driscoll_kraay_lags: int = 3,
    seed: int = 20260824,
    alpha: float = 0.05,
    gates: DynamicPanelGates | None = None,
) -> DynamicPanelResult:
    """Estimate the cumulative panel multiplier with a bias correction and bootstrap interval.

    The returned object carries the uncorrected LSDV estimate beside the corrected one, so the
    size of the correction is visible, and the pre-specified gate failures, so an ineligible
    result cannot be mistaken for a substantive one.
    """
    thresholds = gates or DynamicPanelGates()
    growth = build_growth_panel(panel, driver_column=driver_column)
    design = build_panel_design(
        growth.wage_growth,
        growth.driver_growth,
        growth.countries,
        driver_lags=driver_lags,
    )
    projector = WithinProjector(design, fixed_effects=fixed_effects)
    fit = fit_lsdv(design, projector)

    corrected = BiasCorrector(
        design,
        projector,
        draws=bias_correction_draws,
        iterations=bias_correction_iterations,
        rng=np.random.default_rng(seed + 1),
    ).correct(fit)

    covariance = driscoll_kraay_covariance(design, projector, fit, lags=driscoll_kraay_lags)
    gradient = multiplier_gradient(fit.coefficients)
    multiplier_variance = float(gradient @ covariance @ gradient)
    sum_selector = np.concatenate([np.ones(fit.coefficients.size - 1), [0.0]])
    driver_sum_variance = float(sum_selector @ covariance @ sum_selector)

    draws = bootstrap_dynamic_panel(
        growth,
        projector,
        driver_lags=driver_lags,
        block_length=block_length,
        replications=replications,
        bias_correction_draws=bias_correction_draws,
        bias_correction_iterations=bias_correction_iterations,
        rng=np.random.default_rng(seed),
    )

    effective_years = int(np.unique(design.period_index).size)
    completed = int(np.count_nonzero(np.isfinite(draws.lsdv_multiplier)))
    finite_share = float(np.mean(np.isfinite(draws.corrected_multiplier)))
    convergence_share = float(np.mean(draws.converged))

    failures: list[str] = []
    if not abs(fit.persistence) < thresholds.max_abs_persistence:
        failures.append("lsdv_persistence_outside_unit_circle")
    if not abs(corrected.persistence) < thresholds.max_abs_persistence:
        failures.append("corrected_persistence_outside_unit_circle")
    if effective_years < thresholds.min_effective_years:
        failures.append("insufficient_effective_years")
    if finite_share < thresholds.min_finite_multiplier_share:
        failures.append("bootstrap_multiplier_not_finite")
    if convergence_share < thresholds.min_convergence_share:
        failures.append("bootstrap_convergence_below_threshold")
    if fit.rank_deficient:
        failures.append("rank_deficient_after_fixed_effects")
    if completed < replications:
        failures.append("incomplete_bootstrap")
    if not corrected.converged:
        failures.append("bias_correction_not_converged")

    one_minus = 1.0 - draws.corrected_persistence
    finite_one_minus = one_minus[np.isfinite(one_minus)]
    return DynamicPanelResult(
        driver=driver_column,
        fixed_effects=fixed_effects,
        role=role,
        n_countries=design.n_countries,
        nobs=design.nobs,
        n_effective_years=effective_years,
        driver_lags=int(driver_lags),
        lsdv_coefficients=tuple(float(value) for value in fit.coefficients),
        lsdv_driver_sum=fit.driver_sum,
        lsdv_persistence=fit.persistence,
        lsdv_multiplier=fit.multiplier,
        corrected_coefficients=tuple(float(value) for value in corrected.coefficients),
        corrected_driver_sum=corrected.driver_sum,
        corrected_persistence=corrected.persistence,
        corrected_multiplier=corrected.multiplier,
        correction_bias=tuple(float(value) for value in corrected.bias),
        correction_converged=corrected.converged,
        correction_iterations=corrected.iterations,
        correction_draws=int(bias_correction_draws),
        driscoll_kraay_std_errors=tuple(
            float(value) for value in np.sqrt(np.maximum(np.diag(covariance), 0.0))
        ),
        driscoll_kraay_driver_sum_std_error=float(np.sqrt(max(driver_sum_variance, 0.0))),
        driscoll_kraay_persistence_std_error=float(np.sqrt(max(float(covariance[-1, -1]), 0.0))),
        driscoll_kraay_multiplier_std_error=float(np.sqrt(max(multiplier_variance, 0.0))),
        driscoll_kraay_lags=int(driscoll_kraay_lags),
        block_length=int(block_length),
        seed=int(seed),
        replications_requested=int(replications),
        replications_completed=completed,
        convergence_share=convergence_share,
        finite_multiplier_share=finite_share,
        lsdv_multiplier_ci=_percentile_interval(draws.lsdv_multiplier, alpha),
        corrected_multiplier_ci=_percentile_interval(draws.corrected_multiplier, alpha),
        corrected_persistence_ci=_percentile_interval(draws.corrected_persistence, alpha),
        lsdv_multiplier_bootstrap_median=_finite_median(draws.lsdv_multiplier),
        corrected_multiplier_bootstrap_median=_finite_median(draws.corrected_multiplier),
        corrected_persistence_bootstrap_median=_finite_median(draws.corrected_persistence),
        one_minus_persistence_quantiles=_quantile_map(finite_one_minus),
        one_minus_persistence_min_abs=(
            float(np.min(np.abs(finite_one_minus))) if finite_one_minus.size else float("nan")
        ),
        rank_deficient=fit.rank_deficient,
        gate_failures=tuple(failures),
    )


@dataclass(frozen=True)
class DynamicPanelSuite:
    """Every frozen dynamic-panel specification for one driver, in reporting order."""

    driver: str
    primary: DynamicPanelResult
    specifications: tuple[DynamicPanelResult, ...]

    @property
    def claim_eligible(self) -> bool:
        """True when the primary specification passed every pre-specified gate."""
        return self.primary.claim_eligible


def estimate_dynamic_panel_suite(
    panel: pd.DataFrame,
    *,
    driver_column: str,
    config: DynamicPanelConfig | None = None,
    alpha: float = 0.05,
) -> DynamicPanelSuite:
    """Run the frozen hierarchy for one driver: primary, then the two sensitivity axes.

    The hierarchy is fixed in configuration, not chosen after the estimates were seen. The
    primary specification carries country and year effects and the primary block length; the
    sensitivities vary one thing each -- the fixed effects, or the block length -- so that a
    difference in the result can be attributed to the thing that changed.

    Drivers are never pooled. A suite is estimated separately for each of them.
    """
    settings = config or DynamicPanelConfig()
    gates = DynamicPanelGates(
        max_abs_persistence=settings.max_abs_persistence,
        min_effective_years=settings.min_effective_years,
        min_finite_multiplier_share=settings.min_finite_multiplier_share,
        min_convergence_share=settings.min_convergence_share,
    )

    plan: list[tuple[FixedEffects, int, str]] = [
        ("country_and_year", settings.block_length, "primary"),
        ("country", settings.block_length, "sensitivity_fixed_effects"),
    ]
    plan.extend(
        ("country_and_year", int(length), "sensitivity_block_length")
        for length in settings.sensitivity_block_lengths
    )

    results = tuple(
        estimate_dynamic_panel(
            panel,
            driver_column=driver_column,
            fixed_effects=effects,
            role=role,
            driver_lags=settings.driver_lags,
            block_length=length,
            replications=settings.replications,
            bias_correction_draws=settings.bias_correction_draws,
            bias_correction_iterations=settings.bias_correction_iterations,
            driscoll_kraay_lags=settings.driscoll_kraay_lags,
            seed=settings.seed,
            alpha=alpha,
            gates=gates,
        )
        for effects, length, role in plan
    )
    return DynamicPanelSuite(driver=driver_column, primary=results[0], specifications=results)
