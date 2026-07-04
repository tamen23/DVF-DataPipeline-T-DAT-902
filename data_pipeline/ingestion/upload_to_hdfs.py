from __future__ import annotations

"""
Uploads local data lake Parquet files to HDFS.
Run this after the full pipeline to make data available to Hive.

Usage:
  python -m data_pipeline.ingestion.upload_to_hdfs --year 2023
  python -m data_pipeline.ingestion.upload_to_hdfs --year 2023 --layer gold
"""

import argparse
import subprocess
from pathlib import Path

from data_pipeline.settings import DATA_LAKE_PATH

HDFS_BASE = "hdfs://namenode:8020/homepedia"

LAYERS_TO_UPLOAD = {
    "raw": [
        "communes/communes.parquet",
        "communes/regions.parquet",
        "communes/departements.parquet",
        "arcep/couverture_mobile.csv",
        "osm/osm_poi_counts.parquet",
        "gtfs/stops_per_commune.parquet",
    ],
    "gold": [
        "territories/territory_scores.parquet",
    ],
}


def hdfs_mkdir(path: str) -> None:
    subprocess.run(["hdfs", "dfs", "-mkdir", "-p", path], check=True)


def hdfs_put(local: Path, remote: str) -> None:
    if not local.exists():
        print(f"  [skip] {local} not found locally")
        return
    hdfs_mkdir(remote.rsplit("/", 1)[0])
    subprocess.run(["hdfs", "dfs", "-put", "-f", str(local), remote], check=True)
    print(f"  Uploaded {local.name} → {remote}")


def upload_layer(layer: str, year: int | None = None) -> None:
    files = LAYERS_TO_UPLOAD.get(layer, [])
    for relative in files:
        local = DATA_LAKE_PATH / layer / relative
        remote = f"{HDFS_BASE}/{layer}/{relative}"
        hdfs_put(local, remote)

    # Year-partitioned gold real estate
    if layer in ("gold", "all") and year:
        local = DATA_LAKE_PATH / "gold" / "real_estate" / str(year) / f"real_estate_commune_{year}.parquet"
        remote = f"{HDFS_BASE}/gold/real_estate/annee={year}/real_estate_commune_{year}.parquet"
        hdfs_put(local, remote)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload local Parquet files to HDFS for Hive.")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--layer", choices=["raw", "gold", "all"], default="all")
    args = parser.parse_args()

    layers = ["raw", "gold"] if args.layer == "all" else [args.layer]
    print(f"Uploading {args.layer} layer(s) to HDFS...\n")
    for layer in layers:
        print(f"── {layer} ──")
        upload_layer(layer, args.year)

    print("\nDone. Run Hive schema to create tables:")
    print("  beeline -u jdbc:hive2://localhost:10000 -f database/hive_schema.sql")


if __name__ == "__main__":
    main()
