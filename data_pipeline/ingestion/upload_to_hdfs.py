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
HDFS_BASE = "/homepedia"
CONTAINER_TMP = "/tmp/hdfs_upload"

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


def upload_layer(layer: str, year: int | None = None) -> None:
    files = LAYERS_TO_UPLOAD.get(layer, [])
    for relative in files:
        local = DATA_LAKE_PATH / layer / relative
        hdfs_path = f"{HDFS_BASE}/{layer}/{relative}"
        hdfs_put(local, hdfs_path)

    if layer in ("gold", "all") and year:
        local = DATA_LAKE_PATH / "gold" / "real_estate" / str(year) / f"real_estate_commune_{year}.parquet"
        hdfs_path = f"{HDFS_BASE}/gold/real_estate/annee={year}/real_estate_commune_{year}.parquet"
        hdfs_put(local, hdfs_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload local Parquet files to HDFS via Docker.")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--layer", choices=["raw", "gold", "all"], default="all")
    args = parser.parse_args()

    layers = ["raw", "gold"] if args.layer == "all" else [args.layer]
    print(f"Uploading {args.layer} layer(s) to HDFS...\n")
    for layer in layers:
        print(f"── {layer} ──")
        upload_layer(layer, args.year)

    print("\nDone.")


if __name__ == "__main__":
    main()
