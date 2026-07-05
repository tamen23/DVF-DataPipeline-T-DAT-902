from __future__ import annotations

"""
Spark implementation of the gold real-estate aggregation — the distributed
alternative to data_pipeline.transformation.gold_real_estate (pandas).
Feature-equivalent: same filters, same columns, same single-file output, so
check_gold, upload_to_hdfs and load_postgres work unchanged downstream.

Requires Java (and winutils on Windows). Select it in the pipeline with
USE_SPARK=1 ./pipeline.sh 2023

Usage:
  python -m data_pipeline.spark_jobs.aggregate_dvf --year 2023
"""

import argparse
import os
import shutil

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from data_pipeline.settings import file_path

# Keep aligned with transformation/gold_real_estate.py and quality_checks/check_gold.py
PRICE_M2_MIN = 200
PRICE_M2_MAX = 30_000
MIN_TRANSACTIONS = 3


def build_gold_real_estate(year: int) -> None:
    silver_path = file_path("silver", "dvf", str(year), f"real_estate_transactions_{year}.parquet")
    gold_path = file_path("gold", "real_estate", str(year), f"real_estate_commune_{year}.parquet")
    previous_path = file_path("gold", "real_estate", str(year - 1), f"real_estate_commune_{year - 1}.parquet")

    spark = (
        SparkSession.builder.appName("homepedia-dvf-aggregation")
        .master(os.getenv("SPARK_MASTER", "local[*]"))
        .config("spark.sql.session.timeZone", "Europe/Paris")
        .getOrCreate()
    )

    transactions = spark.read.parquet(str(silver_path))
    before = transactions.count()
    transactions = transactions.filter(
        (F.col("prix_m2") >= PRICE_M2_MIN) & (F.col("prix_m2") <= PRICE_M2_MAX)
    )
    kept = transactions.count()
    print(f"  Filtered {before - kept:,} aberrant price/m² rows ({kept:,} kept)")

    grouped = (
        transactions.groupBy("code_commune", "nom_commune", "year")
        .agg(
            F.count("*").alias("transaction_count"),
            F.avg("valeur_fonciere").alias("avg_price"),
            F.avg("prix_m2").alias("avg_price_m2"),
            F.expr("percentile_approx(prix_m2, 0.5)").alias("median_price_m2"),
            F.avg("surface_reelle_bati").alias("avg_surface"),
        )
        .filter(F.col("transaction_count") >= MIN_TRANSACTIONS)
    )

    if previous_path.exists():
        previous = (
            spark.read.parquet(str(previous_path))
            .select("code_commune", F.col("avg_price_m2").alias("previous_avg_price_m2"))
        )
        grouped = grouped.join(previous, on="code_commune", how="left").withColumn(
            "price_m2_yoy_variation",
            (F.col("avg_price_m2") - F.col("previous_avg_price_m2")) / F.col("previous_avg_price_m2"),
        )
    else:
        grouped = grouped.withColumn("price_m2_yoy_variation", F.lit(None).cast("double"))

    # Downstream consumers expect one Parquet *file* at gold_path, not a
    # Spark output directory: write to a temp dir and move the single part.
    tmp_dir = gold_path.parent / f"_spark_gold_{year}"
    grouped.coalesce(1).write.mode("overwrite").parquet(str(tmp_dir))
    row_count = grouped.count()
    spark.stop()

    part_file = next(tmp_dir.glob("part-*.parquet"))
    gold_path.unlink(missing_ok=True)
    shutil.move(str(part_file), str(gold_path))
    shutil.rmtree(tmp_dir)
    print(f"Gold real estate mart written to {gold_path} ({row_count:,} rows) [spark]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate silver DVF into the gold mart with PySpark.")
    parser.add_argument("--year", required=True, type=int)
    args = parser.parse_args()
    build_gold_real_estate(args.year)


if __name__ == "__main__":
    main()
