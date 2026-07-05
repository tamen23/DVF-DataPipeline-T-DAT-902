"""Charge l'historique de prix démo dans Postgres sous la forme du mart
`mart_commune_real_estate` (même contrat que le modèle dbt), pour que les
panneaux Grafana « Prix moyen national » et « Marché immobilier par commune »
aient des données sur le déploiement léger (où dbt ne tourne pas).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://homepedia:homepedia@localhost:5433/homepedia"
).replace("postgresql://", "postgresql+psycopg2://")

frames = []
for path in sorted((ROOT / "data_lake" / "gold" / "real_estate").glob("*/real_estate_commune_*.parquet")):
    frame = pd.read_parquet(path)
    if not frame.empty:
        frames.append(frame)

if not frames:
    print("Aucun historique gold trouvé — mart non chargé.")
    raise SystemExit(0)

history = pd.concat(frames, ignore_index=True)
mart = history[[
    "nom_commune", "code_commune", "year", "transaction_count",
    "avg_price", "avg_price_m2", "median_price_m2", "avg_surface",
]].copy()
mart["population"] = pd.NA

engine = create_engine(DATABASE_URL)
mart.to_sql("mart_commune_real_estate", engine, if_exists="replace", index=False)
print(f"mart_commune_real_estate: {len(mart):,} lignes ({history['year'].min()}-{history['year'].max()})")
