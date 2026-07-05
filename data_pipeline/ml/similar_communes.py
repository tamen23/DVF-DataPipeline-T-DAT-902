from __future__ import annotations

"""
Recommandation "communes similaires" par k-NN sur les vecteurs de scores
territoriaux (gold territory scores) : espaces verts, transport, réseau,
services, éducation, santé, accessibilité, potentiel d'investissement.

Utilisable :
- en librairie (le dashboard Streamlit appelle find_similar sur le
  DataFrame déjà chargé, quelle que soit sa provenance API/parquet) ;
- en CLI sur le gold local :
  python -m data_pipeline.ml.similar_communes --commune 75056 --top 5
"""

import argparse

import pandas as pd

from data_pipeline.settings import DATA_LAKE_PATH

SCORE_COLUMNS = [
    "affordability_score", "transport_score", "network_score", "green_score",
    "services_score", "education_score", "health_score",
    "investment_potential_score", "income_score",
]


def find_similar(frame: pd.DataFrame, code_commune: str, top: int = 5) -> pd.DataFrame:
    """Return the `top` most similar communes to `code_commune`.

    Similarity = proximity in the standardized score space (k-NN).
    Returns a DataFrame with nom_commune, code_commune, similarity (0-100)
    and the score columns used; empty DataFrame if the commune is unknown
    or fewer than 2 usable score columns exist.
    """
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler

    columns = [c for c in SCORE_COLUMNS if c in frame.columns]
    if len(columns) < 2:
        return pd.DataFrame()

    candidates = frame.dropna(subset=columns, how="all").copy()
    candidates[columns] = candidates[columns].fillna(candidates[columns].median())
    candidates = candidates.drop_duplicates(subset=["code_commune"]).reset_index(drop=True)

    target = candidates.index[candidates["code_commune"].astype(str) == str(code_commune)]
    if target.empty or len(candidates) < 2:
        return pd.DataFrame()

    features = StandardScaler().fit_transform(candidates[columns])
    k = min(top + 1, len(candidates))
    knn = NearestNeighbors(n_neighbors=k).fit(features)
    distances, indices = knn.kneighbors(features[target[0]].reshape(1, -1))

    result = candidates.iloc[indices[0]].copy()
    max_distance = distances[0].max() or 1.0
    result["similarity"] = ((1 - distances[0] / max_distance) * 100).round(0)
    result = result[result["code_commune"].astype(str) != str(code_commune)]
    keep = ["nom_commune", "code_commune", "similarity", "avg_price_m2"] + columns
    return result[[c for c in keep if c in result.columns]].head(top)


def main() -> None:
    parser = argparse.ArgumentParser(description="Communes similaires par k-NN sur les scores territoriaux.")
    parser.add_argument("--commune", required=True, help="Code INSEE (ex: 75056)")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    path = DATA_LAKE_PATH / "gold" / "territories" / "territory_scores.parquet"
    if not path.exists():
        raise SystemExit(f"{path} introuvable — lancez build_territory_gold (ou le générateur démo).")

    frame = pd.read_parquet(path)
    similar = find_similar(frame, args.commune, args.top)
    if similar.empty:
        raise SystemExit(f"Commune {args.commune} introuvable dans les scores territoriaux.")

    origin = frame[frame["code_commune"].astype(str) == str(args.commune)].iloc[0]
    print(f"Communes similaires à {origin['nom_commune']} ({args.commune}) :\n")
    for _, row in similar.iterrows():
        print(f"  {row['nom_commune']:<25} similarité {row['similarity']:.0f}/100")


if __name__ == "__main__":
    main()
