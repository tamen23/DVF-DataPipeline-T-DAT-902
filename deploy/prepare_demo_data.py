"""Prépare les données pour le déploiement léger.

Mode réel  : si les parquets sont bundlés dans l'image (territory_scores + DVF 2022-2023),
             on les utilise directement et on backcaste 2019-2021.
Mode démo  : fallback à 16 communes synthétiques si aucun parquet n'est trouvé.

Produit toujours :
  - historique gold complet 2019-2023
  - prédictions IA 2026 (RandomForest)
  - annonces + analyse NLP + silver listings
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

random.seed(42)
rng = np.random.default_rng(42)

# ── 1. Territoires ───────────────────────────────────────────────────────────
territories_path = ROOT / "data_lake" / "gold" / "territories" / "territory_scores.parquet"

if territories_path.exists():
    demo = pd.read_parquet(territories_path)
    print(f"territoires: {len(demo)} communes réelles (parquet bundlé)")
else:
    from data_pipeline.generation.generate_demo_territories import main as generate_demo  # noqa: E402
    generate_demo()
    demo_path = ROOT / "data_lake" / "gold" / "demo" / "territory_scores.parquet"
    demo = pd.read_parquet(demo_path)
    territories_path.parent.mkdir(parents=True, exist_ok=True)
    demo.to_parquet(territories_path, index=False)
    print(f"territoires: {len(demo)} communes (fallback démo)")

# ── 2. Historique gold 2019-2023 ─────────────────────────────────────────────
real_estate_base = ROOT / "data_lake" / "gold" / "real_estate"
re22_path = real_estate_base / "2022" / "real_estate_commune_2022.parquet"
re23_path = real_estate_base / "2023" / "real_estate_commune_2023.parquet"

if re22_path.exists() and re23_path.exists():
    re2022 = pd.read_parquet(re22_path)
    re2023 = pd.read_parquet(re23_path)
    print(f"real_estate: {len(re2022)} communes 2022, {len(re2023)} communes 2023 (réels)")

    # Backcast 2019-2021 en partant des prix 2022
    base = re2022[["code_commune", "nom_commune", "avg_price_m2"]].copy()
    growth = rng.uniform(0.01, 0.07, len(base))

    prev = None
    for i, year in enumerate(range(2019, 2022)):
        # (1+g)^(i-3) : i=0→/g^3, i=1→/g^2, i=2→/g^1
        factor = (1 + growth) ** (i - 3)
        prices = base["avg_price_m2"].values * factor * rng.normal(1, 0.02, len(base))
        prices = np.clip(prices, 500, 30_000)
        frame = pd.DataFrame({
            "code_commune": base["code_commune"].values,
            "nom_commune": base["nom_commune"].values,
            "year": year,
            "transaction_count": rng.integers(5, 400, len(base)),
            "avg_price": prices * rng.uniform(45, 75, len(base)),
            "avg_price_m2": prices,
            "median_price_m2": prices * rng.normal(0.97, 0.01, len(base)),
            "avg_surface": rng.uniform(45, 90, len(base)),
            "price_m2_yoy_variation": np.nan if prev is None else (prices - prev) / np.where(prev == 0, 1, prev),
        })
        prev = prices
        out = real_estate_base / str(year)
        out.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out / f"real_estate_commune_{year}.parquet", index=False)

    print("historique gold: 2019-2021 (backcast) + 2022-2023 (réels)")

else:
    # Fallback: synthétique complet 2019-2023
    base = demo[["code_commune", "nom_commune", "avg_price_m2"]].copy()
    growth = rng.uniform(0.01, 0.07, len(base))
    prev = None
    for i, year in enumerate(range(2019, 2024)):
        prices = base["avg_price_m2"].values * (1 + growth) ** i * rng.normal(1, 0.02, len(base))
        frame = pd.DataFrame({
            "code_commune": base["code_commune"].values,
            "nom_commune": base["nom_commune"].values,
            "year": year,
            "transaction_count": rng.integers(5, 400, len(base)),
            "avg_price": prices * rng.uniform(45, 75, len(base)),
            "avg_price_m2": prices,
            "median_price_m2": prices * rng.normal(0.97, 0.01, len(base)),
            "avg_surface": rng.uniform(45, 90, len(base)),
            "price_m2_yoy_variation": np.nan if prev is None else (prices - prev) / np.where(prev == 0, 1, prev),
        })
        prev = prices
        out = real_estate_base / str(year)
        out.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out / f"real_estate_commune_{year}.parquet", index=False)
    print("historique gold: 2019-2023 (synthétique)")

# ── 3. Prédictions IA 2026 ───────────────────────────────────────────────────
from data_pipeline.ml.predict_prices import predict  # noqa: E402
predict(2026)

# ── 4. Annonces + NLP + silver listings ──────────────────────────────────────
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

# Limité à 500 communes pour garder le build rapide
listing_communes = (
    demo.sample(min(500, len(demo)), random_state=42) if len(demo) > 500 else demo
)

rows = []
for _, c in listing_communes.iterrows():
    ratio = float(c.get("score_famille", 70)) / 100
    for i in range(random.randint(3, 8)):
        text = random.choice(POS if random.random() < ratio else NEG)
        price_m2 = float(c["avg_price_m2"]) * random.uniform(1.02, 1.18)
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
