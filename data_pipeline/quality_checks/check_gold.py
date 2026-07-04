from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd

from data_pipeline.settings import file_path

# Price boundaries per m² considered realistic for France
PRICE_M2_MIN = 500
PRICE_M2_MAX = 30_000

# A commune with fewer transactions than this is suspicious in the gold layer
MIN_TRANSACTIONS_PER_COMMUNE = 3

# Maximum share of communes that can have null avg_price_m2 (tolerance for small communes)
NULL_PRICE_TOLERANCE = 0.02


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""

    def __str__(self) -> str:
        status = "OK" if self.passed else "FAILED"
        suffix = f" — {self.detail}" if self.detail else ""
        return f"  [{status}] {self.name}{suffix}"


def run_checks(frame: pd.DataFrame, year: int) -> list[CheckResult]:
    results: list[CheckResult] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append(CheckResult(name, condition, detail))

    # --- Structure ---
    check("non_empty", len(frame) > 0, f"{len(frame):,} rows")
    check(
        "required_columns_present",
        all(c in frame.columns for c in ["code_commune", "avg_price_m2", "transaction_count", "year"]),
    )

    if frame.empty:
        return results

    # --- Nulls ---
    null_code = frame["code_commune"].isna().sum()
    check("code_commune_not_null", null_code == 0, f"{null_code} nulls")

    null_price = frame["avg_price_m2"].isna().sum()
    null_price_ratio = null_price / len(frame)
    check(
        "avg_price_m2_null_ratio_acceptable",
        null_price_ratio <= NULL_PRICE_TOLERANCE,
        f"{null_price_ratio:.1%} null ({null_price} communes)",
    )

    valid = frame.dropna(subset=["avg_price_m2", "transaction_count"])

    # --- Price range ---
    below_min = (valid["avg_price_m2"] < PRICE_M2_MIN).sum()
    above_max = (valid["avg_price_m2"] > PRICE_M2_MAX).sum()
    check("avg_price_m2_above_minimum", below_min == 0, f"{below_min} communes below {PRICE_M2_MIN} EUR/m²")
    check("avg_price_m2_below_maximum", above_max == 0, f"{above_max} communes above {PRICE_M2_MAX} EUR/m²")
    check("avg_price_m2_positive", (valid["avg_price_m2"] > 0).all())

    # --- Transaction counts ---
    low_tx = (valid["transaction_count"] < MIN_TRANSACTIONS_PER_COMMUNE).sum()
    check(
        "transaction_count_sufficient",
        low_tx == 0,
        f"{low_tx} communes with fewer than {MIN_TRANSACTIONS_PER_COMMUNE} transactions",
    )

    # --- Duplicates ---
    dupes = frame.duplicated(subset=["code_commune", "year"]).sum()
    check("no_duplicate_commune_year", dupes == 0, f"{dupes} duplicates")

    # --- Year coherence ---
    wrong_year = (frame["year"] != year).sum() if "year" in frame.columns else 0
    check("year_matches_expected", wrong_year == 0, f"{wrong_year} rows with unexpected year value")

    # --- YoY variation sanity (if present) ---
    if "price_m2_yoy_variation" in frame.columns:
        yoy = frame["price_m2_yoy_variation"].dropna()
        extreme_growth = (yoy.abs() > 1.0).sum()
        check(
            "yoy_variation_realistic",
            extreme_growth == 0,
            f"{extreme_growth} communes with >100% YoY price change",
        )

    # --- Coverage ---
    n_communes = len(frame["code_commune"].unique())
    check(
        "commune_coverage_reasonable",
        n_communes >= 100,
        f"{n_communes:,} unique communes (expected at least 100 for a national dataset)",
    )

    return results


def check_gold_real_estate(year: int) -> None:
    path = file_path("gold", "real_estate", str(year), f"real_estate_commune_{year}.parquet")

    if not path.exists():
        raise FileNotFoundError(f"Gold file not found: {path}")

    frame = pd.read_parquet(path)
    print(f"\nQuality checks — gold real estate {year} ({len(frame):,} rows)\n")

    results = run_checks(frame, year)
    for result in results:
        print(result)

    failed = [r for r in results if not r.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed.")

    if failed:
        raise SystemExit(f"\nQuality checks failed: {', '.join(r.name for r in failed)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run gold data quality checks.")
    parser.add_argument("--year", required=True, type=int)
    args = parser.parse_args()
    check_gold_real_estate(args.year)


if __name__ == "__main__":
    main()
