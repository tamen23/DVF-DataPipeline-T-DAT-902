from __future__ import annotations

import argparse

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def run(input_path: str, output_path: str) -> None:
    spark = (
        SparkSession.builder.appName("homepedia-dvf-aggregation")
        .config("spark.sql.session.timeZone", "Europe/Paris")
        .getOrCreate()
    )

    frame = spark.read.parquet(input_path)

    result = (
        frame.groupBy("code_commune", "nom_commune", "year")
        .agg(
            F.count("*").alias("transaction_count"),
            F.avg("valeur_fonciere").alias("avg_price"),
            F.avg("prix_m2").alias("avg_price_m2"),
            F.expr("percentile_approx(prix_m2, 0.5)").alias("median_price_m2"),
            F.avg("surface_reelle_bati").alias("avg_surface"),
        )
    )

    result.write.mode("overwrite").parquet(output_path)
    spark.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate silver DVF with PySpark.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.input, args.output)


if __name__ == "__main__":
    main()

