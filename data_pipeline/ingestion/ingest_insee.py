from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import requests

from data_pipeline.settings import file_path

# INSEE — Fichier Filosofi (revenus, pauvreté par commune)
# Source: https://www.insee.fr/fr/statistiques/6036907
INSEE_FILOSOFI_URLS: dict[int, str] = {
    2020: "https://www.insee.fr/fr/statistiques/fichier/6036907/indic-struct-distrib-revenu-2020-COMMUNES_csv.zip",
    2021: "https://www.insee.fr/fr/statistiques/fichier/6036907/indic-struct-distrib-revenu-2021-COMMUNES_csv.zip",
}

# INSEE — Recensement de la population (population légale par commune)
# Source: https://www.insee.fr/fr/statistiques/6683035
INSEE_POP_URLS: dict[int, str] = {
    2020: "https://www.insee.fr/fr/statistiques/fichier/6683035/ensemble.zip",
    2021: "https://www.insee.fr/fr/statistiques/fichier/6683035/ensemble.zip",
}

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB


def _download(url: str, target: Path) -> None:
    headers = {"User-Agent": "homepedia-data-pipeline/1.0"}
    with requests.get(url, stream=True, timeout=120, headers=headers) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0
        with open(target, "wb") as fh:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                fh.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r  {pct:.1f}%  ({downloaded // 1_048_576} MB / {total // 1_048_576} MB)", end="", flush=True)
        print()


def _write_metadata(target: Path, source: str, year: int, dataset: str) -> None:
    meta = target.with_suffix(".metadata.txt")
    meta.write_text(
        "\n".join([
            f"source={source}",
            f"dataset={dataset}",
            f"year={year}",
            f"target={target}",
            f"imported_at={datetime.now(timezone.utc).isoformat()}",
        ]),
        encoding="utf-8",
    )


def ingest_insee_filosofi(year: int) -> Path:
    url = INSEE_FILOSOFI_URLS.get(year)
    if url is None:
        raise ValueError(f"No Filosofi URL configured for year {year}. Available: {sorted(INSEE_FILOSOFI_URLS)}")

    target = file_path("raw", "insee", "filosofi", str(year), f"filosofi_{year}.zip")
    print(f"Downloading INSEE Filosofi {year}...")
    _download(url, target)
    _write_metadata(target, url, year, "filosofi")
    print(f"Stored at {target}")
    return target


def ingest_insee_population(year: int) -> Path:
    url = INSEE_POP_URLS.get(year)
    if url is None:
        raise ValueError(f"No population URL configured for year {year}. Available: {sorted(INSEE_POP_URLS)}")

    target = file_path("raw", "insee", "population", str(year), f"population_{year}.zip")
    print(f"Downloading INSEE population {year}...")
    _download(url, target)
    _write_metadata(target, url, year, "population")
    print(f"Stored at {target}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest INSEE datasets (Filosofi + population) into the raw data lake.")
    parser.add_argument("--year", required=True, type=int, help="Reference year (e.g. 2020, 2021).")
    parser.add_argument(
        "--dataset",
        choices=["filosofi", "population", "all"],
        default="all",
        help="Which dataset to download (default: all).",
    )
    args = parser.parse_args()

    if args.dataset in ("filosofi", "all"):
        ingest_insee_filosofi(args.year)

    if args.dataset in ("population", "all"):
        ingest_insee_population(args.year)


if __name__ == "__main__":
    main()
