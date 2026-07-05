from __future__ import annotations

"""
Queries OpenStreetMap via Overpass API to count POIs per commune.

Strategy: one bbox query per department (no foreach — much faster/reliable).
POIs are assigned to the nearest commune using lat/lon from the communes reference.

Produces: raw/osm/osm_poi_counts.parquet
Columns: code_commune, school_count, university_count, hospital_count,
         pharmacy_count, supermarket_count, restaurant_count,
         park_count, forest_count, bus_stop_count, train_station_count
"""

import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from data_pipeline.settings import file_path

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
PAUSE = 5.0  # seconds between requests

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
    "2A","2B",
]

# POI type → OSM filter
POI_FILTERS = {
    "school":         '[amenity~"^(school|college)$"]',
    "university":     '[amenity=university]',
    "hospital":       '[amenity~"^(hospital|clinic)$"]',
    "pharmacy":       '[amenity=pharmacy]',
    "supermarket":    '[shop~"^(supermarket|hypermarket)$"]',
    "restaurant":     '[amenity~"^(restaurant|fast_food|cafe)$"]',
    "park":           '[leisure~"^(park|garden)$"]',
    "forest":         '[landuse=forest]',
    "bus_stop":       '[highway=bus_stop]',
    "train_station":  '[railway~"^(station|halt)$"]',
}


def _bbox_query(south: float, west: float, north: float, east: float, osm_filter: str) -> list[dict]:
    """Returns all nodes+way centroids matching osm_filter in the bbox."""
    bbox = f"{south},{west},{north},{east}"
    query = f"""
[out:json][timeout:60];
(
  node{osm_filter}({bbox});
  way{osm_filter}({bbox});
);
out center;
"""
    r = requests.post(
        OVERPASS_URL,
        data={"data": query},
        timeout=90,
        headers={"User-Agent": "homepedia-data-pipeline/1.0"},
    )
    r.raise_for_status()
    return r.json().get("elements", [])


def _assign_commune(lats: np.ndarray, lons: np.ndarray, communes: pd.DataFrame) -> np.ndarray:
    """
    Assign each (lat, lon) to the nearest commune centroid.
    Uses vectorized Euclidean distance (good enough at commune scale).
    Returns array of code_commune strings.
    """
    c_lats = communes["latitude"].values
    c_lons = communes["longitude"].values
    codes = communes["code_commune"].values

    result = np.empty(len(lats), dtype=object)
    # Process in batches to avoid memory explosion
    batch = 500
    for start in range(0, len(lats), batch):
        sl = slice(start, start + batch)
        dlat = lats[sl, None] - c_lats[None, :]
        dlon = lons[sl, None] - c_lons[None, :]
        dist = dlat ** 2 + dlon ** 2
        idx = dist.argmin(axis=1)
        result[sl] = codes[idx]
    return result


def _query_dept_pois(south: float, west: float, north: float, east: float) -> pd.DataFrame:
    """
    Query all POI types for a department bbox.
    Returns DataFrame with lat, lon, poi_type columns.
    """
    rows = []
    for poi_type, osm_filter in POI_FILTERS.items():
        try:
            elements = _bbox_query(south, west, north, east, osm_filter)
            for el in elements:
                lat = el.get("lat") or (el.get("center") or {}).get("lat")
                lon = el.get("lon") or (el.get("center") or {}).get("lon")
                if lat and lon:
                    rows.append({"lat": float(lat), "lon": float(lon), "poi_type": poi_type})
            time.sleep(0.5)
        except Exception as e:
            print(f" [warn] {poi_type}: {e}", end="")
    return pd.DataFrame(rows)


