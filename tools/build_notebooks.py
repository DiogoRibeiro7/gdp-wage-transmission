"""Regenerate the analysis notebooks from a single source of truth.

Notebooks are consumers: they call the package and read its results, and they never
reimplement a transformation. Keeping their source here rather than hand-editing JSON keeps
that boundary visible, keeps the four notebooks consistent with one another, and makes a
change reviewable as a diff of Python rather than of embedded notebook JSON.

Run ``make notebooks`` to rebuild and execute them.
"""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

NOTEBOOK_DIR = Path("notebooks")

KERNEL = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}


def _notebook(cells: list[nbformat.NotebookNode]) -> nbformat.NotebookNode:
    notebook = new_notebook(cells=cells, metadata=KERNEL)
    return notebook


def data_audit() -> nbformat.NotebookNode:
    return _notebook(
        [
            new_markdown_cell(
                "# 01 — Data audit\n"
                "\n"
                "What is in the panel, where it came from, and what would have to be true for it\n"
                "to be usable in a publication.\n"
                "\n"
                "The notebook prefers the processed panel built from a verified source freeze and\n"
                "falls back to the frozen Portugal reference extract, printing which one it used.\n"
                "That distinction matters: the reference extract is a **transcription** from the\n"
                "OECD Data Explorer, not an untouched SDMX payload, and it is adequate for\n"
                "development but not for a published number."
            ),
            new_code_cell(
                "from pathlib import Path\n"
                "\n"
                "import json\n"
                "import pandas as pd\n"
                "\n"
                "PROCESSED = Path('../data/processed/panel.csv')\n"
                "REFERENCE = Path('../data/reference/portugal_oecd_1995_2025.csv')\n"
                "\n"
                "source = PROCESSED if PROCESSED.exists() else REFERENCE\n"
                "panel = pd.read_csv(source)\n"
                "print(f'Source in use: {source}')\n"
                "print(f'Publication-grade source: {source == PROCESSED}')\n"
                "panel.head()"
            ),
            new_code_cell(
                "panel.groupby('country').agg(\n"
                "    first_year=('year', 'min'),\n"
                "    last_year=('year', 'max'),\n"
                "    n_observations=('year', 'size'),\n"
                ")"
            ),
            new_markdown_cell(
                "## Levels\n"
                "\n"
                "Both series must be strictly positive before logging, and gaps matter more than\n"
                "outliers here: a missing year breaks the growth rate on both sides of it."
            ),
            new_code_cell("panel[['real_wage', 'productivity']].describe()"),
            new_code_cell(
                "# A year gap is invisible in a describe() table but fatal to a growth series.\n"
                "years = panel['year'].to_numpy()\n"
                "gaps = sorted(set(range(years.min(), years.max() + 1)) - set(years.tolist()))\n"
                "print(f'Missing years: {gaps if gaps else \"none\"}')\n"
                "print(f'Duplicated years: {int(panel[\"year\"].duplicated().sum())}')"
            ),
            new_markdown_cell(
                "## Provenance\n"
                "\n"
                "Every tracked extract carries a provenance record: where it came from, when, and\n"
                "the digest of the bytes. A number that cannot be traced to one of these is not\n"
                "publishable."
            ),
            new_code_cell(
                "provenance_path = REFERENCE.with_suffix('.provenance.json')\n"
                "if provenance_path.exists():\n"
                "    provenance = json.loads(provenance_path.read_text(encoding='utf-8'))\n"
                "    for key, value in provenance.items():\n"
                "        if not isinstance(value, (dict, list)):\n"
                "            print(f'{key}: {value}')\n"
                "else:\n"
                "    print('No provenance record found next to the reference extract.')"
            ),
            new_markdown_cell(
                "## The schema guard\n"
                "\n"
                "Canonicalisation reduces a source response to country, year and one value column,\n"
                "discarding the unit, price base and observation status. `audit_series_schema`\n"
                "records those attributes first, and refuses to let a series mix measurement\n"
                "concepts.\n"
                "\n"
                "The cell below demonstrates the guard on two small frames shaped like an OECD\n"
                "response. They illustrate the failure mode; they are not data."
            ),
            new_code_cell(
                "from wage_transmission.data.schema_audit import audit_series_schema\n"
                "\n"
                "clean = pd.DataFrame(\n"
                "    {\n"
                "        'REF_AREA': ['PRT', 'PRT'],\n"
                "        'TIME_PERIOD': [2020, 2021],\n"
                "        'OBS_VALUE': [40.0, 41.0],\n"
                "        'Unit of measure': ['US dollars, PPP converted'] * 2,\n"
                "        'Price base': ['Constant prices'] * 2,\n"
                "        'Observation status': ['Normal value', 'Provisional value'],\n"
                "    }\n"
                ")\n"
                "schema = audit_series_schema(clean, source='DEMO', value_name='productivity')\n"
                "print('units             :', schema.units)\n"
                "print('price bases       :', schema.price_bases)\n"
                "print('observation status:', schema.observation_statuses)\n"
                "print('attributes absent :', schema.attributes_absent)"
            ),
            new_code_cell(
                "mixed = clean.copy()\n"
                "mixed.loc[0, 'Price base'] = 'Current prices'\n"
                "try:\n"
                "    audit_series_schema(mixed, source='DEMO', value_name='productivity')\n"
                "except ValueError as error:\n"
                "    print(f'Rejected, as it should be:\\n  {error}')"
            ),
            new_markdown_cell(
                "## What this notebook does not establish\n"
                "\n"
                "A clean audit says the panel is internally coherent. It says nothing about\n"
                "whether the wage and productivity concepts are comparable across the countries\n"
                "in it, and nothing about whether the deflators align. Those are checked at the\n"
                "source-freeze stage, not here."
            ),
        ]
    )


