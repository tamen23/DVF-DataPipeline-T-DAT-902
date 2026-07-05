from __future__ import annotations

"""
Prédiction de prix immobilier par commune (RandomForest, scikit-learn).

Entraînement sur l'historique gold DVF (une ligne par commune et par an) :
chaque transition année t -> t+1 devient un exemple d'apprentissage
(features de l'année t, cible = prix moyen au m² de l'année t+1).
La dernière transition disponible sert de jeu de validation (MAE affichée),
puis le modèle est réentraîné sur tout l'historique pour prédire
l'année cible.

Produit : gold/ml/price_predictions_{target_year}.parquet
Colonnes : code_commune, nom_commune, target_year,
           predicted_avg_price_m2, last_avg_price_m2, predicted_growth_pct

Usage:
  python -m data_pipeline.ml.predict_prices --target-year 2026
"""

import argparse
import re

import numpy as np
import pandas as pd

from data_pipeline.settings import DATA_LAKE_PATH, file_path

FEATURES = [
    "avg_price_m2", "median_price_m2", "avg_price",
    "avg_surface", "transaction_count", "price_m2_yoy_variation",
]


def load_history() -> pd.DataFrame:
    frames = []
    for path in sorted((DATA_LAKE_PATH / "gold" / "real_estate").glob("*/real_estate_commune_*.parquet")):
        match = re.search(r"real_estate_commune_(\d{4})\.parquet$", path.name)
        if not match:
            continue
        frame = pd.read_parquet(path)
        if frame.empty:
            continue
        frame["data_year"] = int(match.group(1))
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_training_pairs(history: pd.DataFrame) -> pd.DataFrame:
    """One row per commune transition (year t features -> year t+1 price)."""
    nxt = history[["code_commune", "data_year", "avg_price_m2"]].copy()
    nxt["data_year"] -= 1  # align: target of year t is the price observed at t+1
    nxt = nxt.rename(columns={"avg_price_m2": "target_price_m2"})
    return history.merge(nxt, on=["code_commune", "data_year"], how="inner")


def predict(target_year: int) -> None:
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import mean_absolute_error
    except ImportError:
        raise SystemExit("scikit-learn manquant : pip install scikit-learn")

    history = load_history()
    years = sorted(history["data_year"].unique()) if not history.empty else []
    if len(years) < 2:
        print(f"[skip] Prédiction impossible : {len(years)} année(s) d'historique gold "
              f"(il en faut au moins 2). Lancez la pipeline sur plusieurs années.")
        return

    pairs = build_training_pairs(history)
    pairs = pairs.dropna(subset=["avg_price_m2", "target_price_m2"])
    if pairs.empty:
        print("[skip] Aucune transition année->année exploitable dans l'historique.")
        return

    X = pairs[FEATURES].fillna(0.0)
    y = pairs["target_price_m2"]

    # Validation temporelle : la transition la plus récente sert de test.
    last_train_year = pairs["data_year"].max()
    train_mask = pairs["data_year"] < last_train_year
    model = RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1)
    if train_mask.any() and (~train_mask).any():
        model.fit(X[train_mask], y[train_mask])
        holdout_pred = model.predict(X[~train_mask])
        mae = mean_absolute_error(y[~train_mask], holdout_pred)
        print(f"Validation (transition {last_train_year}->{last_train_year + 1}) : "
              f"MAE = {mae:,.0f} EUR/m² sur {int((~train_mask).sum()):,} communes")

    # Réentraînement sur tout l'historique, prédiction depuis la dernière année.
    model.fit(X, y)
    base_year = max(years)
    base = history[history["data_year"] == base_year].dropna(subset=["avg_price_m2"]).copy()
    horizon = target_year - base_year
    if horizon < 1:
        raise SystemExit(f"--target-year doit être > {base_year} (dernière année gold)")

    # Prédiction itérative année par année jusqu'à l'année cible.
    current = base[FEATURES].fillna(0.0).copy()
    for _ in range(horizon):
        predicted = model.predict(current)
        current["price_m2_yoy_variation"] = (predicted - current["avg_price_m2"]) / current["avg_price_m2"]
        current["median_price_m2"] *= predicted / current["avg_price_m2"]
        current["avg_price"] *= predicted / current["avg_price_m2"]
        current["avg_price_m2"] = predicted

    result = pd.DataFrame({
        "code_commune": base["code_commune"].values,
        "nom_commune": base["nom_commune"].values,
        "target_year": target_year,
        "predicted_avg_price_m2": current["avg_price_m2"].round(0).values,
        "last_avg_price_m2": base["avg_price_m2"].round(0).values,
    })
    result["predicted_growth_pct"] = (
        (result["predicted_avg_price_m2"] - result["last_avg_price_m2"])
        / result["last_avg_price_m2"] * 100
    ).round(1)

    output = file_path("gold", "ml", f"price_predictions_{target_year}.parquet")
    result.to_parquet(output, index=False)
    print(f"Prédictions {target_year} écrites dans {output} ({len(result):,} communes, "
          f"base {base_year}, horizon {horizon} an(s))")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prédiction du prix au m² par commune (RandomForest).")
    parser.add_argument("--target-year", required=True, type=int)
    args = parser.parse_args()
    predict(args.target_year)


if __name__ == "__main__":
    main()