def ingest_osm(departments: list[str] | None = None, resume: bool = True) -> Path:
    target = file_path("raw", "osm", "osm_poi_counts.parquet")
    target.parent.mkdir(parents=True, exist_ok=True)

    # Load communes reference for spatial assignment
    communes_path = file_path("raw", "communes", "communes.parquet")
    if not communes_path.exists():
        raise FileNotFoundError("Communes reference not found. Run: py -m data_pipeline.ingestion.ingest_communes")
    communes = pd.read_parquet(communes_path)[["code_commune", "latitude", "longitude", "code_departement"]].dropna()
    communes["code_commune"] = communes["code_commune"].astype(str).str.zfill(5)
    communes["code_departement"] = communes["code_departement"].astype(str).str.upper()

    target_depts = [d.upper() for d in (departments or DEPARTMENTS)]

    # Resume: skip already-done departments
    existing = pd.DataFrame()
    done_depts: set[str] = set()
    if resume and target.exists():
        existing = pd.read_parquet(target)
        if not existing.empty and "code_commune" in existing.columns and len(existing) > 0:
            done_depts = set(existing["code_commune"].str[:2].str.upper().unique()) | \
                         set(existing["code_commune"].apply(lambda x: "2A" if x.startswith("2A") else ("2B" if x.startswith("2B") else x[:2])).unique())
            target_depts = [d for d in target_depts if d not in done_depts]
            print(f"  Résumé : {len(existing):,} communes déjà traitées — {len(target_depts)} départements restants")

    all_frames = [existing] if not existing.empty and len(existing) > 0 else []

    POI_COLS = [f"{p}_count" for p in POI_FILTERS]

    print(f"Querying Overpass API (bbox method) for {len(target_depts)} departments...\n")

    for i, dept in enumerate(target_depts, 1):
        # Compute bbox from communes in this department
        dept_communes = communes[communes["code_departement"] == dept]
        if dept_communes.empty:
            # Try numeric prefix
            prefix = dept.lstrip("0") if dept not in ("2A", "2B") else dept
            dept_communes = communes[communes["code_departement"].str.lstrip("0") == prefix]
        if dept_communes.empty:
            print(f"  [{i}/{len(target_depts)}] Dept {dept}: aucune commune référence — ignoré")
            continue

        south = dept_communes["latitude"].min() - 0.1
        north = dept_communes["latitude"].max() + 0.1
        west  = dept_communes["longitude"].min() - 0.1
        east  = dept_communes["longitude"].max() + 0.1

        print(f"  [{i}/{len(target_depts)}] Département {dept} (bbox {south:.2f},{west:.2f} -> {north:.2f},{east:.2f})...", end=" ", flush=True)

        try:
            pois = _query_dept_pois(south, west, north, east)

            if pois.empty:
                # No POIs — fill zeros for all communes in dept
                zeros = dept_communes[["code_commune"]].copy()
                for col in POI_COLS:
                    zeros[col] = 0
                all_frames.append(zeros)
                print(f"0 POIs")
            else:
                # Assign each POI to nearest commune
                pois["code_commune"] = _assign_commune(
                    pois["lat"].values, pois["lon"].values, dept_communes
                )
                # Pivot to counts
                counts = pois.groupby(["code_commune", "poi_type"]).size().unstack(fill_value=0)
                counts.columns = [f"{c}_count" for c in counts.columns]
                for col in POI_COLS:
                    if col not in counts.columns:
                        counts[col] = 0
                counts = counts[POI_COLS].reset_index()

                # Ensure all dept communes appear (even those with 0 POIs)
                merged = dept_communes[["code_commune"]].merge(counts, on="code_commune", how="left")
                for col in POI_COLS:
                    merged[col] = merged[col].fillna(0).astype(int)

                all_frames.append(merged)
                print(f"{len(pois):,} POIs -> {len(merged)} communes")

        except Exception as e:
            print(f"ERREUR : {e}")

        # Checkpoint every 5 departments
        if all_frames and i % 5 == 0:
            checkpoint = pd.concat(all_frames, ignore_index=True).drop_duplicates("code_commune")
            checkpoint.to_parquet(target, index=False)
            print(f"    [checkpoint] {len(checkpoint):,} communes sauvegardées\n")

        time.sleep(PAUSE)

    if not all_frames:
        print("Aucune donnée OSM récupérée.")
        pd.DataFrame(columns=["code_commune"] + POI_COLS).to_parquet(target, index=False)
        return target

    result = pd.concat(all_frames, ignore_index=True).drop_duplicates("code_commune")
    result.to_parquet(target, index=False)

    target.with_suffix(".metadata.txt").write_text(
        "\n".join([
            "source=https://overpass-api.de",
            f"departments={','.join(target_depts)}",
            f"communes={len(result)}",
            f"imported_at={datetime.now(timezone.utc).isoformat()}",
        ]),
        encoding="utf-8",
    )

    print(f"\nOSM POI counts : {len(result):,} communes -> {target}")
    return target


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--departments", nargs="+", default=None)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    ingest_osm(args.departments, resume=not args.no_resume)


if __name__ == "__main__":
    main()
