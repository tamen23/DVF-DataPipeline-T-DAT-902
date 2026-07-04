from __future__ import annotations

import argparse

import pandas as pd

from data_pipeline.common import normalize_columns, read_csv_flexible
from data_pipeline.settings import file_path


def build_bronze_dvf(year: int, chunksize: int = 100_000) -> None:
    gz_path = file_path("raw", "dvf", str(year), f"dvf_{year}.csv.gz")
    csv_path = file_path("raw", "dvf", str(year), f"dvf_{year}.csv")
    raw_path = gz_path if gz_path.exists() else csv_path
    bronze_path = file_path("bronze", "dvf", str(year), f"dvf_{year}.parquet")

    chunks = []
    for chunk in read_csv_flexible(raw_path, chunksize=chunksize):
        frame = normalize_columns(chunk)
        frame["source_year"] = year
        frame["source_file"] = str(raw_path)
        chunks.append(frame)

    if not chunks:
        raise ValueError(f"No rows found in {raw_path}")

    bronze = pd.concat(chunks, ignore_index=True)
    for col in bronze.select_dtypes(include=["object", "str"]).columns:
        bronze[col] = bronze[col].astype(str)
    bronze.to_parquet(bronze_path, index=False)
    print(f"Bronze DVF written to {bronze_path} ({len(bronze):,} rows)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert raw DVF CSV to bronze Parquet.")
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--chunksize", default=100_000, type=int)
    args = parser.parse_args()
    build_bronze_dvf(args.year, args.chunksize)


if __name__ == "__main__":
    main()