def portugal_core_models() -> nbformat.NotebookNode:
    return _notebook(
        [
            new_markdown_cell(
                "# 02 — Portugal core models\n"
                "\n"
                "The full estimator stack for one country, in the order the research design\n"
                "intends: reliability flags first, then coefficients.\n"
                "\n"
                "Reading the coefficients before the flags is the mistake this ordering exists to\n"
                "prevent. A flexible model fitted to thirty annual observations will always return\n"
                "a number; the flags say whether that number carries information."
            ),
            new_code_cell(
                "from pathlib import Path\n"
                "\n"
                "import pandas as pd\n"
                "\n"
                "from wage_transmission.config import load_models_config\n"
                "from wage_transmission.pipeline import analyse_country\n"
                "\n"
                "PROCESSED = Path('../data/processed/panel.csv')\n"
                "REFERENCE = Path('../data/reference/portugal_oecd_1995_2025.csv')\n"
                "\n"
                "source = PROCESSED if PROCESSED.exists() else REFERENCE\n"
                "panel = pd.read_csv(source)\n"
                "portugal = panel.loc[panel['country'] == 'PRT'].copy()\n"
                "config = load_models_config(Path('../config/models.yml'))\n"
                "print(f'Source in use: {source}')\n"
                "print(f'Observations: {len(portugal)}')\n"
                "print('Bootstrap inference enabled:', config.inference.enabled)"
            ),
            new_code_cell(
                "# The pipeline runs every estimator and serialises the results. Bootstrap\n"
                "# replications dominate the runtime; set inference.enabled to false in\n"
                "# config/models.yml for a fast exploratory pass.\n"
                "results = analyse_country(\n"
                "    portugal,\n"
                "    Path('../results/notebook_portugal'),\n"
                "    model_config=config,\n"
                ")\n"
                "results['reliability']"
            ),
            new_markdown_cell(
                "## Sample adequacy\n"
                "\n"
                "The audit reports what the sample can support before any model is interpreted."
            ),
            new_code_cell("results['empirical_audit']"),
            new_markdown_cell(
                "## Long run: cointegration and the ECM\n"
                "\n"
                "The ECM's long-run coefficient is a **conditional** quantity. If the\n"
                "Engle–Granger diagnostic does not support cointegration, the long-run elasticity\n"
                "is not evidence of a long-run relationship, and the flag below says so."
            ),
            new_code_cell(
                "cointegration = results['diagnostics']['cointegration']\n"
                "print('Engle-Granger p-value:', round(cointegration['p_value'], 4))\n"
                "print('Supported at 5%:', results['diagnostics']['cointegration_supported_5pct'])\n"
                "print()\n"
                "results['ecm']"
            ),
            new_markdown_cell(
                "## Primary estimand: cumulative distributed-lag transmission\n"
                "\n"
                "This is the pre-specified primary quantity. Everything below it is supporting\n"
                "evidence, reliability-gated."
            ),
            new_code_cell("results['distributed_lag']"),
            new_markdown_cell(
                "## Breaks: two different questions\n"
                "\n"
                "The BIC segmentation asks *how many regimes fit best*. It always returns a\n"
                "partition, so it cannot tell you whether a break exists at all.\n"
                "\n"
                "The sup-F test asks *is there evidence of a break*, with a wild-bootstrap p-value\n"
                "computed by re-running the entire date search on each replication — so the\n"
                "p-value already accounts for having looked at every candidate date. The two are\n"
                "reported separately because they answer different questions."
            ),
            new_code_cell("results['structural_breaks']"),
            new_code_cell(
                "inference = results['break_inference']\n"
                "if inference is None:\n"
                "    print('Bootstrap inference is disabled in config/models.yml.')\n"
                "else:\n"
                "    print(f'Break year          : {inference.break_year}')\n"
                "    print(f'Bootstrap interval  : {inference.break_year_lower}'\n"
                "          f'-{inference.break_year_upper}')\n"
                "    print(f'sup-F               : {inference.sup_f:.3f}')\n"
                "    print(f'p-value             : {inference.p_value:.4f}')\n"
                "    print(f'Elasticity before   : {inference.pre_break_elasticity:.3f}')\n"
                "    print(f'Elasticity after    : {inference.post_break_elasticity:.3f}')\n"
                "    print(f'Verdict             : {inference.interpretation}')"
            ),
            new_markdown_cell(
                "## Time-varying elasticity\n"
                "\n"
                "The filtered standard errors condition on the estimated variance parameters and\n"
                "ignore the uncertainty in estimating them — which matters, because the state\n"
                "variance is exactly what governs how much the elasticity is allowed to move. The\n"
                "block-bootstrap band re-estimates the whole model per replication.\n"
                "\n"
                "The band is pointwise. It does not license a claim about the path as a whole,\n"
                "such as a decline between two particular years."
            ),
            new_code_cell(
                "band = results['time_varying_elasticity_bands']\n"
                "state = results['state_space']\n"
                "if band is None:\n"
                "    print('Bootstrap bands are disabled in config/models.yml.')\n"
                "else:\n"
                "    comparison = pd.DataFrame(\n"
                "        {\n"
                "            'year': band.year,\n"
                "            'elasticity': band.estimate,\n"
                "            'filtered_lower': state.elasticity - 1.96 * state.elasticity_std_error,\n"
                "            'filtered_upper': state.elasticity + 1.96 * state.elasticity_std_error,\n"
                "            'bootstrap_lower': band.lower_95,\n"
                "            'bootstrap_upper': band.upper_95,\n"
                "        }\n"
                "    )\n"
                "    comparison['filtered_width'] = (\n"
                "        comparison['filtered_upper'] - comparison['filtered_lower']\n"
                "    )\n"
                "    comparison['bootstrap_width'] = (\n"
                "        comparison['bootstrap_upper'] - comparison['bootstrap_lower']\n"
                "    )\n"
                "    display(comparison.tail(8).round(3))\n"
                "    print(\n"
                "        'Median width, filtered vs bootstrap: '\n"
                "        f'{comparison[\"filtered_width\"].median():.3f} vs '\n"
                "        f'{comparison[\"bootstrap_width\"].median():.3f}'\n"
                "    )"
            ),
            new_markdown_cell(
                "## Local projections\n"
                "\n"
                "Local-projection windows overlap, so the effective sample at long horizons is far\n"
                "smaller than the nominal one and the HAC errors are optimistic there. Comparing\n"
                "the two interval widths shows how much.\n"
                "\n"
                "These are dynamic associations. Calling them impulse responses would require an\n"
                "identified productivity shock, which this design does not claim."
            ),
            new_code_cell(
                "bands = results['local_projection_bands']\n"
                "points = results['local_projections']\n"
                "if not bands:\n"
                "    print('Bootstrap bands are disabled in config/models.yml.')\n"
                "else:\n"
                "    frame = pd.DataFrame(\n"
                "        {\n"
                "            'horizon': [p.horizon for p in points],\n"
                "            'estimate': [p.estimate for p in points],\n"
                "            'hac_width': [(p.upper_95 - p.lower_95) for p in points],\n"
                "            'bootstrap_width': [(b.upper_95 - b.lower_95) for b in bands],\n"
                "            'nobs': [p.nobs for p in points],\n"
                "        }\n"
                "    )\n"
                "    frame['bootstrap_wider_by'] = frame['bootstrap_width'] / frame['hac_width']\n"
                "    display(frame.round(3))"
            ),
            new_markdown_cell("## Figures"),
            new_code_cell(
                "from IPython.display import Image\n"
                "\n"
                "Image(filename='../results/notebook_portugal/time_varying_elasticity.png')"
            ),
            new_code_cell("Image(filename='../results/notebook_portugal/local_projections.png')"),
            new_markdown_cell(
                "## What this notebook does not establish\n"
                "\n"
                "None of the above is causal. The transmission elasticity is an association\n"
                "between two series that are jointly determined; a break locates a date without\n"
                "explaining it; and the reliability flags mark where the sample is too short to\n"
                "support the flexible specifications at all."
            ),
        ]
    )


