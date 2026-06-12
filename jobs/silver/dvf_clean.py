"""DVF bronze -> silver: cleaning and standardization.

Cleaning rules (documented for the data-cleaning methodology deliverable):
- keep actual sales only (nature_mutation = 'Vente')
- keep dwellings only (type_local Maison / Appartement)
- keep mutations with exactly ONE dwelling row — multi-lot sales have a
  single price for several buildings, so no reliable price/m² (pragmatic
  V1 choice, ~documented loss, refined later if needed)
- drop rows without price, surface or commune code
- price/m² bounded to [100, 25000] € to remove data-entry outliers
- Paris/Lyon/Marseille arrondissement codes remapped to the parent commune
  (DVF records them at arrondissement level; the referential is city level)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyspark.sql import functions as F
from pyspark.sql.window import Window

from common.session import get_spark, lake_path


def main() -> None:
    spark = get_spark("dvf_silver")

    df = (
        spark.read.option("header", True)
        .csv(lake_path("bronze/dvf/*/full.csv.gz"))
        .select(
            "id_mutation",
            F.to_date("date_mutation").alias("date_mutation"),
            "nature_mutation",
            F.col("valeur_fonciere").cast("double"),
            "code_commune",
            "code_departement",
            "type_local",
            F.col("surface_reelle_bati").cast("double"),
            F.col("nombre_pieces_principales").cast("int").alias("nb_pieces"),
            F.col("longitude").cast("double"),
            F.col("latitude").cast("double"),
        )
        .withColumn("year", F.year("date_mutation"))
    )

    dwellings = df.filter(
        (F.col("nature_mutation") == "Vente")
        & F.col("type_local").isin("Maison", "Appartement")
        & F.col("valeur_fonciere").isNotNull()
        & F.col("code_commune").isNotNull()
        & (F.col("surface_reelle_bati") >= 9)
    )

    # keep single-dwelling mutations only (reliable price/m²)
    single = (
        dwellings.withColumn(
            "nb_dwellings", F.count("*").over(Window.partitionBy("id_mutation"))
        )
        .filter(F.col("nb_dwellings") == 1)
        .drop("nb_dwellings", "nature_mutation")
    )

    silver = (
        single.withColumn(
            "price_m2", F.round(F.col("valeur_fonciere") / F.col("surface_reelle_bati"), 2)
        )
        .filter(F.col("price_m2").between(100, 25000))
        .dropDuplicates(["id_mutation"])
        .withColumn(
            "code_commune",
            F.when(F.col("code_commune").between("75101", "75120"), "75056")  # Paris
            .when(F.col("code_commune").between("13201", "13216"), "13055")  # Marseille
            .when(F.col("code_commune").between("69381", "69389"), "69123")  # Lyon
            .otherwise(F.col("code_commune")),
        )
    )

    (
        silver.repartition("year")
        .write.mode("overwrite")
        .partitionBy("year")
        .parquet(lake_path("silver/dvf"))
    )

    print(f"silver/dvf written: {silver.count()} sales")
    spark.stop()


if __name__ == "__main__":
    main()
