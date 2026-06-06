from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlretrieve

from data_pipeline.settings import file_path


def ingest_dvf(source: str, year: int) -> Path:
    target = file_path("raw", "dvf", str(year), f"dvf_{year}.csv")

    if source.startswith(("http://", "https://")):
        urlretrieve(source, target)
    else:
        shutil.copy2(Path(source), target)

    metadata = target.with_suffix(".metadata.txt")
    metadata.write_text(
        "\n".join(
            [
                f"source={source}",
                f"year={year}",
                f"target={target}",
                f"imported_at={datetime.now(timezone.utc).isoformat()}",
            ]
        ),
        encoding="utf-8",
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a DVF CSV into the raw data lake.")
    parser.add_argument("--input", required=True, help="Local CSV path or public URL.")
    parser.add_argument("--year", required=True, type=int)
    args = parser.parse_args()

    target = ingest_dvf(args.input, args.year)
    print(f"DVF raw file stored at {target}")


if __name__ == "__main__":
    main()

