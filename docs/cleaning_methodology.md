# Cleaning Methodology

## DVF Cleaning

1. Normalize column names to lowercase ASCII snake case.
2. Parse dates with invalid values coerced to null.
3. Convert French numeric strings using comma decimals.
4. Normalize commune codes to five characters.
5. Remove rows without date, price, surface, or commune code.
6. Remove rows with zero or negative price and surface.
7. Compute `prix_m2`.
8. Remove obvious outliers:
   - `prix_m2 < 100`
   - `prix_m2 > 50000`
9. Deduplicate rows.

## Gold Aggregation Rules

Applied identically by the pandas builder and the Spark job:

- keep transactions with `200 <= prix_m2 <= 30000`
- drop communes with fewer than 3 transactions (unreliable averages)
- YoY variation computed against the previous year's gold mart

The quality gate (`quality_checks.check_gold`) enforces the same bounds and
fails the pipeline when anomalies are systematic (e.g. more than 10% of
communes moving over 100% YoY); isolated small-commune outliers only warn.

## Traceability

Raw files are never modified. Each ingestion creates metadata containing source, year, target path, and import timestamp.

