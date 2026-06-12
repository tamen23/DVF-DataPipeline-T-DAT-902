"""INSEE Filosofi 2021 (final edition): median income & poverty per commune.

One zip from insee.fr containing the commune-level CSV.
Small dataset -> bronze then plain SQL load, no Spark needed.
"""
import csv
import io
import os
import zipfile

import requests

EDITION_YEAR = 2021
URL = (
    "https://www.insee.fr/fr/statistiques/fichier/7756729/"
    "base-cc-filosofi-2021-geo2025_csv.zip"
)
BRONZE_KEY = "bronze/insee/filosofi_2021_csv.zip"


def _minio_client():
    from minio import Minio

    return Minio(
        os.environ["MINIO_ENDPOINT"].removeprefix("http://"),
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )


def download_to_bronze() -> None:
    client = _minio_client()
    bucket = os.environ["LAKE_BUCKET"]
    resp = requests.get(URL, timeout=600, headers={"User-Agent": "homepedia-epitech"})
    resp.raise_for_status()
    client.put_object(
        bucket,
        BRONZE_KEY,
        io.BytesIO(resp.content),
        length=len(resp.content),
        content_type="application/zip",
    )
    print(f"bronze <- filosofi zip ({len(resp.content) / 1e6:.1f} MB)")


def _to_float(value: str):
    value = (value or "").strip()
    return float(value.replace(",", ".")) if value else None


def load_postgres(conn) -> None:
    """The 2025 INSEE delivery is in long/tidy format: one row per
    (GEO, FILOSOFI_MEASURE) with the value in OBS_VALUE. We pivot the two
    measures we serve: MED_SL (median standard of living, €) and
    PR_MD60 (poverty rate, %)."""
    from psycopg2.extras import execute_values

    client = _minio_client()
    bucket = os.environ["LAKE_BUCKET"]
    obj = client.get_object(bucket, BRONZE_KEY)
    try:
        archive = zipfile.ZipFile(io.BytesIO(obj.read()))
    finally:
        obj.close()
        obj.release_conn()

    name = next(n for n in archive.namelist() if n.lower().endswith("_data.csv"))
    text = archive.read(name).decode("utf-8-sig")
    print(f"reading {name} from the archive")

    medians, poverties = {}, {}
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        if row["GEO_OBJECT"] != "COM":
            continue
        value = _to_float(row["OBS_VALUE"])
        if value is None:
            continue  # confidential (statistical secrecy)
        if row["FILOSOFI_MEASURE"] == "MED_SL":
            medians[row["GEO"]] = value
        elif row["FILOSOFI_MEASURE"] == "PR_MD60":
            poverties[row["GEO"]] = value

    rows = [
        (code, medians.get(code), poverties.get(code), EDITION_YEAR)
        for code in sorted(set(medians) | set(poverties))
    ]

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO gold.filosofi_commune
                (code_insee, median_income, poverty_rate, edition_year)
            VALUES %s
            ON CONFLICT (code_insee) DO UPDATE SET
                median_income = EXCLUDED.median_income,
                poverty_rate = EXCLUDED.poverty_rate,
                edition_year = EXCLUDED.edition_year
            """,
            rows,
            page_size=1000,
        )
    conn.commit()
    print(f"gold.filosofi_commune loaded: {len(rows)} communes")
