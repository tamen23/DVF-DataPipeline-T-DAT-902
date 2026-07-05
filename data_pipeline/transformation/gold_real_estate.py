from __future__ import annotations

import argparse

import pandas as pd

from data_pipeline.settings import file_path


def build_gold_real_estate(year: int) -> None:
    silver_path = file_path("silver", "dvf", str(year), f"real_estate_transactions_{year}.parquet")
    gold_path = file_path("gold", "real_estate", str(year), f"real_estate_commune_{year}.parquet")

    transactions = pd.read_parquet(silver_path)

    # Filter aberrant prices (data entry errors or missing surface)
    before = len(transactions)
    transactions = transactions[
        (transactions["prix_m2"] >= 200) &
        (transactions["prix_m2"] <= 30_000)
    ]
    print(f"  Filtered {before - len(transactions):,} aberrant price/m² rows ({len(transactions):,} kept)")

    grouped = (
        transactions.groupby(["code_commune", "nom_commune", "year"], dropna=False)
        .agg(
            transaction_count=("prix_m2", "size"),
            avg_price=("valeur_fonciere", "mean"),
            avg_price_m2=("prix_m2", "mean"),
            median_price_m2=("prix_m2", "median"),
            avg_surface=("surface_reelle_bati", "mean"),
        )
        .reset_index()
    )

    # Remove communes with too few transactions (unreliable averages)
    before = len(grouped)
    grouped = grouped[grouped["transaction_count"] >= 3]
    print(f"  Removed {before - len(grouped):,} communes with < 3 transactions ({len(grouped):,} kept)")

    previous_year_path = file_path("gold", "real_estate", str(year - 1), f"real_estate_commune_{year - 1}.parquet")
    grouped["price_m2_yoy_variation"] = None
    if previous_year_path.exists():
        previous = pd.read_parquet(previous_year_path)[["code_commune", "avg_price_m2"]]
        previous = previous.rename(columns={"avg_price_m2": "previous_avg_price_m2"})
        grouped = grouped.merge(previous, on="code_commune", how="left")
        grouped["price_m2_yoy_variation"] = (
            (grouped["avg_price_m2"] - grouped["previous_avg_price_m2"])
            / grouped["previous_avg_price_m2"]
        )

    grouped.to_parquet(gold_path, index=False)
    print(f"Gold real estate mart written to {gold_path} ({len(grouped):,} rows)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build gold real estate KPIs by commune.")
    parser.add_argument("--year", required=True, type=int)
    args = parser.parse_args()
    build_gold_real_estate(args.year)


if __name__ == "__main__":
    main()

