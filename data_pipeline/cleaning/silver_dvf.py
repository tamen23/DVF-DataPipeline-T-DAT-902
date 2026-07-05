from __future__ import annotations

import argparse

import pandas as pd

from data_pipeline.common import first_existing_column, to_numeric
from data_pipeline.settings import file_path


DVF_COLUMN_CANDIDATES = {
    "date_mutation": ["date_mutation", "date_de_mutation"],
    "valeur_fonciere": ["valeur_fonciere", "valeur_fonciere_eur", "price"],
    "surface_reelle_bati": ["surface_reelle_bati", "surface_reelle_batie", "surface_bati"],
    "nombre_pieces": ["nombre_pieces_principales", "nombre_pieces", "pieces"],
    "type_local": ["type_local", "type_de_local"],
    "code_commune": ["code_commune", "code_insee", "insee_code"],
    "nom_commune": ["commune", "nom_commune", "libelle_commune"],
    "code_postal": ["code_postal", "postal_code"],
}


def build_silver_dvf(year: int) -> None:
    bronze_path = file_path("bronze", "dvf", str(year), f"dvf_{year}.parquet")
    silver_path = file_path("silver", "dvf", str(year), f"real_estate_transactions_{year}.parquet")

    source = pd.read_parquet(bronze_path)
    output = pd.DataFrame()

    for target_column, candidates in DVF_COLUMN_CANDIDATES.items():
        source_column = first_existing_column(source.columns, candidates)
        output[target_column] = source[source_column] if source_column else None

    output["date_mutation"] = pd.to_datetime(output["date_mutation"], errors="coerce")
    output["valeur_fonciere"] = to_numeric(output["valeur_fonciere"])
    output["surface_reelle_bati"] = to_numeric(output["surface_reelle_bati"])
    output["nombre_pieces"] = pd.to_numeric(output["nombre_pieces"], errors="coerce").astype("Int64")
    output["code_commune"] = output["code_commune"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    output["nom_commune"] = output["nom_commune"].astype(str).str.strip().str.title()
    output["code_postal"] = output["code_postal"].astype(str).str.replace(r"\.0$", "", regex=True)
    output["prix_m2"] = output["valeur_fonciere"] / output["surface_reelle_bati"]
    output["source"] = "DVF"
    output["year"] = year

    output = output.dropna(subset=["date_mutation", "valeur_fonciere", "surface_reelle_bati", "code_commune"])
    output = output[output["surface_reelle_bati"] > 0]
    output = output[output["valeur_fonciere"] > 0]
    output = output[(output["prix_m2"] >= 100) & (output["prix_m2"] <= 50_000)]
    output = output.drop_duplicates()

    # Timestamps en millisecondes : pandas/pyarrow écrit du TIMESTAMP(NANOS)
    # par défaut, que Spark et Hive ne savent pas lire.
    output.to_parquet(silver_path, index=False, coerce_timestamps="ms", allow_truncated_timestamps=True)
    print(f"Silver DVF written to {silver_path} ({len(output):,} rows)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean bronze DVF into silver transactions.")
    parser.add_argument("--year", required=True, type=int)
    args = parser.parse_args()
    build_silver_dvf(args.year)


if __name__ == "__main__":
    main()

