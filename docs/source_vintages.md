# Source vintages and publication data freezes

## Purpose

Official macroeconomic data are revised. A reproducible empirical release therefore needs to distinguish four objects:

1. the **query definition** sent to the official source;
2. the **raw response bytes** returned by that query;
3. the **canonical processed panel** derived from those bytes;
4. the **model outputs** derived from the processed panel.

This repository treats each of those as a separate provenance layer. A later OECD or Eurostat revision should create a new source vintage, not mutate an earlier one.

## 1. Export the query manifest

The query manifest is deterministic and requires no network access:

```bash
poetry run wage-transmission export-source-queries \
  --project-config config/project.yml \
  --raw-dir data/raw \
  --vintage 2026-08-22 \
  --output data/query_manifests/2026-08-22.json
```

For the current project configuration this creates **63 queries**:

- 1 OECD average-wage request;
- 1 OECD GDP-per-hour request;
- 1 OECD GDP-per-employed-person request;
- 5 Eurostat decomposition requests for each of 12 European countries.

OECD requests include the exact `startPeriod` and `endPeriod`. Eurostat requests use `sinceTimePeriod` and `untilTimePeriod`, so a raw file named for 1995–2025 contains that requested range rather than a full-history response that is truncated only after download.

## 2. Freeze the official responses

On a machine with network access, the normal downloader may be run with an explicit vintage directory:

```bash
poetry run wage-transmission download-oecd-matched \
  --vintage 2026-08-22

poetry run wage-transmission download-decomposition \
  --vintage 2026-08-22
```

If the response must be downloaded in a browser, with `curl`, or on another machine, preserve the file **without decoding or re-saving it**. Then import it through the query manifest:

```bash
poetry run wage-transmission import-query-snapshot \
  --input ~/Downloads/oecd-response.csv \
  --query-manifest data/query_manifests/2026-08-22.json \
  --query-id oecd_gdpemp
```

The importer copies the bytes unchanged, writes adjacent metadata, records the official URL and query-manifest hash, and marks the retrieval method as `external_import` rather than pretending that the package itself performed the HTTP request.

## 3. Audit the freeze

```bash
poetry run wage-transmission audit-source-freeze \
  --query-manifest data/query_manifests/2026-08-22.json \
  --output data/query_manifests/2026-08-22.audit.csv \
  --strict
```

Every query must have status `verified` before a publication release is promoted. `--strict` exits non-zero when any query is missing, unverified, or hash-invalid.

A second registry is built directly from all adjacent raw metadata:

```bash
poetry run wage-transmission audit-snapshots \
  --raw-dir data/raw \
  --output data/raw/SNAPSHOT_REGISTRY.csv
```

The registry contains the source vintage, source, dataset/flow, measure, retrieval method, retrieval time, SHA-256 digest, byte count, raw path, metadata path and official URL.

## 4. Rebuild processed data offline

Once raw responses exist, all main processed panels can be recreated without network access.

Matched annual OECD panel:

```bash
poetry run wage-transmission build-oecd-from-snapshots \
  --wage-snapshot data/raw/2026-08-22/oecd_average_wages_1995_2025.csv \
  --productivity-snapshot data/raw/2026-08-22/oecd_gdpemp_1995_2025.csv \
  --measure GDPEMP \
  --output data/processed/2026-08-22/panel_per_worker.csv
```

Eurostat decomposition panel:

```bash
poetry run wage-transmission build-decomposition-from-snapshots \
  --raw-dir data/raw/2026-08-22 \
  --output data/processed/2026-08-22/decomposition_inputs.csv \
  --coverage-output data/processed/2026-08-22/decomposition_coverage.csv
```

Metadata verification is required by default. `--allow-unverified` exists only for development fixtures and should never be used for publication results.

Hash validity is necessary but not sufficient. Offline reconstruction also checks source semantics where the official payload exposes them: OECD productivity measure/flow codes and Eurostat dataset plus filtered dimension codes (`unit`, `na_item`/`coicop`, `geo`, `freq`). A valid payload for the wrong economic concept is rejected.

## 5. Quantify official-data revisions

Processed vintages can be compared directly:

```bash
poetry run wage-transmission compare-vintages \
  --old data/processed/2026-08-22/panel_per_worker.csv \
  --new data/processed/2026-11-01/panel_per_worker.csv \
  --values real_wage,productivity_per_worker \
  --output results/revisions/2026-08-22_vs_2026-11-01.csv
```

The audit distinguishes:

- unchanged observations;
- numerically revised observations;
- newly added observations;
- observations removed by the source.

For every series it also reports the number of revisions and the maximum and median absolute revision. This makes sensitivity to official revisions an empirical result rather than a hidden maintenance detail.

## Current release state

`data/query_manifests/2026-08-22.json` is the exact query plan for v0.4. In this execution environment outbound DNS is unavailable, so `data/query_manifests/2026-08-22.audit.csv` truthfully reports all 63 expected responses as `missing`.

That audit is a **release gate**, not a failure of the analysis code. It prevents the repository from promoting indexed/transcribed reference values to the status of untouched official API freezes.
