# Reproducibility

1. Official API responses are written unchanged to `data/raw/`. Once a raw path exists, a later response with different bytes is refused rather than overwritten; use a versioned raw directory for a new data vintage.
2. Each raw snapshot receives a metadata JSON file with query URL, source, filters, byte count, UTC retrieval timestamp, provenance-schema version and SHA-256 digest. Repeating an identical download is idempotent and does not rewrite the first freeze.
3. Canonical transformations live in `src/`; notebooks do not contain hidden data-cleaning logic.
4. Model outputs are serialized to JSON before plotting or prose interpretation.
5. Synthetic sample data are labelled explicitly and are never mixed with empirical results.
6. Data revisions are expected. A study release should record retrieval date, raw digests and package version.
7. Cross-country comparisons must use harmonised definitions and must not mix current-price and constant-price series.
8. OECD wage/productivity analysis and Eurostat compensation decomposition are separate empirical layers with different remuneration concepts.
9. The Eurostat decomposition uses the domestic-concept employee count (`SAL_DC`) because it aligns with resident production and GDP; total employment (`EMP_DC`) is not substituted silently.
10. Country-level cross-country coefficients are retained before any meta-analytic summary is produced. The summary cannot replace the underlying country table.

11. The Eurostat decomposition downloader writes a source-by-source coverage audit before intersecting the five level series. Publication samples must therefore report both requested coverage and the final common sample.
12. Publication releases export a deterministic source-query manifest before data retrieval. The raw freeze is complete only when every manifest query is present and SHA-256 verified.
13. Browser/curl/other-machine downloads may be imported byte-for-byte, but are labelled `external_import`; they are never misrepresented as package-performed HTTP retrievals.
14. Processed panels can be rebuilt offline from verified raw responses. An unverified-input override exists only for development and must not be used for publication evidence.
15. Official-source revisions are compared explicitly across processed vintages and classified as unchanged, revised, added or dropped observations.
