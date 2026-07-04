from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from data_pipeline.settings import file_path

# geo.api.gouv.fr — communes with coordinates, department, region
GEO_API_URL = "https://geo.api.gouv.fr/communes?fields=code,nom,codeDepartement,codeRegion,centre,population&format=json&geometry=centre"

# regions reference
REGIONS_URL = "https://geo.api.gouv.fr/regions?fields=code,nom&format=json"

# departments reference
DEPARTEMENTS_URL = "https://geo.api.gouv.fr/departements?fields=code,nom,codeRegion&format=json"


def _get_json(url: str) -> list[dict]:
    response = requests.get(url, timeout=60, headers={"User-Agent": "homepedia/1.0"})
    response.raise_for_status()
    return response.json()


def ingest_communes() -> Path:
    print("Downloading communes from geo.api.gouv.fr...")
    raw = _get_json(GEO_API_URL)
    print(f"  {len(raw):,} communes retrieved")

    rows = []
    for c in raw:
        centre = c.get("centre", {}).get("coordinates", [None, None])
        rows.append({
            "code_commune": c.get("code"),
            "nom_commune": c.get("nom"),
            "code_departement": c.get("codeDepartement"),
            "code_region": c.get("codeRegion"),
            "longitude": centre[0],
            "latitude": centre[1],
            "population": c.get("population"),
        })

    frame = pd.DataFrame(rows)
    target = file_path("raw", "communes", "communes.parquet")
    frame.to_parquet(target, index=False)
    _write_metadata(target, GEO_API_URL)
    print(f"Communes stored at {target}")
    return target


def ingest_regions() -> Path:
    print("Downloading regions...")
    raw = _get_json(REGIONS_URL)
    frame = pd.DataFrame([{"code_region": r["code"], "nom_region": r["nom"]} for r in raw])
    target = file_path("raw", "communes", "regions.parquet")
    frame.to_parquet(target, index=False)
    print(f"  {len(frame)} regions stored at {target}")
    return target


def ingest_departements() -> Path:
    print("Downloading departements...")
    raw = _get_json(DEPARTEMENTS_URL)
    frame = pd.DataFrame([{"code_departement": d["code"], "nom_departement": d["nom"], "code_region": d["codeRegion"]} for d in raw])
    target = file_path("raw", "communes", "departements.parquet")
    frame.to_parquet(target, index=False)
    print(f"  {len(frame)} departements stored at {target}")
    return target


def _write_metadata(target: Path, source: str) -> None:
    meta = target.with_suffix(".metadata.txt")
    meta.write_text(
        "\n".join([
            f"source={source}",
            f"target={target}",
            f"imported_at={datetime.now(timezone.utc).isoformat()}",
        ]),
        encoding="utf-8",
    )


def main() -> None:
    ingest_regions()
    ingest_departements()
    ingest_communes()
    print("\nDone. All commune reference data stored in raw/communes/")


if __name__ == "__main__":
    main()