def cross_country() -> nbformat.NotebookNode:
    return _notebook(
        [
            new_markdown_cell(
                "# 03 — Cross-country robustness\n"
                "\n"
                "Identical specifications estimated separately for each country, before any\n"
                "pooled model is considered.\n"
                "\n"
                "The order is deliberate. A pooled coefficient imposes homogeneous transmission\n"
                "dynamics; where countries genuinely differ, it is a weighted average of different\n"
                "processes rather than a common parameter. Looking at the spread first makes that\n"
                "visible instead of hiding it in one number."
            ),
            new_code_cell(
                "from pathlib import Path\n"
                "\n"
                "import numpy as np\n"
                "import pandas as pd\n"
                "\n"
                "from wage_transmission.config import load_models_config\n"
                "from wage_transmission.cross_country import (\n"
                "    estimate_country_robustness,\n"
                "    summarise_country_robustness,\n"
                ")\n"
                "from wage_transmission.models.dynamic_panel import estimate_dynamic_panel\n"
                "\n"
                "PROCESSED = Path('../data/processed/panel.csv')\n"
                "ILLUSTRATIVE = not PROCESSED.exists()\n"
                "\n"
                "if not ILLUSTRATIVE:\n"
                "    panel = pd.read_csv(PROCESSED)\n"
                "else:\n"
                "    # No processed multi-country panel in this checkout. The frame below exists\n"
                "    # only to exercise the interface: it is SIMULATED, and nothing estimated\n"
                "    # from it is evidence about any real country.\n"
                "    rng = np.random.default_rng(20260824)\n"
                "    years = np.arange(1995, 2025)\n"
                "    frames = []\n"
                "    for code, beta in {'AAA': 0.4, 'BBB': 0.7, 'CCC': 0.9, 'DDD': 1.1}.items():\n"
                "        growth = rng.normal(0.017, 0.017, len(years))\n"
                "        wage_growth = 0.001 + beta * growth + rng.normal(0, 0.007, len(years))\n"
                "        frames.append(\n"
                "            pd.DataFrame(\n"
                "                {\n"
                "                    'country': code,\n"
                "                    'year': years,\n"
                "                    'real_wage': 20000 * np.exp(np.cumsum(wage_growth)),\n"
                "                    'productivity': 30 * np.exp(np.cumsum(growth)),\n"
                "                }\n"
                "            )\n"
                "        )\n"
                "    panel = pd.concat(frames, ignore_index=True)\n"
                "\n"
                "config = load_models_config(Path('../config/models.yml'))\n"
                "print('SIMULATED DATA — NOT EVIDENCE' if ILLUSTRATIVE else f'Source: {PROCESSED}')\n"
                "print(f'Countries: {sorted(panel[\"country\"].unique())}')"
            ),
            new_markdown_cell("## Country-specific estimates"),
            new_code_cell(
                "estimates = estimate_country_robustness(panel, config=config)\n"
                "columns = [\n"
                "    'country',\n"
                "    'nobs',\n"
                "    'distributed_lag_cumulative',\n"
                "    'distributed_lag_cumulative_se',\n"
                "    'cointegration_5pct',\n"
                "]\n"
                "estimates.loc[:, columns].sort_values('distributed_lag_cumulative').round(3)"
            ),
            new_markdown_cell(
                "## How different are they?\n"
                "\n"
                "`I²` is the share of the observed variation in country estimates that exceeds what\n"
                "sampling error alone would produce. A high value means a pooled number is\n"
                "describing heterogeneous processes."
            ),
            new_code_cell(
                "summary = summarise_country_robustness(estimates)\n"
                "print(f'Countries              : {summary.n_countries}')\n"
                "print(f'Median transmission    : {summary.median_cumulative_transmission:.3f}')\n"
                "print(f'Interquartile range    : {summary.q25_cumulative_transmission:.3f}'\n"
                "      f' to {summary.q75_cumulative_transmission:.3f}')\n"
                "print(f'Random-effects estimate: {summary.random_effect_estimate:.3f}'\n"
                "      f' (se {summary.random_effect_std_error:.3f})')\n"
                "print(f'I-squared              : {summary.i_squared_percent:.1f}%')\n"
                "print(f'Verdict                : {summary.interpretation}')"
            ),
            new_markdown_cell(
                "## Only now: the pooled dynamic panel\n"
                "\n"
                "A pooled estimate is only comparable with the country estimates above if it\n"
                "targets the same quantity. The country models report a **cumulative multiplier**,\n"
                "so the panel uses the same dynamic structure and reports\n"
                "$\\Theta = (\\sum_j \\beta_j)/(1-\\gamma)$ rather than a contemporaneous slope.\n"
                "\n"
                "Earlier releases of this notebook showed a static pooled regression beside the\n"
                "cumulative country estimates. That comparison was wrong: the two are different\n"
                "objects on different samples, and the static version is no longer reported.\n"
                "\n"
                "A lagged dependent variable beside fixed effects biases least squares downward by\n"
                "order $1/T$, so the estimate is bias-corrected; the uncorrected value is printed\n"
                "beside it to show the size of the correction. **The correction addresses dynamic\n"
                "fixed-effects bias only.** It does nothing about contemporaneous endogeneity\n"
                "between productivity and wages."
            ),
            new_code_cell(
                "# The published figures use 4,999 replications and take minutes per specification.\n"
                "# This notebook uses far fewer so it stays runnable; the release artefact under\n"
                "# results/vintages/<vintage>/ carries the numbers the paper reports.\n"
                "panel_result = estimate_dynamic_panel(\n"
                "    panel,\n"
                "    fixed_effects='country_and_year',\n"
                "    replications=299,\n"
                "    bias_correction_draws=100,\n"
                ")\n"
                "low, high = panel_result.corrected_multiplier_ci\n"
                "print(f'Observations      : {panel_result.nobs}"
                " ({panel_result.n_countries} countries,'\n"
                "      f' {panel_result.n_effective_years} years)')\n"
                "print(f'Uncorrected Theta : {panel_result.lsdv_multiplier:.3f}"
                " (gamma {panel_result.lsdv_persistence:.3f})')\n"
                "print(f'Corrected Theta   : {panel_result.corrected_multiplier:.3f}"
                " (gamma {panel_result.corrected_persistence:.3f})')\n"
                "print(f'Bootstrap 95%     : {low:.3f} to {high:.3f}')\n"
                "print(f'Gates             :"
                ' {panel_result.gate_failures or "all passed"}\')'
            ),
            new_code_cell(
                "# The pre-specified sensitivity: country effects only. Year effects absorb an\n"
                "# additive shock common to every country in a year, and nothing more.\n"
                "country_only = estimate_dynamic_panel(\n"
                "    panel,\n"
                "    fixed_effects='country',\n"
                "    replications=299,\n"
                "    bias_correction_draws=100,\n"
                ")\n"
                "print(f'With year effects   : {panel_result.corrected_multiplier:.3f}')\n"
                "print(f'Country effects only: {country_only.corrected_multiplier:.3f}')"
            ),
            new_markdown_cell(
                "## What this notebook does not establish\n"
                "\n"
                "The pooled estimate is not a second body of evidence. It uses the same\n"
                "country-years as the country table above, and it reaches whatever precision it\n"
                "has by assuming common dynamics. Where `I²` is high, that assumption is\n"
                "contradicted by the same data, and the country estimates are the finding."
            ),
        ]
    )


