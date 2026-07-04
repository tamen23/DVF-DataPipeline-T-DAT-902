from __future__ import annotations

"""
Queries OpenStreetMap via Overpass API to count POIs per commune.
Runs department by department (96 queries) to avoid timeouts.

Produces: raw/osm/osm_poi_counts.parquet
Columns: code_commune, school_count, university_count, hospital_count,
         pharmacy_count, supermarket_count, restaurant_count,
         park_count, forest_count, bus_stop_count, train_station_count
"""

import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from data_pipeline.settings import file_path

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# POI categories to count per commune
# key: output column prefix  value: OSM filter expression
POI_QUERIES: dict[str, str] = {
    "school":        '[amenity~"^(school|college)$"]',
    "university":    '[amenity=university]',
    "hospital":      '[amenity~"^(hospital|clinic)$"]',
    "pharmacy":      '[amenity=pharmacy]',
    "supermarket":   '[shop~"^(supermarket|hypermarket)$"]',
    "restaurant":    '[amenity~"^(restaurant|fast_food|cafe)$"]',
    "park":          '[leisure~"^(park|garden)$"]',
    "forest":        '[landuse=forest]',
    "bus_stop":      '[highway=bus_stop]',
    "train_station": '[railway~"^(station|halt)$"]',
}

# French metropolitan departments (2-digit codes + DOM)
DEPARTMENTS = [
    "01","02","03","04","05","06","07","08","09",
    "10","11","12","13","14","15","16","17","18","19",
    "21","22","23","24","25","26","27","28","29",
    "30","31","32","33","34","35","36","37","38","39",
    "40","41","42","43","44","45","46","47","48","49",
    "50","51","52","53","54","55","56","57","58","59",
    "60","61","62","63","64","65","66","67","68","69",
    "70","71","72","73","74","75","76","77","78","79",
    "80","81","82","83","84","85","86","87","88","89",
    "90","91","92","93","94","95",
    "971","972","973","974","976",
]

PAUSE_BETWEEN_REQUESTS = 2.0  # seconds — be polite to Overpass


def _overpass_query(dept_code: str, osm_filter: str) -> list[dict]:
    """Count nodes+ways matching osm_filter inside each commune of the department."""
    query = f"""
[out:json][timeout:120];
area["ref:INSEE"~"^{dept_code}"](if:length(t["ref:INSEE"]) == {len(dept_code) + 3 if dept_code.startswith("97") else 5})[admin_level=8]->.communes;
foreach.communes(
  .communes is_in;
  area._[admin_level=8]->.commune;
  (
    node(area.commune){osm_filter};
    way(area.commune){osm_filter};
  );
  make stat insee=commune.u(t["ref:INSEE"]), count=count(nodes)+count(ways);
  out;
);
"""
    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        timeout=150,
        headers={"User-Agent": "homepedia-data-pipeline/1.0"},
    )
    response.raise_for_status()
    return response.json().get("elements", [])


def _query_department(dept_code: str) -> dict[str, dict[str, int]]:
    """Returns {code_commune: {poi_type: count}} for one department."""
    results: dict[str, dict[str, int]] = {}

    for poi_type, osm_filter in POI_QUERIES.items():
        try:
            elements = _overpass_query(dept_code, osm_filter)
            for el in elements:
                tags = el.get("tags", {})
                insee = str(tags.get("insee", "")).zfill(5)
                if not insee or insee == "00000":
                    continue
                count = int(tags.get("count", 0))
                if insee not in results:
                    results[insee] = {}
                results[insee][f"{poi_type}_count"] = count
            time.sleep(PAUSE_BETWEEN_REQUESTS)
        except Exception as e:
            print(f"    [warn] {dept_code}/{poi_type}: {e}")

    return results


def ingest_osm(departments: list[str] | None = None) -> Path:
    target_depts = departments or DEPARTMENTS
    all_results: dict[str, dict[str, int]] = {}

    print(f"Querying Overpass API for {len(target_depts)} departments...")
    print("(This takes ~10-20 min for all of France — be patient)\n")

    for i, dept in enumerate(target_depts, 1):
        print(f"  [{i}/{len(target_depts)}] Department {dept}...", end=" ", flush=True)
        dept_data = _query_department(dept)
        all_results.update(dept_data)
        print(f"{len(dept_data)} communes")

    # Build dataframe
    rows = [{"code_commune": code, **counts} for code, counts in all_results.items()]
    frame = pd.DataFrame(rows)

    # Fill missing counts with 0
    for poi_type in POI_QUERIES:
        col = f"{poi_type}_count"
        if col not in frame.columns:
            frame[col] = 0
        else:
            frame[col] = frame[col].fillna(0).astype(int)

    target = file_path("raw", "osm", "osm_poi_counts.parquet")
    frame.to_parquet(target, index=False)

    meta = target.with_suffix(".metadata.txt")
    meta.write_text(
        "\n".join([
            "source=https://overpass-api.de",
            f"departments={','.join(target_depts)}",
            f"communes={len(frame)}",
            f"imported_at={datetime.now(timezone.utc).isoformat()}",
        ]),
        encoding="utf-8",
    )

    print(f"\nOSM POI counts stored at {target} ({len(frame):,} communes)")
    return target


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Download OSM POI counts per commune via Overpass API.")
    parser.add_argument(
        "--departments", nargs="+", default=None,
        help="Limit to specific departments (e.g. --departments 75 92 93 94). Default: all France.",
    )
    args = parser.parse_args()
    ingest_osm(args.departments)


if __name__ == "__main__":
    main()
