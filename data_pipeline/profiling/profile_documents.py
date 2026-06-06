from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from data_pipeline.settings import file_path


DATASET_INTERPRETATIONS = {
    "KaDo.csv": {
        "domain": "Retail / customer purchases",
        "business_summary": "Ticket-level cosmetic and hygiene product sales.",
        "homepedia_fit": "Not useful for the HOMEPEDIA real-estate MVP.",
        "recommended_use": "Keep as an external big-data practice dataset for segmentation, basket analysis, or retail BI.",
    },
    "speech_time_mw.csv": {
        "domain": "Media / gender representation",
        "business_summary": "Radio and TV speaking-time and music-duration observations by channel, date, and hour.",
        "homepedia_fit": "Not useful for the HOMEPEDIA real-estate MVP.",
        "recommended_use": "Keep as an external big-data practice dataset for time-series and equality dashboards.",
    },
    "data_pathologies.csv": {
        "domain": "Public health / territorial indicators",
        "business_summary": "Pathology prevalence by year, age class, sex, region, and department.",
        "homepedia_fit": "Potential V3 territorial context only, not part of the MVP scoring.",
        "recommended_use": "Could enrich territorial analysis at department/region level after the housing MVP is stable.",
    },
}


def detect_separator(path: Path) -> str:
    first_line = path.open("r", encoding="utf-8-sig", errors="ignore").readline()
    return ";" if first_line.count(";") > first_line.count(",") else ","


def safe_top_values(series: pd.Series, limit: int = 8) -> dict[str, int]:
    values = series.dropna().astype(str).value_counts().head(limit)
    return {str(key): int(value) for key, value in values.items()}


def profile_csv(path: Path, sample_rows: int, chunksize: int) -> dict[str, Any]:
    separator = detect_separator(path)
    sample = pd.read_csv(path, sep=separator, nrows=sample_rows, encoding="utf-8-sig")

    profile: dict[str, Any] = {
        "file_name": path.name,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "separator": separator,
        "columns": list(sample.columns),
        "sample_rows": len(sample),
        "dtypes": {column: str(dtype) for column, dtype in sample.dtypes.items()},
        "sample_nulls": {column: int(sample[column].isna().sum()) for column in sample.columns},
        "sample_unique_counts": {column: int(sample[column].nunique(dropna=True)) for column in sample.columns},
        "top_values": {},
        "numeric_summary": {},
        "row_count": 0,
    }
    profile.update(DATASET_INTERPRETATIONS.get(path.name, {}))

    for column in sample.columns:
        if sample[column].dtype == "object" or sample[column].nunique(dropna=True) <= 20:
            profile["top_values"][column] = safe_top_values(sample[column])

    numeric = sample.select_dtypes(include="number")
    if not numeric.empty:
        profile["numeric_summary"] = json.loads(numeric.describe().round(4).to_json())

    global_top_columns = [
        "FAMILLE",
        "media_type",
        "channel_name",
        "patho_niv1",
        "libelle_sexe",
        "region",
        "dept",
    ]
    min_max_columns = ["MOIS_VENTE", "annee", "hour", "date"]
    sums: dict[str, float] = {}
    nulls: dict[str, int] = {}
    top_values: dict[str, pd.Series] = {}
    min_values: dict[str, Any] = {}
    max_values: dict[str, Any] = {}

    for chunk in pd.read_csv(path, sep=separator, chunksize=chunksize, encoding="utf-8-sig"):
        profile["row_count"] += len(chunk)
        for column in chunk.columns:
            nulls[column] = nulls.get(column, 0) + int(chunk[column].isna().sum())

        for column in global_top_columns:
            if column in chunk.columns:
                values = chunk[column].value_counts(dropna=False)
                top_values[column] = top_values.get(column, pd.Series(dtype="float64")).add(values, fill_value=0)

        for column in min_max_columns:
            if column not in chunk.columns:
                continue
            values = pd.to_datetime(chunk[column], errors="coerce") if column == "date" else chunk[column]
            current_min = values.min()
            current_max = values.max()
            if pd.notna(current_min):
                min_values[column] = min(min_values[column], current_min) if column in min_values else current_min
            if pd.notna(current_max):
                max_values[column] = max(max_values[column], current_max) if column in max_values else current_max

        for column in chunk.select_dtypes(include="number").columns:
            sums[column] = sums.get(column, 0.0) + float(chunk[column].sum(skipna=True))

    profile["null_counts"] = nulls
    profile["global_top_values"] = {
        column: {str(key): int(value) for key, value in values.sort_values(ascending=False).head(10).items()}
        for column, values in top_values.items()
    }
    profile["min_values"] = {column: str(value) for column, value in min_values.items()}
    profile["max_values"] = {column: str(value) for column, value in max_values.items()}
    profile["numeric_sums"] = {column: round(value, 4) for column, value in sums.items()}
    return profile


