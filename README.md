# GDP–Wage Transmission

[![CI](https://github.com/DiogoRibeiro7/gdp-wage-transmission/actions/workflows/ci.yml/badge.svg)](https://github.com/DiogoRibeiro7/gdp-wage-transmission/actions/workflows/ci.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22080269.svg)](https://doi.org/10.5281/zenodo.22080269)
[![Python 3.11–3.13](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/types-mypy%20strict-2a6db2.svg)](https://mypy-lang.org/)

A reproducible empirical research repository for studying how economic growth and labour productivity transmit into real wages, how quickly that transmission occurs, and whether the relationship changes over time.

The primary country is **Portugal**. The code is designed from the beginning to support cross-country robustness analysis.

## Contents

- [Research question](#research-question)
- [Manuscripts](#manuscripts)
- [Model stack](#model-stack)
- [Data sources](#data-sources)
- [Repository layout](#repository-layout)
- [Frozen Portugal reference audit](#frozen-portugal-reference-audit)
- [Installation](#installation)
- [Quick start without network access](#quick-start-without-network-access)
- [Publication source freeze](#publication-source-freeze)
- [Download official data](#download-official-data)
- [Core analysis](#core-analysis)
- [National-accounts decomposition](#national-accounts-decomposition)
- [Rebuild from frozen responses without network access](#rebuild-from-frozen-responses-without-network-access)
- [Statistical principles](#statistical-principles)
- [Notebooks](#notebooks)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Citation](#citation)
- [License](#license)
- [Status](#status)

## Research question

The project does **not** assume that GDP growth mechanically implies wage growth. The central empirical object is the wage-transmission elasticity

\[
\beta_t = \frac{\partial \log(w_t)}{\partial \log(p_t)},
\]

where \(w_t\) is a real wage or compensation measure and \(p_t\) is real labour productivity or real output per worker/hour.

The repository asks:

1. How much of productivity growth is transmitted to real wages?
2. How long does the transmission take?
3. Is there a stable long-run relationship between wages and productivity?
4. Did the transmission coefficient change structurally over time?
5. Do wages respond asymmetrically to expansions and contractions?
6. Is the result different for mean and median wages?
7. How much of wage growth can be decomposed into real GDP growth, labour-share changes, employment growth, and relative-price effects?


## Manuscripts

Two manuscripts draw on this repository: the GDP/productivity-to-wage transmission paper, and a
second on wage-distribution compression and structural breaks, which reuses the 2002-2024
Quadros de Pessoal wage-distribution panel and tests endogenous break dates separately from
historically specified 2008/2009 breaks.

Neither manuscript is kept in version control. The estimators, data layer and result artefacts
that feed them are what this repository tracks; the LaTeX sources, generated fragments and the
specification locks that bound them are maintained outside it.

The second strand is explicitly **post-hoc/exploratory**, not preregistered: the distribution
series were inspected before its protocol was fixed. Its current results select approximately
**2006** for D10/D1 and D9/D1, **2013** for D10/D5, and **2014** for mean/median. Forced 2008
and 2009 models still show negative post-break slopes, so the GFC remains a historically
meaningful candidate rather than the unique data-selected break.

## Model stack

The implementation deliberately progresses from accounting identities to increasingly flexible time-series models:

1. accounting decomposition;
2. stationarity and cointegration diagnostics;
3. distributed-lag growth regressions;
4. Engle–Granger error-correction model (ECM);
5. endogenous least-squares structural-break search;
6. formal single-break inference (sup-F with a wild-bootstrap p-value and a bootstrap
   break-date interval), reported separately from the BIC segmentation above;
7. state-space time-varying transmission elasticity, with block-bootstrap bands;
8. local projections, with block-bootstrap bands;
9. asymmetric transmission regression;
10. optional VECM impulse responses;
11. cross-country robustness, country by country, with a pooled fixed-effects estimate and
    country-clustered standard errors offered only as a secondary check.

The state-space and break models do **not** hard-code historical break dates. Historical events are used only after estimation to interpret estimated regimes. The break test searches over candidate dates, and its bootstrap p-value already accounts for that search, so a rejection is not an artefact of looking everywhere.

## Data sources

Primary harmonised sources:

- **OECD Average annual wages** (`OECD.ELS.SAE,DSD_EARNINGS@AV_AN_WAGE,1.0`)
- **OECD Productivity database** (`OECD.SDD.TPS,DSD_PDB@DF_PDB,2.0`), including GDP per hour worked

Secondary accounting source:

- **Eurostat** `nama_10_gdp` — GDP and compensation of employees
- **Eurostat** `nama_10_pe` — employees in the domestic concept
- **Eurostat** `prc_hicp_aind` — annual HICP indices
- **Eurostat** `nama_10_lp_ulc` — independent productivity robustness concepts

The download layer stores source extracts unchanged under `data/raw/` before canonicalisation. Raw snapshots retain the source unit, price-base, status fields, query URL and SHA-256 digest; the canonical panel is deliberately narrower. v0.4 also supports explicit source-vintage subdirectories, byte-preserving external imports, an auditable raw-snapshot registry, and complete offline reconstruction from frozen responses.

## Repository layout

```text
.
├── config/
│   ├── data_sources.yml
│   ├── models.yml
│   ├── project.yml
│   └── publication.yml
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   ├── reference/
│   └── sample/
├── docs/
├── notebooks/
├── results/
│   ├── figures/
│   └── tables/
├── src/wage_transmission/
│   ├── data/
│   ├── diagnostics/
│   └── models/
└── tests/
```

## Frozen Portugal reference audit

The repository now contains a frozen Portugal reference run for 1995–2025 using current OECD average annual real wages and GDP per hour worked. The reference dataset is stored under `data/reference/` with provenance and SHA-256 metadata. Because the execution environment could inspect OECD Data Explorer but could not make Python HTTP requests, this is a **reference transcription**, not the raw SDMX archive required for a publication release.

The first diagnostic run finds:

- full-period real wage growth: **+31.36%**;
- full-period GDP/hour growth: **+34.57%**;
- annual log-growth correlation: **0.087**;
- no Engle–Granger cointegration evidence at 5% (`p = 0.407`);
- exploratory break candidates at 2004 and 2013, but with segments too short for strong regime inference;
- latest state-space elasticity about `0.196` with standard error `0.424`, hence not distinguishable from zero;
- only five negative productivity changes, so the asymmetry specification is flagged as underpowered;
- local-projection horizons 4–8 are labelled exploratory because their effective sample falls below 25 observations.

See [`docs/portugal_empirical_audit.md`](docs/portugal_empirical_audit.md) for the interpretation audit. These are reduced-form diagnostics, not causal estimates.

### Matched annual specification

The frozen reference run pairs annual wages with GDP per hour, which is useful but not denominator-matched. The OECD data layer now also supports **GDP per person employed (`GDPEMP`)** as `productivity_per_worker`:

```bash
poetry run wage-transmission download-oecd-matched

poetry run wage-transmission analyse \
  --input data/processed/panel_per_worker.csv \
  --country PRT \
  --driver productivity_per_worker \
  --output results/portugal-per-worker
```

That matched series must be fetched from the official API for publication use; the repository does not fabricate a raw snapshot when network access is unavailable.

### Exploratory live-data check

A reporting-side exploratory run now uses values visible in current OECD Data Explorer indexed output for the common 1995–2023 Portugal sample, while leaving the v0.6 analysis lock unchanged. It is stored under `results/exploratory_live/` and is explicitly marked `publication_eligible: false`.

Under the locked primary distributed-lag specification, the cumulative coefficient is about `0.222` for GDP per person employed (HAC SE `0.543`, p = `0.684`) and about `-0.698` for GDP per hour (HAC SE `0.780`, p = `0.371`). Neither specification supports cointegration at 5%. The point of this exercise is therefore methodological: using the matched denominator does not, by itself, create evidence of a strong wage-transmission relationship. See [`docs/live_data_exploratory_audit.md`](docs/live_data_exploratory_audit.md).

### Exploratory endpoint decomposition

The same exploratory area now contains a 1996–2025 two-endpoint accounting decomposition. The
publication-specification denominator is Eurostat national-accounts employees under the domestic
concept (`SAL_DC`). Because the indexed-web route does not expose the 1996 Portugal `SAL_DC` level
with sufficient provenance, the locked decomposition deliberately leaves the employment term and
full total unresolved.

The employee-independent terms are `+40.86` log points from real GDP, `+1.43` from the raw D.1/GDP
labour share and `+14.66` from the GDP-deflator/HICP price wedge. The raw compensation share rises
from `47.44%` to `48.12%`. A separately labelled LFS-employee sensitivity adds `-34.09` log points
from employee growth and closes at `+22.86` log points, or about `+25.68%` in levels. The LFS
denominator is a national/resident concept and is **not** a substitute for `SAL_DC`; the complete
exercise remains `publication_eligible: false`. See
[`docs/live_data_decomposition_audit.md`](docs/live_data_decomposition_audit.md).

### Exploratory annual decomposition

The endpoint exercise is now expanded to a full **1996–2025 annual accounting path** without
changing any locked estimator or configuration. Nominal GDP, D.1 compensation, the GDP deflator
and LFS employees use the same exploratory INE/PORDATA series; annual HICP is constructed from a
frozen 360-row Eurostat/FRED monthly table, with exactly twelve monthly observations averaged for
each calendar year.

The employee-independent locked terms are complete for all 29 annual changes. The exact Eurostat
`SAL_DC` vector is still unavailable through the indexed-web surface, so the locked employment term
and locked annual total remain missing by construction. A complete LFS-employee identity is retained
only as a concept-mismatched sensitivity and is marked `publication_eligible: false`.

The annual path shows why the almost unchanged endpoint D.1/GDP share should not be interpreted as
a constant allocation mechanism. In the LFS sensitivity, 2011 and 2012 have totals of about
`-0.0581` and `-0.0591` log points. In 2020 real GDP contributes `-0.0856`, while the raw labour
share contributes `+0.0641`, lower LFS employment `+0.0224`, and the relative-price wedge `+0.0220`,
leaving a small positive total. In 2022 the corresponding terms are `+0.0675`, `-0.0288`, `-0.0375`
and `-0.0260`, producing a negative total. These are descriptive accounting contributions, not
causal estimates. See
[`docs/live_data_annual_decomposition_audit.md`](docs/live_data_annual_decomposition_audit.md).

### Exploratory wage distribution

The exploratory layer now adds a coherent **2002–2024 mean/median/decile panel** from GEP/MTSSS
`Quadros de Pessoal`. The population is deliberately narrow and consistent: mainland-Portugal
full-time employees with complete remuneration in October. The historical 2002–2014 and latest
2014–2024 official chronological tables are stored separately and must agree exactly at their
duplicated 2014 bridge year before the panel is built.

Because the wage observation is for October, nominal gain is deflated with **October HICP** rather
than annual-average HICP. Over 2002–2024, exploratory real monthly gain grows about `25.0%` at the
mean, `30.9%` at the median, `55.2%` in the bottom decile and `13.4%` in the top decile. The ratio
of average D10 to average D1 gain compresses from `6.83` to `4.99`, while mean/median falls from
`1.392` to `1.329`. Thus the covered post-2002 employee distribution does not show the typical
worker falling progressively behind the mean; it shows substantial compression, particularly from
2008 onward. On the common 2002–2023 endpoint with the exploratory OECD GDP/person-employed series,
productivity grows `19.12%` and real mean gain `18.89%`, but the median grows `24.09%`, D1 `47.12%`
and D10 only `8.41%`. Aggregate co-movement therefore hides very different distributional incidence.

These are employee-pay distribution facts, not household-income inequality and not causal evidence
about minimum-wage policy or productivity. The complete layer remains `publication_eligible: false`.
See [`docs/live_data_wage_distribution_audit.md`](docs/live_data_wage_distribution_audit.md).

## Installation

The project targets Python 3.11–3.13 and uses [Poetry](https://python-poetry.org/) 2.x. Dependencies
are pinned in `poetry.lock`, so an install reproduces the exact versions CI uses.

```bash
poetry install
poetry run pre-commit install    # optional, but recommended for contributors
```

Run the quality gates, exactly as CI does:

```bash
make check                       # ruff check + mypy + pytest
```

or individually:

```bash
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src
poetry run pytest --cov=wage_transmission
```

## Quick start without network access

A deterministic synthetic dataset is included only to exercise the pipeline. It is **not empirical evidence**.

```bash
poetry run wage-transmission analyse \
  --input data/sample/synthetic_portugal.csv \
  --country PRT \
  --output results/demo
```

## Publication source freeze

Before downloading a publication vintage, export the exact request plan:

```bash
poetry run wage-transmission export-source-queries \
  --vintage 2026-08-22 \
  --output data/query_manifests/2026-08-22.json
```

The current project configuration produces **63 official requests**: three OECD queries and five Eurostat decomposition queries for each of twelve European countries. The release includes this manifest plus `data/query_manifests/2026-08-22.audit.csv`. The audit currently says `missing` for every request because this execution container has no outbound DNS; that is deliberate and prevents a reference transcription from being promoted to a raw API freeze.

### Internet-enabled publication freeze

v0.5 added a network-safe fetch command and `.github/workflows/source-freeze.yml`. On an internet-enabled machine, the exact manifest can now be fetched directly without switching back to the older ad-hoc download path:

```bash
poetry run wage-transmission fetch-source-freeze \
  --query-manifest data/query_manifests/2026-08-22.json \
  --output data/query_manifests/2026-08-22.fetch.csv \
  --audit-output data/query_manifests/2026-08-22.audit.csv \
  --registry data/raw/SNAPSHOT_REGISTRY.csv \
  --strict
```

The fetcher stores the exact response bytes, retries only transient transport/HTTP failures, rejects obvious HTML/error payloads before storage, and reuses already verified snapshots without a second request. The audit also checks manifest metadata (URL, query id, dataset/flow/measure when present), so a self-consistent hash is not enough if the file belongs to a different source request.

The GitHub Actions workflow performs the complete publication path on an internet-enabled runner: query manifest → immutable raw freeze → strict audit → offline panel reconstruction → Portugal/cross-country analyses → publication dossier → Ruff/mypy/pytest → checksummed Actions artifact. See [`docs/github_source_freeze.md`](docs/github_source_freeze.md).

On a network-enabled machine, downloads should use an explicit vintage directory:

```bash
poetry run wage-transmission download-oecd-matched --vintage 2026-08-22
poetry run wage-transmission download-decomposition --vintage 2026-08-22
```

If a response was downloaded externally, import its bytes directly from the query manifest:

```bash
poetry run wage-transmission import-query-snapshot \
  --input ~/Downloads/oecd-response.csv \
  --query-manifest data/query_manifests/2026-08-22.json \
  --query-id oecd_gdpemp
```

Then enforce the release gate:

```bash
poetry run wage-transmission audit-source-freeze \
  --query-manifest data/query_manifests/2026-08-22.json \
  --output data/query_manifests/2026-08-22.audit.csv \
  --strict

poetry run wage-transmission audit-snapshots \
  --raw-dir data/raw \
  --output data/raw/SNAPSHOT_REGISTRY.csv
```

See [`docs/source_vintages.md`](docs/source_vintages.md) for the full freeze/revision protocol.

## Download official data

```bash
poetry run wage-transmission download-data --vintage 2026-08-22
```

The OECD client uses the current SDMX REST API and requests `csvfilewithlabels`; Eurostat uses the Statistics API. OECD wage queries pin the constant-price code `Q`. Eurostat requests pin the requested year range with `sinceTimePeriod` and `untilTimePeriod`. Exact raw responses are persisted before canonicalisation.

## Core analysis

For a processed panel with columns

```text
country, year, real_wage, productivity
```

run:

```bash
poetry run wage-transmission analyse \
  --input data/processed/panel.csv \
  --country PRT \
  --driver productivity \
  --output results/portugal-productivity

# Aggregate-GDP robustness run, when `real_gdp` is available:
poetry run wage-transmission analyse \
  --input data/processed/panel.csv \
  --country PRT \
  --driver real_gdp \
  --output results/portugal-gdp

# Country-specific robustness estimates, without pooled-homogeneity assumptions:
poetry run wage-transmission analyse-panel \
  --input data/processed/panel.csv \
  --driver productivity \
  --output results/cross_country/country_estimates.csv
```

`analyse-panel` writes the country table first and then a secondary `country_estimates.summary.json` containing the median transmission, inverse-variance fixed/random-effects summaries, Cochran's Q and I-squared. The summary is explicitly a robustness aggregation, not a substitute for the country estimates.

## National-accounts decomposition

The Eurostat layer now implements the exact accounting identity

\[
\Delta\log w^{D1}
=\Delta\log Y+\Delta\log s_L-\Delta\log N+(\pi_Y-\pi_C).
\]

Download the five aligned inputs and a source-by-source coverage audit:

```bash
poetry run wage-transmission download-decomposition
```

This writes both `data/processed/decomposition_inputs.csv` and
`data/processed/decomposition_coverage.csv`. The coverage table is produced **before** the common-sample
inner join, so a missing source-year cannot disappear silently from the analysis panel.

Then run Portugal or the full European decomposition panel:

```bash
poetry run wage-transmission decompose \
  --input data/processed/decomposition_inputs.csv \
  --country PRT \
  --output results/decomposition/PRT

poetry run wage-transmission decompose \
  --input data/processed/decomposition_inputs.csv \
  --output results/decomposition/all
```

The inputs are current-price GDP (`B1GQ`), chain-linked real GDP, compensation of employees (`D1`), employees in the domestic concept (`SAL_DC`) and the all-items HICP annual-average index. `SAL_DC` is intentional: total employment would add self-employed persons to the denominator. The decomposition's wage concept is **real compensation per employee**, not the OECD average annual wage, so the two empirical layers remain separate.

Each one-country decomposition also writes annual and cumulative contribution figures. The notebook `04_labour_share_decomposition.ipynb` consumes the processed panel and package functions rather than reimplementing the identity.

The analysis commands write model summaries, machine-readable reliability flags, figures, and run manifests containing package/version information plus input hashes. The notebooks consume those outputs rather than duplicating modelling logic.

## Rebuild from frozen responses without network access

The processed empirical panels can be regenerated from verified raw bytes only:

```bash
poetry run wage-transmission build-oecd-from-snapshots \
  --wage-snapshot data/raw/2026-08-22/oecd_average_wages_1995_2025.csv \
  --productivity-snapshot data/raw/2026-08-22/oecd_gdpemp_1995_2025.csv \
  --measure GDPEMP \
  --output data/processed/2026-08-22/panel_per_worker.csv

poetry run wage-transmission build-decomposition-from-snapshots \
  --raw-dir data/raw/2026-08-22 \
  --output data/processed/2026-08-22/decomposition_inputs.csv
```

Metadata verification is mandatory by default. A development-only `--allow-unverified` escape hatch exists but must not be used for publication results.

Official revisions are measurable rather than silently absorbed:

```bash
poetry run wage-transmission compare-vintages \
  --old data/processed/2026-08-22/panel_per_worker.csv \
  --new data/processed/2026-11-01/panel_per_worker.csv \
  --values real_wage,productivity_per_worker \
  --output results/revisions/2026-08-22_vs_2026-11-01.csv
```

The revision table labels each observation `unchanged`, `revised`, `added`, or `dropped` and writes per-series revision summaries.

## Statistical principles

- Levels are never regressed mechanically without checking integration/cointegration. Both levels and first differences receive ADF/KPSS diagnostics.
- The ECM is estimated as a conditional specification, but its long-run coefficient is flagged as unsupported when the Engle–Granger diagnostic does not support cointegration at 5%.
- Growth regressions use HAC covariance estimates.
- Break dates are estimated, not selected to match a narrative.
- Local projections are interpreted as dynamic associations unless a credible shock-identification strategy is supplied.
- VECM/VAR impulse responses are not labelled causal without identification.
- Mean-wage and median-wage analyses are kept separate.
- Price bases and deflators are explicit in every processed series.
- Revisions to official data are expected; raw snapshots and metadata make runs auditable.
- Flexible specifications are accompanied by pre-specified interpretation gates for cointegration, shock balance, break-segment size, local-projection effective sample size, and state-space precision.

## Notebooks

Four notebooks under [`notebooks/`](notebooks/) consume the package; none of them reimplements a
transformation. They are **committed with their outputs**, so the estimator results are readable
on GitHub without installing anything or waiting for a bootstrap to finish.

| Notebook | Contents |
| --- | --- |
| [01_data_audit](notebooks/01_data_audit.ipynb) | Coverage, gaps, provenance, and the schema guard rejecting a mixed price base |
| [02_portugal_core_models](notebooks/02_portugal_core_models.ipynb) | The full stack on the frozen Portugal extract: reliability flags first, then the primary estimand, the BIC segmentation against the sup-F break test, and HAC intervals against bootstrap bands |
| [03_cross_country_robustness](notebooks/03_cross_country_robustness.ipynb) | Country-specific estimates and heterogeneity before the pooled fixed-effects estimate |
| [04_labour_share_decomposition](notebooks/04_labour_share_decomposition.ipynb) | The accounting identity, its components, and a check that the residual closes |

Notebooks 01 and 02 run on the tracked Portugal reference extract. Notebooks 03 and 04 need a
processed panel that is not tracked; without it they fall back to clearly labelled **simulated**
frames that exercise the interface and are not evidence about any economy.

Their source lives in [`tools/build_notebooks.py`](tools/build_notebooks.py) rather than in the
notebook JSON, so a change is reviewable as a Python diff. Rebuild and re-execute all four with:

```bash
make notebooks
```

## Documentation

Detailed notes live under [`docs/`](docs/):

| Document | Contents |
| --- | --- |
| [research_design.md](docs/research_design.md) | Identification strategy and specification hierarchy |
| [model_notes.md](docs/model_notes.md) | Estimator-by-estimator implementation notes |
| [data_dictionary.md](docs/data_dictionary.md) | Canonical panel schema and variable definitions |
| [source_vintages.md](docs/source_vintages.md) | Vintage layout, snapshot registry and revision handling |
| [reproducibility.md](docs/reproducibility.md) | How to reproduce a published run end to end |
| [specification_lock.md](docs/specification_lock.md) | What the specification lock binds, and why its artefact stays untracked |
| [paper_generation.md](docs/paper_generation.md) | Building the paper-facing report packet |
| [github_source_freeze.md](docs/github_source_freeze.md) | Running the internet-enabled freeze workflow |
| [portugal_empirical_audit.md](docs/portugal_empirical_audit.md) | Frozen Portugal reference audit |
| [zenodo_archiving.md](docs/zenodo_archiving.md) | Minting a DOI for a release, and the release checklist |

Live-data audit notes for the exploratory revisions are also in `docs/`, one file per revision.

## Contributing

Contributions are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) describes the development setup, the
quality gates, and — most importantly — the reproducibility rules that keep published numbers
defensible: data is never committed, raw snapshots are immutable, and specification locks are not
edited to make a result fit.

Please also read the [code of conduct](CODE_OF_CONDUCT.md). Security-relevant reports follow
[SECURITY.md](SECURITY.md); data and reproducibility problems have their own issue template.

## Citation

Archived on Zenodo. Cite [10.5281/zenodo.22080269](https://doi.org/10.5281/zenodo.22080269) — this is the
**concept DOI**, which covers all versions and always resolves to the newest one. Use it
everywhere, including in papers; per-version DOIs exist on Zenodo but are not the citation
this project asks for.

If you use this software, cite it through [CITATION.cff](CITATION.cff), together with the study
release used for the data snapshot. GitHub renders a ready-made citation from that file under
**Cite this repository**.

## License

Released under the MIT License. See [LICENSE](LICENSE).

Note that the licence covers the code in this repository. Data retrieved from OECD and Eurostat
remains subject to those providers' own terms of use.

## Status

**v0.6** contains the complete core time-series stack, reliability guardrails, frozen Portugal reference audit, denominator-explicit OECD productivity drivers, exact Eurostat labour-share accounting decomposition, country-specific cross-country estimates with HAC uncertainty, and the source-vintage/revision layer.

The publication hierarchy is fixed in configuration: the primary annual specification is GDP per person employed versus real annual wages, the cumulative distributed-lag coefficient is the primary inferential estimand, and flexible models are reliability-gated supporting evidence. Those choices live in `config/publication.yml`; the specification locks that previously bound them to a source freeze are maintained outside version control along with the manuscripts.

The configured `2026-08-22` manifest still contains **63 official source queries**. Its bundled audit deliberately reports all 63 as missing because this local environment cannot perform the network fetches; the GitHub Actions workflow is the reproducible internet-enabled path for producing the untouched raw vintage, processed panels, empirical outputs and locked publication dossier.

Validation is **72/72 tests passing**. The annual-decomposition tests cover missing and complete `SAL_DC` paths, exact accounting closure, concept labelling and annual-input contracts; the dossier reliability gates remain in the suite. Ruff (lint and format) and mypy in strict mode run clean locally and in CI on Python 3.11, 3.12 and 3.13, in addition to the publication workflow's release gates.
