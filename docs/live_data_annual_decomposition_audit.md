# Portugal annual labour-income decomposition: exploratory audit

## Status

This is a **non-publication exploratory reconstruction** for Portugal over 1996–2025. It does not
replace the verified-source-vintage workflow and it does not modify the v0.6 pre-results analysis
specification.

The annual employee-independent terms of the locked accounting identity are now available for every
year:

\[
\Delta\log w^{D1}
=\Delta\log Y+\Delta\log s_L-\Delta\log N+(\pi_Y-\pi_C).
\]

The exact locked employment denominator remains Eurostat national-accounts employees, domestic
concept (`SAL_DC`, `THS_PER`). The indexed web surfaces confirm the series and its coverage, but do
not expose the complete Portugal annual value vector in machine-readable text. Consequently:

- real-GDP, raw labour-share and relative-price annual contributions are available;
- the locked `SAL_DC` employment contribution is deliberately left missing;
- a full annual identity using INE Labour Force Survey employees is retained **only as a sensitivity**;
- every artifact in this exploratory annual layer has `publication_eligible = false`.

## Data construction

The annual level table contains 30 observations, 1996–2025.

- Nominal GDP: INE via PORDATA, million euro.
- Compensation of employees: INE via PORDATA, D.1 aggregate, million euro.
- GDP deflator: INE via PORDATA, 2021=1.
- HICP: Eurostat via the FRED table for series `CP0000PTM086NEST`, currently re-referenced to
  2025=100. The annual index is the arithmetic mean of the twelve monthly observations. The
  underlying 360 monthly observations used in the aggregation are frozen as a separate exploratory
  CSV.
- LFS employees: INE via PORDATA, thousand persons, sensitivity only.
- `SAL_DC`: intentionally unfilled until the exact Eurostat annual vector is obtained through the
  verified source-freeze path.

Eurostat's national-accounts metadata distinguishes the domestic from the national concept and
states that the domestic concept is consistent with GDP and other national-accounts variables. It
also reports `SAL_DC` in `nama_10_pe` as thousands of persons. This is why LFS employees cannot be
silently substituted into the locked result.

## Cumulative check

The annual components telescope exactly to the endpoint exercise. Over 1996–2025 the
employee-independent contributions are:

| Component | Cumulative log contribution |
|---|---:|
| Real GDP | +0.4086 |
| Raw D.1/GDP labour share | +0.0143 |
| Relative-price wedge | +0.1466 |
| Locked `SAL_DC` employment | unavailable |

The separate LFS sensitivity contributes -0.3409 from employee growth, producing +0.2286 log points
of HICP-deflated D.1 compensation per LFS employee, or about +25.68% in levels. Its maximum annual
accounting residual is approximately 2e-15, i.e. floating-point noise.

## What the annual path adds

The endpoint result made the raw D.1/GDP share look almost unchanged. The annual decomposition shows
that this stability is not monotone.

Selected observations, reported only to orient the full table:

- **2011:** real GDP contributes -0.0173 log points and the raw labour share -0.0182; the relative
  price term is also negative (-0.0376). The LFS-sensitivity total is -0.0581.
- **2012:** real GDP contributes -0.0414 and the raw labour share -0.0345. Falling LFS employment
  partly offsets those terms (+0.0479), but the LFS-sensitivity total remains -0.0591.
- **2020:** real GDP contributes -0.0856, while the raw labour share jumps +0.0641; falling LFS
  employment contributes +0.0224 and the relative-price term +0.0220. The LFS-sensitivity total is
  therefore positive (+0.0230) despite the output collapse.
- **2022:** real GDP contributes +0.0675, but the raw labour share (-0.0288), rising LFS employment
  (-0.0375) and consumer prices rising faster than the GDP deflator (-0.0260) more than absorb it;
  the LFS-sensitivity total is -0.0247.

These are accounting decompositions, not causal statements. In particular, a positive labour-share
term does not say *why* employee compensation rose relative to GDP, and the LFS employment term is
not the publication denominator.

## Descriptive period sums

For readability only, the LFS sensitivity can be summed over broad historical windows. These are
not model regimes and they are not used for inference.

| Growth years | Real GDP | Labour share | LFS employment | Relative prices | Total |
|---|---:|---:|---:|---:|---:|
| 1997–2007 | +0.2498 | -0.0266 | -0.1854 | +0.0698 | +0.1076 |
| 2008–2013 | -0.0798 | -0.0288 | +0.1034 | -0.0455 | -0.0508 |
| 2014–2019 | +0.1317 | +0.0071 | -0.1697 | +0.0569 | +0.0260 |
| 2020–2025 | +0.1069 | +0.0626 | -0.0892 | +0.0655 | +0.1457 |

The most useful qualitative result is therefore not that one component dominates permanently.
Portugal moves through different accounting configurations. Aggregate real output, the D.1 share,
employee counts and the producer/consumer price wedge can reinforce or offset one another in a
given year.

## Remaining promotion condition

The annual locked decomposition becomes complete only when all 30 `SAL_DC` levels are present and
verified under the existing source-freeze contract. `tools/exploratory_annual_decomposition.py`
already accepts an optional `employees_sal_dc_thousand` column; once complete, it activates the
locked annual employment and total terms without any estimator or configuration change.

Until then, the annual LFS calculation is a sensitivity and the annual locked total remains missing.
