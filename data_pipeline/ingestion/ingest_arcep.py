from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import requests

from data_pipeline.settings import file_path

# ARCEP open data — couverture mobile par commune (4G/5G)
# Source: https://www.data.gouv.fr/fr/datasets/mon-reseau-mobile/
ARCEP_URL = "https://www.data.gouv.fr/fr/datasets/r/35e52723-a0aa-4f57-a5dd-ff4f58c6ee75"

CHUNK_SIZE = 4 * 1024 * 1024


def _download(url: str, target: Path) -> None:
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": "homepedia/1.0"}) as response:
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


def ingest_arcep() -> Path:
    target = file_path("raw", "arcep", "couverture_mobile.csv")
    print(f"Downloading ARCEP mobile coverage data...")
    _download(ARCEP_URL, target)

    meta = target.with_suffix(".metadata.txt")
    meta.write_text(
        "\n".join([
            f"source={ARCEP_URL}",
            f"target={target}",
            f"imported_at={datetime.now(timezone.utc).isoformat()}",
        ]),
        encoding="utf-8",
    )
    print(f"ARCEP data stored at {target}")
    return target


def main() -> None:
    ingest_arcep()


if __name__ == "__main__":
    main()