def render_markdown(profiles: list[dict[str, Any]]) -> str:
    lines = [
        "# Documents CSV Analysis",
        "",
        "This report is generated by `data_pipeline.profiling.profile_documents`.",
        "",
        "## Executive Summary",
        "",
        "| File | Rows | Size | Domain | HOMEPEDIA fit |",
        "|---|---:|---:|---|---|",
    ]
    for profile in profiles:
        size_mb = profile["size_bytes"] / 1024 / 1024
        lines.append(
            f"| `{profile['file_name']}` | {profile['row_count']:,} | {size_mb:.1f} MB | "
            f"{profile.get('domain', 'Unknown')} | {profile.get('homepedia_fit', 'To classify')} |"
        )

    for profile in profiles:
        lines.extend(
            [
                "",
                f"## {profile['file_name']}",
                "",
                f"**Domain:** {profile.get('domain', 'Unknown')}",
                "",
                f"**Business summary:** {profile.get('business_summary', 'Not classified.')}",
                "",
                f"**Recommended use:** {profile.get('recommended_use', 'Review manually.')}",
                "",
                f"**Rows:** {profile['row_count']:,}",
                "",
                f"**Separator:** `{profile['separator']}`",
                "",
                "**Columns:**",
                "",
            ]
        )
        lines.extend([f"- `{column}` ({profile['dtypes'].get(column, 'unknown')})" for column in profile["columns"]])

        if profile["global_top_values"]:
            lines.extend(["", "**Global top values:**", ""])
            for column, values in profile["global_top_values"].items():
                rendered = ", ".join(f"{key}: {value:,}" for key, value in values.items())
                lines.append(f"- `{column}`: {rendered}")

        if profile["min_values"] or profile["max_values"]:
            lines.extend(["", "**Detected ranges:**", ""])
            for column in sorted(set(profile["min_values"]) | set(profile["max_values"])):
                lines.append(
                    f"- `{column}`: {profile['min_values'].get(column, '?')} -> {profile['max_values'].get(column, '?')}"
                )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile CSV files stored in the Documents folder.")
    parser.add_argument("--documents-dir", default="../Documents")
    parser.add_argument("--sample-rows", type=int, default=100_000)
    parser.add_argument("--chunksize", type=int, default=300_000)
    args = parser.parse_args()

    documents_dir = Path(args.documents_dir)
    csv_files = sorted(documents_dir.glob("*.csv"))
    profiles = [profile_csv(path, args.sample_rows, args.chunksize) for path in csv_files]

    json_path = file_path("gold", "external_catalog", "documents_csv_profiles.json")
    json_path.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8")

    report_path = Path("docs") / "documents_csv_analysis.md"
    report_path.write_text(render_markdown(profiles), encoding="utf-8")

    print(f"Wrote JSON catalog to {json_path}")
    print(f"Wrote Markdown report to {report_path}")


if __name__ == "__main__":
    main()

