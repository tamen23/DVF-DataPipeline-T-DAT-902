from __future__ import annotations

"""
Uploads local data lake Parquet files to HDFS via docker exec (namenode container).
Run this after the full pipeline to make data available to Hive.

Usage:
  python -m data_pipeline.ingestion.upload_to_hdfs --year 2023
  python -m data_pipeline.ingestion.upload_to_hdfs --year 2023 --layer gold
"""

import argparse
import subprocess
from pathlib import Path

from data_pipeline.settings import DATA_LAKE_PATH

NAMENODE_CONTAINER = "homepedia-namenode"
HIVE_SERVER_CONTAINER = "homepedia-hive-server"
HDFS_BASE = "/homepedia"
CONTAINER_TMP = "/tmp/hdfs_upload"

# (local path relative to layer dir, HDFS path relative to layer dir)
# Each dataset gets its own HDFS directory so Hive external tables
# (one LOCATION per table) only see their own files.
LAYERS_TO_UPLOAD = {
    "raw": [
        ("communes/communes.parquet", "communes/communes/communes.parquet"),
        ("communes/regions.parquet", "communes/regions/regions.parquet"),
        ("communes/departements.parquet", "communes/departements/departements.parquet"),
        ("arcep/couverture_mobile.csv", "arcep/couverture_mobile.csv"),
        ("osm/osm_poi_counts.parquet", "osm/osm_poi_counts.parquet"),
        ("gtfs/stops_per_commune.parquet", "gtfs/stops_per_commune.parquet"),
    ],
    "gold": [
        ("territories/territory_scores.parquet", "territories/territory_scores.parquet"),
    ],
}


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def hdfs_mkdir(hdfs_path: str) -> None:
    _run(["docker", "exec", NAMENODE_CONTAINER, "hdfs", "dfs", "-mkdir", "-p", hdfs_path])


def hdfs_put(local: Path, hdfs_path: str) -> None:
    if not local.exists():
        print(f"  [skip] {local.name} not found locally")
        return

    # Copy file into the container then push to HDFS
    container_path = f"{CONTAINER_TMP}/{local.name}"
    _run(["docker", "exec", NAMENODE_CONTAINER, "mkdir", "-p", CONTAINER_TMP])
    _run(["docker", "cp", str(local), f"{NAMENODE_CONTAINER}:{container_path}"])

    hdfs_dir = hdfs_path.rsplit("/", 1)[0]
    hdfs_mkdir(hdfs_dir)
    _run(["docker", "exec", NAMENODE_CONTAINER, "hdfs", "dfs", "-put", "-f", container_path, hdfs_path])

    # Cleanup temp file
    _run(["docker", "exec", NAMENODE_CONTAINER, "rm", "-f", container_path], check=False)
    print(f"  Uploaded {local.name} → hdfs:{hdfs_path}")


def repair_partitions(tables: list[str]) -> None:
    """Register newly uploaded partitions in the Hive metastore.

    Partitioned external tables return 0 rows until their partitions
    are registered, even when the files are present in HDFS.
    """
    for table in tables:
        print(f"  MSCK REPAIR TABLE {table}")
        result = _run(
            [
                "docker", "exec", HIVE_SERVER_CONTAINER,
                "beeline", "-u", "jdbc:hive2://localhost:10000/homepedia",
                "-n", "hive", "-e", f"MSCK REPAIR TABLE {table};",
            ],
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr.strip() or result.stdout.strip())[:300]
            print(f"  [warn] partition repair failed for {table}: {detail}")
            print(f"  [warn] table {table} may return 0 rows until repaired manually:")
            print(f"         docker exec {HIVE_SERVER_CONTAINER} beeline -u jdbc:hive2://localhost:10000/homepedia -n hive -e 'MSCK REPAIR TABLE {table};'")


def upload_layer(layer: str, year: int | None = None) -> None:
    files = LAYERS_TO_UPLOAD.get(layer, [])
    for local_relative, hdfs_relative in files:
        local = DATA_LAKE_PATH / layer / local_relative
        hdfs_path = f"{HDFS_BASE}/{layer}/{hdfs_relative}"
        hdfs_put(local, hdfs_path)

    if layer == "silver":
        listing_files = sorted((DATA_LAKE_PATH / "silver" / "listings").glob("source_name=*/*.parquet"))
        if not listing_files:
            print("  [skip] no silver listings found locally")
        else:
            for local in listing_files:
                hdfs_put(local, f"{HDFS_BASE}/silver/listings/{local.parent.name}/{local.name}")
            repair_partitions(["silver_listings"])

    if layer == "gold" and year:
        local = DATA_LAKE_PATH / "gold" / "real_estate" / str(year) / f"real_estate_commune_{year}.parquet"
        hdfs_path = f"{HDFS_BASE}/gold/real_estate/annee={year}/real_estate_commune_{year}.parquet"
        hdfs_put(local, hdfs_path)
        repair_partitions(["gold_real_estate"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload local Parquet files to HDFS via Docker.")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--layer", choices=["raw", "silver", "gold", "all"], default="all")
    args = parser.parse_args()

    layers = ["raw", "silver", "gold"] if args.layer == "all" else [args.layer]
    print(f"Uploading {args.layer} layer(s) to HDFS...\n")
    for layer in layers:
        print(f"── {layer} ──")
        upload_layer(layer, args.year)

    print("\nDone.")


if __name__ == "__main__":
    main()
