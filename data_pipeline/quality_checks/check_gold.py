from __future__ import annotations

import argparse

import pandas as pd

from data_pipeline.settings import file_path


def check_gold_real_estate(year: int) -> None:
    path = file_path("gold", "real_estate", str(year), f"real_estate_commune_{year}.parquet")
    frame = pd.read_parquet(path)

    checks = {
        "non_empty": len(frame) > 0,
        "code_commune_not_null": frame["code_commune"].notna().all(),
        "avg_price_m2_not_null": frame["avg_price_m2"].notna().all(),
        "avg_price_m2_positive": (frame["avg_price_m2"] > 0).all(),
        "no_duplicate_communes": not frame.duplicated(subset=["code_commune", "year"]).any(),
    }

    failed = [name for name, passed in checks.items() if not passed]
    for name, passed in checks.items():
        print(f"{name}: {'OK' if passed else 'FAILED'}")

    if failed:
        raise SystemExit(f"Quality checks failed: {', '.join(failed)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run gold data quality checks.")
    parser.add_argument("--year", required=True, type=int)
    args = parser.parse_args()
    check_gold_real_estate(args.year)


if __name__ == "__main__":
    main()

