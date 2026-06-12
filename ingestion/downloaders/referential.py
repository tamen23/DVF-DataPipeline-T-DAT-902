"""Geographic referential: download to bronze, then load into PostGIS.

Sources:
- geo.api.gouv.fr        -> attributes (codes, names, population, postal codes)
- france-geojson (IGN)   -> simplified boundary polygons (enough for choropleths)
"""
import io
import json
import os

import requests

SOURCES = {
    "regions.json": "https://geo.api.gouv.fr/regions",
    "departements.json": "https://geo.api.gouv.fr/departements",
    "communes.json": (
        "https://geo.api.gouv.fr/communes"
        "?fields=code,nom,codeDepartement,codeRegion,population,codesPostaux"
    ),
    "regions.geojson": (
        "https://raw.githubusercontent.com/gregoiredavid/france-geojson"
        "/master/regions-version-simplifiee.geojson"
    ),
    "departements.geojson": (
        "https://raw.githubusercontent.com/gregoiredavid/france-geojson"
        "/master/departements-version-simplifiee.geojson"
    ),
    "communes.geojson": (
        "https://raw.githubusercontent.com/gregoiredavid/france-geojson"
        "/master/communes-version-simplifiee.geojson"
    ),
}

BRONZE_PREFIX = "bronze/referential"


def _minio_client():
    from minio import Minio

    return Minio(
        os.environ["MINIO_ENDPOINT"].removeprefix("http://"),
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )


def download_to_bronze() -> None:
    """Full raw copy of each source into the lake (bronze layer)."""
    client = _minio_client()
    bucket = os.environ["LAKE_BUCKET"]
    for filename, url in SOURCES.items():
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        data = resp.content
        client.put_object(
            bucket,
            f"{BRONZE_PREFIX}/{filename}",
            io.BytesIO(data),
            length=len(data),
            content_type="application/json",
        )
        print(f"bronze <- {filename} ({len(data) / 1e6:.1f} MB)")


def _read_bronze(client, bucket: str, filename: str):
    obj = client.get_object(bucket, f"{BRONZE_PREFIX}/{filename}")
    try:
        return json.load(obj)
    finally:
        obj.close()
        obj.release_conn()


def _geometries_by_code(geojson: dict) -> dict:
    # some features carry a null geometry; skip them so the row gets a
    # SQL NULL instead of the invalid GeoJSON string "null"
    return {
        feat["properties"]["code"]: json.dumps(feat["geometry"])
        for feat in geojson["features"]
        if feat.get("geometry") is not None
    }


def load_postgres(conn) -> None:
    """Upsert regions, departments and communes (with geometry) into PostGIS.

    The referential is small (~35k rows) so plain SQL is the right tool here —
    Spark is reserved for the volumetric datasets (DVF & co).
    """
    from psycopg2.extras import execute_values

    client = _minio_client()
    bucket = os.environ["LAKE_BUCKET"]

    regions = _read_bronze(client, bucket, "regions.json")
    departements = _read_bronze(client, bucket, "departements.json")
    communes = _read_bronze(client, bucket, "communes.json")
    region_geom = _geometries_by_code(_read_bronze(client, bucket, "regions.geojson"))
    dep_geom = _geometries_by_code(_read_bronze(client, bucket, "departements.geojson"))
    commune_geom = _geometries_by_code(_read_bronze(client, bucket, "communes.geojson"))

    known_regions = {r["code"] for r in regions}
    known_departments = {d["code"] for d in departements}

    geom_sql = "ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))"

    with conn.cursor() as cur:
        execute_values(
            cur,
            f"""
            INSERT INTO referential.region (code, name, geom)
            VALUES %s
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, geom = EXCLUDED.geom
            """,
            [(r["code"], r["nom"], region_geom.get(r["code"])) for r in regions],
            template=f"(%s, %s, {geom_sql})",
        )

        execute_values(
            cur,
            f"""
            INSERT INTO referential.department (code, name, region_code, geom)
            VALUES %s
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name,
                region_code = EXCLUDED.region_code, geom = EXCLUDED.geom
            """,
            [
                (d["code"], d["nom"], d["codeRegion"], dep_geom.get(d["code"]))
                for d in departements
            ],
            template=f"(%s, %s, %s, {geom_sql})",
        )

        execute_values(
            cur,
            f"""
            INSERT INTO referential.commune
                (code_insee, name, department_code, region_code,
                 population, postal_codes, geom)
            VALUES %s
            ON CONFLICT (code_insee) DO UPDATE SET name = EXCLUDED.name,
                department_code = EXCLUDED.department_code,
                region_code = EXCLUDED.region_code,
                population = EXCLUDED.population,
                postal_codes = EXCLUDED.postal_codes,
                geom = EXCLUDED.geom
            """,
            [
                (
                    c["code"],
                    c["nom"],
                    c["codeDepartement"],
                    c["codeRegion"],
                    c.get("population"),
                    c.get("codesPostaux", []),
                    commune_geom.get(c["code"]),
                )
                for c in communes
                # scope = the 101 official departments (métropole + DROM);
                # overseas collectivities (975, 977, 98x...) reference
                # "departments" that don't exist in the referential
                if c.get("codeDepartement") in known_departments
                and c.get("codeRegion") in known_regions
            ],
            template=f"(%s, %s, %s, %s, %s, %s, {geom_sql})",
            page_size=500,
        )

    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT (SELECT count(*) FROM referential.region),"
            "       (SELECT count(*) FROM referential.department),"
            "       (SELECT count(*) FROM referential.commune)"
        )
        nb_reg, nb_dep, nb_com = cur.fetchone()
    print(f"referential loaded: {nb_reg} regions, {nb_dep} departments, {nb_com} communes")
