from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

import requests

from data_pipeline.settings import file_path

# Official DataGouv DVF URLs by year
DVF_URLS: dict[int, str] = {
    2019: "https://files.data.gouv.fr/geo-dvf/latest/csv/2019/full.csv.gz",
    2020: "https://files.data.gouv.fr/geo-dvf/latest/csv/2020/full.csv.gz",
    2021: "https://files.data.gouv.fr/geo-dvf/latest/csv/2021/full.csv.gz",
    2022: "https://files.data.gouv.fr/geo-dvf/latest/csv/2022/full.csv.gz",
    2023: "https://files.data.gouv.fr/geo-dvf/latest/csv/2023/full.csv.gz",
    2024: "https://files.data.gouv.fr/geo-dvf/latest/csv/2024/full.csv.gz",
    2025: "https://files.data.gouv.fr/geo-dvf/latest/csv/2025/full.csv.gz",
}

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


def _download(url: str, target: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as response:
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


def _write_metadata(target: Path, source: str, year: int) -> None:
    metadata = target.with_suffix("").with_suffix(".metadata.txt") if target.suffix == ".gz" else target.with_suffix(".metadata.txt")
    metadata.write_text(
        "\n".join([
            f"source={source}",
            f"year={year}",
            f"target={target}",
            f"imported_at={datetime.now(timezone.utc).isoformat()}",
        ]),
        encoding="utf-8",
    )


def ingest_dvf(source: str | None, year: int) -> Path:
    suffix = ".csv.gz" if (source is None or source.endswith(".gz")) else ".csv"
    target = file_path("raw", "dvf", str(year), f"dvf_{year}{suffix}")

    if source is None:
        url = DVF_URLS.get(year)
        if url is None:
            raise ValueError(f"No default DVF URL for year {year}. Provide --input explicitly.")
        print(f"Downloading DVF {year} from DataGouv: {url}")
        _download(url, target)
    elif source.startswith(("http://", "https://")):
        print(f"Downloading DVF {year} from: {source}")
        _download(source, target)
    else:
        shutil.copy2(Path(source), target)
        print(f"Copied {source} -> {target}")

    _write_metadata(target, source or DVF_URLS[year], year)
    print(f"DVF raw file stored at {target}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a DVF CSV into the raw data lake.")
    parser.add_argument("--input", default=None, help="Local path or URL. Omit to use the official DataGouv URL for the given year.")
    parser.add_argument("--year", required=True, type=int, help="Year to ingest (2019-2024).")
    args = parser.parse_args()
    ingest_dvf(args.input, args.year)


if __name__ == "__main__":
    main()
