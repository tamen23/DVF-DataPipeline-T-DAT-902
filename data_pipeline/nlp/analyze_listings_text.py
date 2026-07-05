from __future__ import annotations

"""
Analyse textuelle des annonces immobilières (exigence du sujet : textual analysis).

Sources de texte, par commune :
  - titres + descriptions des annonces collectées par le pipeline Kafka
    (bronze/listings/{source}/{date}/batch_*.parquet)
  - avis optionnels déposés dans raw/avis/*.parquet (colonnes: code_commune, text)

Produit gold/nlp/text_analysis.parquet avec, par commune :
  - n_texts               : nombre de textes analysés
  - sentiment_score       : score lexical FR entre -1 (négatif) et +1 (positif)
  - sentiment_label       : positif / neutre / négatif
  - top_words             : fréquences des mots (JSON) → nuage de mots du dashboard

L'approche est volontairement lexicale (listes de mots FR) : transparente,
sans dépendance lourde, et explicable en soutenance.

Usage:
  python -m data_pipeline.nlp.analyze_listings_text
"""

import json
import re
import unicodedata
from collections import Counter

import pandas as pd

from data_pipeline.settings import DATA_LAKE_PATH, file_path

# Mots vides FR + vocabulaire d'annonce sans valeur informative
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "d", "l", "et", "ou", "a", "au",
    "aux", "en", "dans", "sur", "sous", "avec", "sans", "pour", "par", "ce", "cet",
    "cette", "ces", "son", "sa", "ses", "leur", "leurs", "vous", "nous", "il", "elle",
    "est", "sont", "etre", "avoir", "tout", "tous", "toute", "toutes", "tres", "plus",
    "moins", "bien", "comme", "mais", "donc", "or", "ni", "car", "que", "qui", "quoi",
    "dont", "si", "ne", "pas", "se", "sa", "on", "y", "m2", "m", "euros", "euro", "eur",
    "appartement", "maison", "piece", "pieces", "chambre", "chambres", "vente", "louer",
    "location", "vendre", "achat", "situe", "situee", "compose", "composee", "comprenant",
    "dispose", "etage", "rez", "chaussee", "salle", "bain", "cuisine", "sejour", "wc",
}

# Lexique de sentiment FR orienté immobilier / cadre de vie
POSITIVE_WORDS = {
    "lumineux", "lumineuse", "spacieux", "spacieuse", "calme", "charmant", "charmante",
    "renove", "renovee", "neuf", "neuve", "moderne", "ideal", "ideale", "excellent",
    "excellente", "magnifique", "superbe", "beau", "belle", "agreable", "ensoleille",
    "ensoleillee", "securise", "securisee", "proche", "commodites", "recherche",
    "recherchee", "rare", "exceptionnel", "exceptionnelle", "verdure", "jardin",
    "terrasse", "balcon", "parking", "vue", "dynamique", "convivial", "conviviale",
    "propre", "paisible", "pratique", "commerces", "ecoles", "transports",
}
NEGATIVE_WORDS = {
    "bruyant", "bruyante", "bruit", "vetuste", "travaux", "sombre", "humide",
    "humidite", "petit", "petite", "exigu", "exigue", "degrade", "degradee",
    "insalubre", "sale", "dangereux", "dangereuse", "insecurite", "vis", "nuisances",
    "pollution", "enclave", "enclavee", "isole", "isolee", "delabre", "delabree",
    "probleme", "problemes", "defaut", "defauts", "mauvais", "mauvaise", "cher",
    "chere", "eloigne", "eloignee",
}


def _normalize(text: str) -> list[str]:
    """Lowercase, strip accents, keep alphabetic tokens of 3+ chars."""
    text = unicodedata.normalize("NFKD", str(text).lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return [t for t in re.findall(r"[a-z]{3,}", text) if t not in STOPWORDS]


def analyze_texts(texts: list[str], top: int = 40) -> dict:
    """Word frequencies + lexicon sentiment for a list of raw texts."""
    tokens: list[str] = []
    for text in texts:
        if text and str(text) != "nan":
            tokens.extend(_normalize(text))

    positive = sum(1 for t in tokens if t in POSITIVE_WORDS)
    negative = sum(1 for t in tokens if t in NEGATIVE_WORDS)
    total_polar = positive + negative
    sentiment = (positive - negative) / total_polar if total_polar else 0.0

    return {
        "n_tokens": len(tokens),
        "sentiment_score": round(sentiment, 3),
        "sentiment_label": "positif" if sentiment > 0.15 else ("négatif" if sentiment < -0.15 else "neutre"),
        "word_freq": dict(Counter(tokens).most_common(top)),
    }


def _load_texts_per_commune() -> dict[str, list[str]]:
    texts: dict[str, list[str]] = {}

    # 1. Annonces du pipeline Kafka
    for path in sorted((DATA_LAKE_PATH / "bronze" / "listings").glob("*/*/batch_*.parquet")):
        frame = pd.read_parquet(path)
        text_cols = [c for c in ("title", "description", "city") if c in frame.columns]
        code_col = "commune_code" if "commune_code" in frame.columns else None
        if not text_cols or code_col is None:
            continue
        for _, row in frame.iterrows():
            code = str(row[code_col])
            blob = " ".join(str(row[c]) for c in text_cols if pd.notna(row.get(c)))
            texts.setdefault(code, []).append(blob)

    # 2. Avis optionnels (raw/avis/*.parquet : code_commune, text)
    avis_dir = DATA_LAKE_PATH / "raw" / "avis"
    if avis_dir.exists():
        for path in sorted(avis_dir.glob("*.parquet")):
            frame = pd.read_parquet(path)
            if {"code_commune", "text"}.issubset(frame.columns):
                for _, row in frame.iterrows():
                    texts.setdefault(str(row["code_commune"]), []).append(str(row["text"]))

    return texts


def build_text_analysis() -> None:
    texts = _load_texts_per_commune()
    if not texts:
        print("Aucun texte trouvé (bronze/listings vide et pas d'avis) — lancez le pipeline Kafka d'abord.")
        return

    rows = []
    for code_commune, commune_texts in texts.items():
        result = analyze_texts(commune_texts)
        rows.append({
            "code_commune": code_commune,
            "n_texts": len(commune_texts),
            "n_tokens": result["n_tokens"],
            "sentiment_score": result["sentiment_score"],
            "sentiment_label": result["sentiment_label"],
            "top_words": json.dumps(result["word_freq"], ensure_ascii=False),
        })

    output = file_path("gold", "nlp", "text_analysis.parquet")
    pd.DataFrame(rows).to_parquet(output, index=False)
    print(f"Analyse textuelle écrite dans {output} ({len(rows):,} communes, "
          f"{sum(len(t) for t in texts.values()):,} textes)")


if __name__ == "__main__":
    build_text_analysis()
