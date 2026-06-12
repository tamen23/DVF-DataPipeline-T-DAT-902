"""DVF silver -> gold: real estate indicators at the three analysis levels.

Output (parquet in the lake + tables in Postgres schema `gold`):
- dvf_commune_year / dvf_department_year / dvf_region_year:
  sales count, median & avg price/m², median price — per area, year, type_local.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyspark.sql import functions as F

from common.session import get_spark, lake_path

JDBC_URL = "jdbc:postgresql://{host}:5432/{db}".format(
    host=os.environ.get("POSTGRES_HOST", "postgres"),
    db=os.environ["POSTGRES_DB"],
)
JDBC_PROPS = {
    "user": os.environ["POSTGRES_USER"],
    "password": os.environ["POSTGRES_PASSWORD"],
    "driver": "org.postgresql.Driver",
}


def aggregate(df, area_col: str):
    return df.groupBy(area_col, "year", "type_local").agg(
        F.count("*").alias("nb_sales"),
        F.percentile_approx("price_m2", 0.5).alias("median_price_m2"),
        F.round(F.avg("price_m2"), 2).alias("avg_price_m2"),
        F.percentile_approx("valeur_fonciere", 0.5).alias("median_price"),
    )


def write(df, name: str) -> None:
    df.write.mode("overwrite").parquet(lake_path(f"gold/{name}"))
    df.write.mode("overwrite").jdbc(JDBC_URL, f"gold.{name}", properties=JDBC_PROPS)
    print(f"gold/{name}: {df.count()} rows")


def main() -> None:
    spark = get_spark("dvf_gold")

    silver = spark.read.parquet(lake_path("silver/dvf"))

    # department -> region mapping from the referential (small, via JDBC)
    departments = spark.read.jdbc(
        JDBC_URL, "referential.department", properties=JDBC_PROPS
    ).select(F.col("code").alias("code_departement"), "region_code")

    silver = silver.join(departments, on="code_departement", how="left")

    write(aggregate(silver, "code_commune"), "dvf_commune_year")
    write(aggregate(silver, "code_departement"), "dvf_department_year")
    write(aggregate(silver, "region_code"), "dvf_region_year")

    spark.stop()


if __name__ == "__main__":
    main()
