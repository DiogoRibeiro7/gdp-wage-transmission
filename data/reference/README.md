# Frozen reference data

`portugal_oecd_1995_2025.csv` is the first empirical Portugal snapshot used by the repository.

It contains two current OECD series as observed on **2026-08-22**:

- average annual wage, constant 2025 prices, PPP-converted USD;
- GDP per hour worked, PPP-converted USD/hour, OECD Productivity Database v2.0.

The common window is 1995–2025. The adjacent provenance JSON records the source dataset, query page and retrieval status.

## Important provenance limitation

The execution environment used to create v0.2 could inspect the official OECD Data Explorer but could not make outbound HTTP requests from Python. The CSV is therefore a **frozen reference transcription from the official Data Explorer**, not an untouched SDMX response.

It is suitable for reproducing the v0.2 empirical run, but it is not a substitute for the raw-source archive. In a network-enabled environment, run:

```bash
poetry run wage-transmission download-data
```

The resulting `data/raw/` files and metadata hashes should be used for a publication release.

The per-employed-person matched annual specification is supported by the downloader but is intentionally not fabricated into this frozen file; it must be obtained from the official API in a network-enabled run.
