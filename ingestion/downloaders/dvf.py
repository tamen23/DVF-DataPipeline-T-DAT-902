"""DVF (Demandes de valeurs foncières, Etalab geolocated version).

One ~500 MB csv.gz per year, full France. Stored as-is in bronze.
"""
import os

import requests

URL_TEMPLATE = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/full.csv.gz"
BRONZE_PREFIX = "bronze/dvf"


def _minio_client():
    from minio import Minio

    return Minio(
        os.environ["MINIO_ENDPOINT"].removeprefix("http://"),
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )


def years_to_load() -> list[str]:
    """Years come from the DVF_YEARS env var (comma-separated)."""
    return [y.strip() for y in os.environ.get("DVF_YEARS", "2024").split(",")]


def download_to_bronze() -> None:
    client = _minio_client()
    bucket = os.environ["LAKE_BUCKET"]
    for year in years_to_load():
        key = f"{BRONZE_PREFIX}/year={year}/full.csv.gz"
        # skip if already in the lake (bronze is immutable raw)
        if any(True for _ in client.list_objects(bucket, prefix=key)):
            print(f"bronze: {key} already present, skipping")
            continue
        url = URL_TEMPLATE.format(year=year)
        print(f"downloading {url} ...")
        with requests.get(url, stream=True, timeout=1800) as resp:
            resp.raise_for_status()
            size = int(resp.headers["Content-Length"])
            client.put_object(
                bucket, key, resp.raw, length=size,
                content_type="application/gzip",
            )
        print(f"bronze <- {key} ({size / 1e6:.0f} MB)")
