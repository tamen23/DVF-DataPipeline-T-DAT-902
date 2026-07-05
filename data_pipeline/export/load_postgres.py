from __future__ import annotations

"""
Loads the data lake into PostgreSQL/PostGIS (database/schema.sql) so the
relational branch — psql, dbt models, Power BI over Postgres — runs on the
same data as the Hive stack.

Reads:
  raw/communes/{regions,departements,communes}.parquet   (ingest_communes)
  silver/dvf/{year}/real_estate_transactions_{year}.parquet (silver_dvf)
  gold/territories/territory_scores.parquet              (build_territory_gold)

The load is idempotent: tables are truncated and fully reloaded.

Usage:
  python -m data_pipeline.export.load_postgres --year 2023
  python -m data_pipeline.export.load_postgres --year 2023 --skip-transactions
  DATABASE_URL=postgresql://user:pwd@host:5432/db python -m data_pipeline.export.load_postgres --year 2023
"""

import argparse
import os

import pandas as pd
from sqlalchemy import create_engine, text

from data_pipeline.settings import DATA_LAKE_PATH, PROJECT_ROOT

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://homepedia:homepedia@localhost:5433/homepedia"
).replace("postgresql://", "postgresql+psycopg2://")

TRANSACTION_COLUMNS = [
    "date_mutation", "valeur_fonciere", "surface_reelle_bati",
    "nombre_pieces", "type_local", "commune_id", "prix_m2", "source",
]


def _read_parquet(relative: str) -> pd.DataFrame | None:
    path = DATA_LAKE_PATH / relative
    if not path.exists():
        print(f"  [skip] {relative} not found — run the ingestion/pipeline first")
        return None
    return pd.read_parquet(path)


def _id_map(conn, table: str, code_column: str) -> dict[str, int]:
    rows = conn.execute(text(f"SELECT id, {code_column} FROM {table}")).fetchall()
    return {code: id_ for id_, code in rows}


def init_schema(engine) -> None:
    """Apply database/schema.sql (idempotent: IF NOT EXISTS / OR REPLACE only)."""
    schema_sql = (PROJECT_ROOT / "database" / "schema.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(schema_sql)
    print("  schema applied (database/schema.sql)")


def load_reference_tables(engine) -> None:
    regions = _read_parquet("raw/communes/regions.parquet")
    departements = _read_parquet("raw/communes/departements.parquet")
    communes = _read_parquet("raw/communes/communes.parquet")
    if regions is None or departements is None or communes is None:
        raise SystemExit("Reference data missing — run: python -m data_pipeline.ingestion.ingest_communes")

    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE territorial_scores, real_estate_transactions, communes, departements, regions "
            "RESTART IDENTITY CASCADE"
        ))

    regions[["code_region", "nom_region"]].to_sql("regions", engine, if_exists="append", index=False)
    print(f"  regions: {len(regions):,} rows")

    with engine.connect() as conn:
        region_ids = _id_map(conn, "regions", "code_region")
    departements = departements.assign(region_id=departements["code_region"].map(region_ids))
    departements[["code_departement", "nom_departement", "region_id"]].to_sql(
        "departements", engine, if_exists="append", index=False
    )
    print(f"  departements: {len(departements):,} rows")

    with engine.connect() as conn:
        dept_ids = _id_map(conn, "departements", "code_departement")
    communes = communes.assign(
        departement_id=communes["code_departement"].map(dept_ids),
        code_postal=(
            communes["codes_postaux"].astype(str).str.split(",").str[0].replace({"": None, "None": None})
            if "codes_postaux" in communes.columns else None
        ),
    )
    communes[[
        "code_commune", "nom_commune", "code_postal", "departement_id",
        "latitude", "longitude", "population",
    ]].to_sql("communes", engine, if_exists="append", index=False, chunksize=5000)

    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE communes SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) "
            "WHERE longitude IS NOT NULL AND latitude IS NOT NULL"
        ))
    print(f"  communes: {len(communes):,} rows (geom computed)")


def load_transactions(engine, year: int) -> None:
    transactions = _read_parquet(f"silver/dvf/{year}/real_estate_transactions_{year}.parquet")
    if transactions is None:
        return

    with engine.connect() as conn:
        commune_ids = _id_map(conn, "communes", "code_commune")
    transactions = transactions.assign(commune_id=transactions["code_commune"].map(commune_ids))
    unmapped = transactions["commune_id"].isna().sum()
    if unmapped:
        print(f"  [warn] {unmapped:,} transactions dropped (commune code not in reference)")
    transactions = transactions.dropna(subset=["commune_id"])

    transactions[TRANSACTION_COLUMNS].to_sql(
        "real_estate_transactions", engine, if_exists="append", index=False, chunksize=5000
    )
    print(f"  real_estate_transactions ({year}): {len(transactions):,} rows")


def load_territorial_scores(engine, year: int) -> None:
    scores = _read_parquet("gold/territories/territory_scores.parquet")
    if scores is None:
        return

    with engine.connect() as conn:
        commune_ids = _id_map(conn, "communes", "code_commune")

    persona_cols = [c for c in scores.columns if c.startswith("score_")]
    mapped = pd.DataFrame({
        "commune_id": scores["code_commune"].map(commune_ids),
        "year": year,
        # schema.sql score names predate the persona model: map the closest
        # gold columns (affordability -> real_estate, income -> socio_economic,
        # global = mean of the persona scores).
        "real_estate_score": scores.get("affordability_score"),
        "network_score": scores.get("network_score"),
        "transport_score": scores.get("transport_score"),
        "socio_economic_score": scores.get("income_score"),
        "global_score": scores[persona_cols].mean(axis=1) if persona_cols else None,
    }).dropna(subset=["commune_id"])

    mapped.to_sql("territorial_scores", engine, if_exists="append", index=False, chunksize=5000)
    print(f"  territorial_scores: {len(mapped):,} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the data lake into PostgreSQL/PostGIS.")
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--skip-transactions", action="store_true",
                        help="Load only reference tables and scores (faster).")
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)
    print(f"Loading data lake into {engine.url.render_as_string(hide_password=True)}\n")

    init_schema(engine)
    load_reference_tables(engine)
    if not args.skip_transactions:
        load_transactions(engine, args.year)
    load_territorial_scores(engine, args.year)
    print("\nDone. dbt models can now run: cd dbt && dbt run")


if __name__ == "__main__":
    main()
