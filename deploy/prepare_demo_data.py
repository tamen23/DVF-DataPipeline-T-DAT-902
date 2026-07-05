"""Prépare le jeu de données de DÉMONSTRATION pour le déploiement léger.

Génère dans le data lake local de l'image :
  - les scores territoires démo (generate_demo_territories)
  - un historique gold DVF plausible 2019-2023 (pour la courbe + le modèle IA)
  - les prédictions IA 2026 (RandomForest réel, entraîné sur cet historique)
  - des annonces avec textes FR + l'analyse NLP (sentiment + nuage de mots)
  - les stats silver listings (écart annonces vs DVF)

Données synthétiques assumées : le pipeline réel produit les mêmes artefacts
depuis DVF/ANIL/ARCEP — ce script n'existe que pour la démo autoportante.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_pipeline.generation.generate_demo_territories import main as generate_demo  # noqa: E402

random.seed(42)
rng = np.random.default_rng(42)

# 1. Territoires démo
generate_demo()
demo_path = ROOT / "data_lake" / "gold" / "demo" / "territory_scores.parquet"
demo = pd.read_parquet(demo_path)
territories = ROOT / "data_lake" / "gold" / "territories"
territories.mkdir(parents=True, exist_ok=True)
demo.to_parquet(territories / "territory_scores.parquet", index=False)
print(f"territoires: {len(demo)} communes")

# 2. Historique gold 2019-2023 (croissance structurelle par commune + bruit)
extra_codes = [f"{d:02d}{i:03d}" for d in range(1, 60) for i in range(1, 6)]
base = pd.concat([
    demo[["code_commune", "nom_commune", "avg_price_m2"]],
    pd.DataFrame({
        "code_commune": extra_codes,
        "nom_commune": [f"Commune-{c}" for c in extra_codes],
        "avg_price_m2": rng.uniform(900, 6500, len(extra_codes)),
    }),
], ignore_index=True)
growth = rng.uniform(0.01, 0.07, len(base))
prev = None
for i, year in enumerate(range(2019, 2024)):
    prices = base["avg_price_m2"].values * (1 + growth) ** i * rng.normal(1, 0.02, len(base))
    frame = pd.DataFrame({
        "code_commune": base["code_commune"],
        "nom_commune": base["nom_commune"],
        "year": year,
        "transaction_count": rng.integers(5, 400, len(base)),
        "avg_price": prices * rng.uniform(45, 75, len(base)),
        "avg_price_m2": prices,
        "median_price_m2": prices * rng.normal(0.97, 0.01, len(base)),
        "avg_surface": rng.uniform(45, 90, len(base)),
        "price_m2_yoy_variation": float("nan") if prev is None else 0.0,
    })
    if prev is not None:
        frame["price_m2_yoy_variation"] = (prices - prev) / prev
    prev = prices
    out = ROOT / "data_lake" / "gold" / "real_estate" / str(year)
    out.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out / f"real_estate_commune_{year}.parquet", index=False)
print("historique gold: 2019-2023")

# 3. Prédictions IA
from data_pipeline.ml.predict_prices import predict  # noqa: E402
predict(2026)

# 4. Annonces démo (textes FR) + NLP + silver listings
POS = [
    "Superbe appartement lumineux et spacieux avec balcon, proche commerces et transports",
    "Maison charmante entièrement rénovée, jardin ensoleillé, quartier calme et recherché",
    "Bel appartement moderne, terrasse avec vue magnifique, résidence sécurisée, parking",
    "Idéal famille : agréable, proche écoles, cadre paisible avec beaucoup de verdure",
    "Rare : appartement neuf très lumineux, séjour spacieux, quartier dynamique et convivial",
]
NEG = [
    "Appartement sombre avec travaux à prévoir, rue bruyante, immeuble vétuste",
    "Petit logement humide, quartier avec nuisances et problèmes d'insécurité",
    "Maison dégradée, travaux importants, secteur enclavé éloigné des commerces",
]
rows = []
for _, c in demo.iterrows():
    ratio = float(c.get("score_famille", 70)) / 100
    for i in range(random.randint(8, 15)):
        text = random.choice(POS if random.random() < ratio else NEG)
        price_m2 = float(c["avg_price_m2"]) * random.uniform(1.02, 1.18)  # marché affiché > DVF
        surface = random.randint(25, 110)
        rows.append({
            "listing_id": f"demo-{c['code_commune']}-{i}",
            "source": "seloger",
            "commune_code": str(c["code_commune"]),
            "city": c["nom_commune"],
            "title": text.split(",")[0],
            "description": text,
            "price": round(price_m2 * surface),
            "surface_m2": surface,
            "price_m2": round(price_m2),
            "scraped_at": "2026-07-05T10:00:00+00:00",
        })
out = ROOT / "data_lake" / "bronze" / "listings" / "seloger" / "2026-07-05"
out.mkdir(parents=True, exist_ok=True)
pd.DataFrame(rows).to_parquet(out / "batch_demo.parquet", index=False)
print(f"annonces demo: {len(rows)}")

from data_pipeline.nlp.analyze_listings_text import build_text_analysis  # noqa: E402
build_text_analysis()
from data_pipeline.transformation.silver_listings import build_silver_listings  # noqa: E402
build_silver_listings()
print("préparation démo terminée")
