"""Carte des loyers (Ministère de la Transition écologique, edition 2025).

Predicted rent €/m² per commune, one CSV for apartments and one for houses.
Small dataset (~35k rows) -> bronze then plain SQL load, no Spark needed.
"""
import io
import os

import requests

EDITION_YEAR = 2025
SOURCES = {
    "loyers_appartement.csv": (
        "https://static.data.gouv.fr/resources/"
        "carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-2025/"
        "20251211-145010/pred-app-mef-dhup.csv"
    ),
    "loyers_maison.csv": (
        "https://static.data.gouv.fr/resources/"
        "carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-2025/"
        "20251211-145039/pred-mai-mef-dhup.csv"
    ),
}
BRONZE_PREFIX = "bronze/loyers"


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
    for filename, url in SOURCES.items():
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
        client.put_object(
            bucket,
            f"{BRONZE_PREFIX}/{filename}",
            io.BytesIO(resp.content),
            length=len(resp.content),
            content_type="text/csv",
        )
        print(f"bronze <- {filename} ({len(resp.content) / 1e6:.1f} MB)")


def _read_rents(client, bucket: str, filename: str) -> dict:
    """code INSEE -> (rent €/m², nb observations). French CSV: ';' and ','."""
    import csv

    obj = client.get_object(bucket, f"{BRONZE_PREFIX}/{filename}")
    try:
        raw = obj.read()
    finally:
        obj.close()
        obj.release_conn()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:  # the ministry ships Latin-1 CSVs
        text = raw.decode("latin-1")

    rents = {}
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        code = _parent_commune(row["INSEE_C"].strip('"'))
        rent = float(row["loypredm2"].replace(",", "."))
        nbobs = int(row.get("nbobs_com") or 0)
        if code in rents:  # arrondissements aggregated into the parent city
            prev_rent, prev_obs = rents[code]
            total = max(prev_obs + nbobs, 1)
            rent = (prev_rent * prev_obs + rent * nbobs) / total if prev_obs + nbobs else (prev_rent + rent) / 2
            nbobs = prev_obs + nbobs
        rents[code] = (round(rent, 2), nbobs)
    return rents


def _parent_commune(code: str) -> str:
    """Same remap as the DVF silver job: arrondissements -> parent city."""
    if "75101" <= code <= "75120":
        return "75056"  # Paris
    if "13201" <= code <= "13216":
        return "13055"  # Marseille
    if "69381" <= code <= "69389":
        return "69123"  # Lyon
    return code


def load_postgres(conn) -> None:
    from psycopg2.extras import execute_values

    client = _minio_client()
    bucket = os.environ["LAKE_BUCKET"]
    apartments = _read_rents(client, bucket, "loyers_appartement.csv")
    houses = _read_rents(client, bucket, "loyers_maison.csv")

    rows = [
        (
            code,
            apartments.get(code, (None, 0))[0],
            houses.get(code, (None, 0))[0],
            apartments.get(code, (None, 0))[1],
            EDITION_YEAR,
        )
        for code in sorted(set(apartments) | set(houses))
    ]

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO gold.loyers_commune
                (code_insee, rent_m2_apartment, rent_m2_house,
                 nb_observations, edition_year)
            VALUES %s
            ON CONFLICT (code_insee) DO UPDATE SET
                rent_m2_apartment = EXCLUDED.rent_m2_apartment,
                rent_m2_house = EXCLUDED.rent_m2_house,
                nb_observations = EXCLUDED.nb_observations,
                edition_year = EXCLUDED.edition_year
            """,
            rows,
            page_size=1000,
        )
    conn.commit()
    print(f"gold.loyers_commune loaded: {len(rows)} communes")
