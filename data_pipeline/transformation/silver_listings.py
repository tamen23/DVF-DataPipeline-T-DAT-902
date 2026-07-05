from __future__ import annotations

"""
Aggregates bronze listing batches (written by the Kafka bronze consumer)
into the silver per-commune listings mart consumed by the API (/listings)
and the vw_commune_full Hive view.

Scrapers tag listings with whatever code they were given on the CLI —
usually a postal code — while the rest of the platform is keyed on INSEE
commune codes. Codes that are not valid INSEE codes are translated using
the postal codes from the communes reference (ingest_communes).

Output layout matches the silver_listings Hive table partitioning:
  silver/listings/source_name={source}/listings.parquet

Usage:
  python -m data_pipeline.transformation.silver_listings
"""

import pandas as pd

from data_pipeline.settings import DATA_LAKE_PATH, file_path


def _load_commune_codes() -> tuple[set[str], dict[str, str]]:
    """Return (valid INSEE codes, postal code -> INSEE code of the most populous match)."""
    path = DATA_LAKE_PATH / "raw" / "communes" / "communes.parquet"
    if not path.exists():
        return set(), {}

    communes = pd.read_parquet(path)
    insee_codes = set(communes["code_commune"].dropna().astype(str))

    postal_map: dict[str, str] = {}
    if "codes_postaux" in communes.columns:
        # Ascending population sort so the most populous commune wins
        # when several communes share a postal code.
        ordered = communes.sort_values("population", na_position="first")
        for code_commune, postaux in zip(ordered["code_commune"], ordered["codes_postaux"]):
            for postal in str(postaux or "").split(","):
                postal = postal.strip()
                if postal:
                    postal_map[postal] = str(code_commune)
    return insee_codes, postal_map


def build_silver_listings() -> None:
    bronze_root = DATA_LAKE_PATH / "bronze" / "listings"
    files = sorted(bronze_root.glob("*/*/batch_*.parquet"))
    if not files:
        print(f"No bronze listing batches found under {bronze_root} — run the Kafka consumer first.")
        return

    listings = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    listings = listings.dropna(subset=["commune_code", "price_m2"])
    listings = listings[listings["price_m2"] > 0]
    listings["commune_code"] = listings["commune_code"].astype(str)

    # Translate postal codes to INSEE codes where possible.
    insee_codes, postal_map = _load_commune_codes()
    if postal_map:
        needs_mapping = ~listings["commune_code"].isin(insee_codes)
        listings.loc[needs_mapping, "commune_code"] = (
            listings.loc[needs_mapping, "commune_code"]
            .map(postal_map)
            .fillna(listings.loc[needs_mapping, "commune_code"])
        )

    # The same listing reappears at every scrape cycle: keep the latest
    # snapshot only, otherwise counts and averages are inflated. Listings
    # without an id are all distinct, so they are kept as-is.
    if "listing_id" in listings.columns:
        has_id = listings["listing_id"].fillna("").astype(str) != ""
        deduped = (
            listings[has_id]
            .sort_values("scraped_at")
            .drop_duplicates(subset=["source", "listing_id"], keep="last")
        )
        listings = pd.concat([deduped, listings[~has_id]], ignore_index=True)

    grouped = (
        listings.groupby(["source", "commune_code"])
        .agg(
            listing_count=("price_m2", "size"),
            avg_listing_price_m2=("price_m2", "mean"),
            median_listing_price_m2=("price_m2", "median"),
            min_listing_price_m2=("price_m2", "min"),
            max_listing_price_m2=("price_m2", "max"),
            last_updated=("scraped_at", "max"),
        )
        .reset_index()
        .rename(columns={"commune_code": "code_commune"})
    )

    for source, frame in grouped.groupby("source"):
        output = file_path("silver", "listings", f"source_name={source}", "listings.parquet")
        frame.drop(columns=["source"]).to_parquet(output, index=False)
        print(f"Silver listings written to {output} ({len(frame):,} communes)")


if __name__ == "__main__":
    build_silver_listings()