def decomposition() -> nbformat.NotebookNode:
    return _notebook(
        [
            new_markdown_cell(
                "# 04 — Labour-share accounting decomposition\n"
                "\n"
                "This notebook consumes the processed Eurostat decomposition panel and does not\n"
                "reimplement the accounting logic. The identity is\n"
                "\n"
                "$$\\Delta\\log w = \\Delta\\log Y + \\Delta\\log s_L - \\Delta\\log N + (\\pi_Y-\\pi_C).$$\n"
                "\n"
                "`w` is **real compensation per employee from national accounts**, not the OECD\n"
                "average annual wage series. The two concepts are kept separate throughout: they\n"
                "have different numerators, different denominators and different deflators."
            ),
            new_code_cell(
                "from pathlib import Path\n"
                "\n"
                "import numpy as np\n"
                "import pandas as pd\n"
                "\n"
                "from wage_transmission.decomposition import decompose_panel\n"
                "from wage_transmission.plots import (\n"
                "    plot_cumulative_decomposition,\n"
                "    plot_decomposition_components,\n"
                ")\n"
                "\n"
                "INPUT = Path('../data/processed/decomposition_inputs.csv')\n"
                "ILLUSTRATIVE = not INPUT.exists()\n"
                "\n"
                "if not ILLUSTRATIVE:\n"
                "    panel = pd.read_csv(INPUT)\n"
                "else:\n"
                "    # No processed decomposition input in this checkout. Build one from the\n"
                "    # identity itself so the notebook still demonstrates that the accounting\n"
                "    # closes. This is SIMULATED and is not evidence about any real economy.\n"
                "    rng = np.random.default_rng(20260824)\n"
                "    years = np.arange(1996, 2025)\n"
                "    n = len(years)\n"
                "    real_gdp = 100 * np.exp(np.cumsum(rng.normal(0.015, 0.02, n)))\n"
                "    deflator = np.exp(np.cumsum(rng.normal(0.02, 0.01, n)))\n"
                "    labour_share = 0.50 * np.exp(np.cumsum(rng.normal(-0.001, 0.006, n)))\n"
                "    employees = 4000 * np.exp(np.cumsum(rng.normal(0.004, 0.008, n)))\n"
                "    cpi = np.exp(np.cumsum(rng.normal(0.021, 0.009, n)))\n"
                "    panel = pd.DataFrame(\n"
                "        {\n"
                "            'country': 'PRT',\n"
                "            'year': years,\n"
                "            'real_gdp': real_gdp,\n"
                "            'nominal_gdp': real_gdp * deflator,\n"
                "            'employee_compensation': real_gdp * deflator * labour_share,\n"
                "            'employees': employees,\n"
                "            'consumer_price_index': cpi,\n"
                "        }\n"
                "    )\n"
                "\n"
                "print('SIMULATED DATA — NOT EVIDENCE' if ILLUSTRATIVE else f'Source: {INPUT}')\n"
                "panel.groupby('country').agg(\n"
                "    first_year=('year', 'min'), last_year=('year', 'max'), n=('year', 'size')\n"
                ")"
            ),
            new_code_cell(
                "portugal = panel.loc[panel['country'].eq('PRT')].copy()\n"
                "components, summaries = decompose_panel(portugal)\n"
                "summaries[0]"
            ),
            new_markdown_cell(
                "## Annual contributions\n"
                "\n"
                "Each row adds up: the four components reconstruct observed real wage growth."
            ),
            new_code_cell(
                "components[\n"
                "    [\n"
                "        'year',\n"
                "        'observed_real_wage_growth',\n"
                "        'real_gdp_component',\n"
                "        'labour_share_component',\n"
                "        'employment_component',\n"
                "        'relative_price_component',\n"
                "        'identity_residual',\n"
                "    ]\n"
                "].tail(10).round(4)"
            ),
            new_markdown_cell(
                "## Does the identity close?\n"
                "\n"
                "This is an accounting identity, so the residual must be zero to floating-point\n"
                "tolerance. A non-trivial residual means the inputs are inconsistent — a mismatched\n"
                "employee concept or deflator — not that the economy behaved unusually."
            ),
            new_code_cell(
                "residual = components['identity_residual'].dropna()\n"
                "print(f'Largest absolute residual: {residual.abs().max():.2e}')\n"
                "print(f'Closes to tolerance      : {bool(residual.abs().max() < 1e-10)}')"
            ),
            new_markdown_cell("## Figures"),
            new_code_cell(
                "from IPython.display import Image\n"
                "\n"
                "figure_dir = Path('../results/decomposition/PRT')\n"
                "plot_decomposition_components(components, figure_dir / 'annual_components.png')\n"
                "plot_cumulative_decomposition(components, figure_dir / 'cumulative_components.png')\n"
                "Image(filename=str(figure_dir / 'cumulative_components.png'))"
            ),
            new_markdown_cell(
                "## Interpretation guardrail\n"
                "\n"
                "The decomposition is an accounting identity, not a causal model. A negative\n"
                "labour-share contribution means the labour share moved against real compensation\n"
                "per employee over the interval. It does **not** identify why the labour share\n"
                "changed, and it cannot be read as the effect of any policy or shock."
            ),
        ]
    )


BUILDERS = {
    "01_data_audit.ipynb": data_audit,
    "02_portugal_core_models.ipynb": portugal_core_models,
    "03_cross_country_robustness.ipynb": cross_country,
    "04_labour_share_decomposition.ipynb": decomposition,
}


def main() -> int:
    NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    for name, builder in BUILDERS.items():
        path = NOTEBOOK_DIR / name
        # LF explicitly: notebook bytes are hashed into the release manifest.
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            nbformat.write(builder(), handle)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
