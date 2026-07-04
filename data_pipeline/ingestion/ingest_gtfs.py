from __future__ import annotations

"""
Downloads the national French stops database from transport.data.gouv.fr
and counts transit stops per commune.

Source: Base Nationale des Lieux et Arrets (BNLCA)
URL: https://transport.data.gouv.fr/datasets/base-nationale-des-lieux-et-arrets

Produces: raw/gtfs/stops_per_commune.parquet
Columns: code_commune, stop_count, has_train, has_metro, has_tram, has_bus
"""

import zipfile
import io
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from data_pipeline.settings import file_path

# National stops database — updated monthly by transport.data.gouv.fr
BNLCA_URL = "https://transport.data.gouv.fr/resources/7186/download"

CHUNK_SIZE = 4 * 1024 * 1024

# Route type codes from GTFS spec
ROUTE_TYPE_LABELS = {
    0: "tram",
    1: "metro",
    2: "train",
    3: "bus",
    4: "ferry",
    7: "funicular",
    100: "train",
    400: "metro",
    700: "bus",
    900: "tram",
}


def _download(url: str, target: Path) -> None:
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": "homepedia/1.0"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(target, "wb") as fh:
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                fh.write(chunk)
                downloaded += len(chunk)
                if total:
                    print(f"\r  {downloaded / total * 100:.1f}%", end="", flush=True)
        print()


def _parse_stops(zip_path: Path) -> pd.DataFrame:
    """Extract stops.txt and trips/routes info from the GTFS zip."""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

        # stops.txt contains lat/lon and optionally commune code
        with zf.open("stops.txt") as f:
            stops = pd.read_csv(f, dtype=str, on_bad_lines="skip")
        stops.columns = [c.strip().lower() for c in stops.columns]

        routes = None
        if "routes.txt" in names:
            with zf.open("routes.txt") as f:
                routes = pd.read_csv(f, dtype=str, on_bad_lines="skip")
            routes.columns = [c.strip().lower() for c in routes.columns]

    return stops, routes


def _match_stops_to_communes(stops: pd.DataFrame, communes: pd.DataFrame) -> pd.DataFrame:
    """
    Match stops to communes using:
    1. stop_code or parent_station if it contains INSEE code
    2. Nearest commune by lat/lon (approximation via rounding)
    """
    stops = stops.copy()

    # Some BNLCA stops have a municipality code column
    code_col = next(
        (c for c in stops.columns if "insee" in c or "commune" in c or "municipality" in c),
        None,
    )

    if code_col:
        stops["code_commune"] = stops[code_col].astype(str).str.zfill(5)
    else:
        # Approximate spatial join: round coordinates to 2 decimals and match with nearest commune
        stops["stop_lat"] = pd.to_numeric(stops.get("stop_lat", pd.Series(dtype=float)), errors="coerce")
        stops["stop_lon"] = pd.to_numeric(stops.get("stop_lon", pd.Series(dtype=float)), errors="coerce")
        communes["lat_r"] = communes["latitude"].round(2)
        communes["lon_r"] = communes["longitude"].round(2)
        stops["lat_r"] = stops["stop_lat"].round(2)
        stops["lon_r"] = stops["stop_lon"].round(2)
        stops = stops.merge(
            communes[["code_commune", "lat_r", "lon_r"]],
            on=["lat_r", "lon_r"],
            how="left",
        )

    return stops


def ingest_gtfs() -> Path:
    zip_target = file_path("raw", "gtfs", "bnlca.zip")
    print("Downloading national stops database from transport.data.gouv.fr...")
    _download(BNLCA_URL, zip_target)

    print("Parsing stops...")
    stops, routes = _parse_stops(zip_target)
    print(f"  {len(stops):,} stops in database")

    # Load communes reference for spatial matching
    communes_path = file_path("raw", "communes", "communes.parquet")
    if not communes_path.exists():
        raise FileNotFoundError(
            "Communes reference not found. Run: python -m data_pipeline.ingestion.ingest_communes"
        )
    communes = pd.read_parquet(communes_path)

    stops = _match_stops_to_communes(stops, communes)
    stops = stops.dropna(subset=["code_commune"])

    # Count stops per commune
    agg = (
        stops.groupby("code_commune")
        .agg(stop_count=("code_commune", "size"))
        .reset_index()
    )

    # Add transport type flags if route info available
    for mode in ["has_train", "has_metro", "has_tram", "has_bus"]:
        agg[mode] = False

    if routes is not None and "route_type" in routes.columns:
        routes["route_type"] = pd.to_numeric(routes["route_type"], errors="coerce")
        # This is simplified — a full join would go stops→stop_times→trips→routes
        # For now we flag communes with any stops as having bus service at minimum
        agg["has_bus"] = True

    target = file_path("raw", "gtfs", "stops_per_commune.parquet")
    agg.to_parquet(target, index=False)

    meta = target.with_suffix(".metadata.txt")
    meta.write_text(
        "\n".join([
            f"source={BNLCA_URL}",
            f"total_stops={len(stops)}",
            f"communes_covered={len(agg)}",
            f"imported_at={datetime.now(timezone.utc).isoformat()}",
        ]),
        encoding="utf-8",
    )

    print(f"GTFS stops per commune stored at {target} ({len(agg):,} communes covered)")
    return target


def main() -> None:
    ingest_gtfs()


if __name__ == "__main__":
    main()
