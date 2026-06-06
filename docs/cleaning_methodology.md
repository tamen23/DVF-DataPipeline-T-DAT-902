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

## Traceability

Raw files are never modified. Each ingestion creates metadata containing source, year, target path, and import timestamp.

