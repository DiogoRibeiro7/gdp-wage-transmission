# Data dictionary

## Canonical core panel

| Column | Type | Meaning |
|---|---|---|
| `country` | string | ISO-like source country code |
| `year` | integer | Calendar year |
| `real_wage` | float | OECD real average annual wage measure |
| `productivity` | float | Real GDP per hour worked; primary hourly-productivity driver |
| `productivity_per_worker` | float, optional | Real GDP per person employed; denominator-matched annual robustness driver |
| `real_gdp` | float, optional | Aggregate real GDP robustness driver |

## Preferred definitions

### Wage

The first implementation uses the OECD **average annual wage** series at constant prices. It is an annual remuneration concept, so it should not be described as an hourly wage. The source unit and price-base columns are retained in raw snapshots and must be reported in empirical tables.

### Productivity per hour

`productivity` is OECD GDP per hour worked for the total economy. It is the preferred measure of hourly labour productivity, but pairing it with an annual wage series is not a denominator-matched comparison. It remains useful as a productivity-transmission specification because fixed unit scaling does not affect within-country log elasticities.

### Productivity per employed person

`productivity_per_worker` is OECD GDP per person employed. It is the preferred **matched annual robustness specification** for the available annual wage series. The downloader keeps the column distinct so the analysis cannot silently change denominators.

Run it with:

```bash
poetry run wage-transmission download-oecd-matched
poetry run wage-transmission analyse \
  --input data/processed/panel_per_worker.csv \
  --country PRT \
  --driver productivity_per_worker \
  --output results/portugal-per-worker
```

## Eurostat accounting panel

`download-decomposition` creates a separate panel with the inputs required for an exact national-accounts identity:

| Column | Eurostat source | Selection | Meaning |
|---|---|---|---|
| `nominal_gdp` | `nama_10_gdp` | `B1GQ`, `CP_MEUR` | GDP at current market prices |
| `real_gdp` | `nama_10_gdp` | `B1GQ`, `CLV20_MEUR` | GDP chain-linked volume, 2020 reference |
| `employee_compensation` | `nama_10_gdp` | `D1`, `CP_MEUR` | Compensation of employees |
| `employees` | `nama_10_pe` | `SAL_DC`, `THS_PER` | Employees, domestic concept |
| `consumer_price_index` | `prc_hicp_aind` | `CP00`, `INX_A_AVG` | All-items HICP annual-average index |

`SAL_DC` is deliberate. `EMP_DC` includes self-employed persons and is therefore not the correct denominator for compensation of employees.

The decomposition derives:

- labour share: `employee_compensation / nominal_gdp`;
- implicit GDP deflator: `nominal_gdp / real_gdp`;
- real compensation per employee: `employee_compensation / employees / consumer_price_index`;
- annual contributions from real GDP, labour share, employees and relative prices.

The million-euro/thousand-person scale factors are constant and therefore cancel in log differences.

### Concept warning

The accounting dependent variable is **real compensation per employee**, including employers' social contributions through ESA transaction D.1. It is not the same concept as the OECD average annual wage. The two analyses are complementary and must not be merged into one series.

## Source schema audit

Canonicalisation reduces a labelled SDMX response to `country`, `year`, one value column and a
source tag. The unit, price base, observation status and any revision flag are dropped at that
point, which is what makes the analytical panel safe to model and also what makes provenance
disappear.

`data/schema_audit.py` records those attributes *before* the reduction, so a published number can
be traced to the exact measurement concept behind it. It distinguishes two kinds of attribute:

| Attribute | Behaviour on variation |
| --- | --- |
| Unit of measure | **Fails.** Two units in one series means two economic concepts. |
| Price base | **Fails.** Mixing current and constant prices changes the concept silently. |
| Observation status | Recorded in full. Provisional and estimated values are normal. |
| Transformation | Recorded in full. |
| Revision flag | Recorded in full; absence is reported rather than assumed. |

Both coded (`UNIT_MEASURE`, `OBS_STATUS`) and labelled (`Unit of measure`, `Observation status`)
column names are recognised, because the SDMX response carries one or the other depending on the
requested format.

## Median earnings

| Column | Meaning |
| --- | --- |
| `median_wage` | Median gross earnings, in the source's own unit and price base |

Mean and median wages answer different questions, so the two are kept as separate columns and are
never substituted for one another: a mean annual wage moves with the top of the distribution and
a median with the middle, and transmission estimated on each can differ for reasons unrelated to
the transmission mechanism.

Harmonised median earnings are patchier than mean wages. `data/median_wages.py` therefore gates
attachment on measured per-country coverage over the requested window; countries below the
threshold (80% by default) are dropped and reported in the returned coverage table rather than
carried with gaps, because which countries were dropped changes what the estimates mean.

The median dataflow identifier is supplied from `config/data_sources.yml` rather than hard-coded,
and is currently marked `status: unverified`. It must be confirmed against the OECD Data Explorer
before a live source freeze: a wrong identifier returns a neighbouring concept instead of failing.
