from __future__ import annotations

"""
Ingestion de la "Carte des loyers" — ANIL / Ministère du Logement
Source : data.gouv.fr — loyer médian par commune (annonces réelles 2024)

Colonnes clés :
  INSEE_C     : code commune INSEE
  loypredm2   : loyer médian prédit (€/m²/mois)
  lwr.IPm2    : borne basse intervalle de prédiction
  upr.IPm2    : borne haute
  nbobs_com   : nb annonces dans la commune (0 = extrapolé depuis la maille)
  TYPPRED     : "commune" (données locales) ou "maille" (extrapolé)
"""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from data_pipeline.settings import file_path

# Carte des loyers 2024 — appartements (toutes tailles)
LOYERS_URL_APP = (
    "https://static.data.gouv.fr/resources/"
    "carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-2024/"
    "20241205-153050/pred-app-mef-dhup.csv"
)
# Appartements 1-2 pièces (studios, T1, T2)
LOYERS_URL_APP12 = (
    "https://static.data.gouv.fr/resources/"
    "carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-2024/"
    "20241205-153048/pred-app12-mef-dhup.csv"
)
# Appartements 3 pièces et plus
LOYERS_URL_APP3 = (
    "https://static.data.gouv.fr/resources/"
    "carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-2024/"
    "20241205-145658/pred-app3-mef-dhup.csv"
)


def _download_csv(url: str, label: str) -> pd.DataFrame:
    print(f"  Téléchargement {label}...")
    r = requests.get(url, timeout=120, headers={"User-Agent": "homepedia/1.0"})
    r.raise_for_status()
    from io import StringIO
    df = pd.read_csv(
        StringIO(r.text),
        sep=";",
        decimal=",",
        quotechar='"',
        dtype={"INSEE_C": str},
    )
    # Normalise les noms de colonnes
    df.columns = [c.strip().strip('"') for c in df.columns]
    df["INSEE_C"] = df["INSEE_C"].str.strip().str.zfill(5)
    print(f"    -> {len(df):,} communes")
    return df


def ingest_loyers() -> Path:
    target = file_path("raw", "loyers", "loyers_communes_2024.parquet")

    df_app = _download_csv(LOYERS_URL_APP, "appartements (toutes tailles)")
    df_app12 = _download_csv(LOYERS_URL_APP12, "appartements 1-2 pièces")
    df_app3 = _download_csv(LOYERS_URL_APP3, "appartements 3+ pièces")

    # Renomme avant merge pour distinguer les types
    def _rename(df: pd.DataFrame, suffix: str) -> pd.DataFrame:
        return df.rename(columns={
            "loypredm2": f"loyer_m2_{suffix}",
            "lwr.IPm2":  f"loyer_m2_{suffix}_min",
            "upr.IPm2":  f"loyer_m2_{suffix}_max",
            "nbobs_com": f"nb_annonces_{suffix}",
            "TYPPRED":   f"qualite_{suffix}",
        })[["INSEE_C", f"loyer_m2_{suffix}", f"loyer_m2_{suffix}_min",
            f"loyer_m2_{suffix}_max", f"nb_annonces_{suffix}", f"qualite_{suffix}"]]

    df_all = _rename(df_app, "app")
    df_all = df_all.merge(_rename(df_app12, "app12"), on="INSEE_C", how="left")
    df_all = df_all.merge(_rename(df_app3, "app3"), on="INSEE_C", how="left")

    # Indicateur de marché actif : au moins 1 annonce locale dans la commune
    df_all["marche_locatif_actif"] = (
        df_all["nb_annonces_app"].fillna(0) > 0
    )

    df_all.to_parquet(target, index=False)
    actifs = df_all["marche_locatif_actif"].sum()
    print(f"Loyers sauvegardes : {len(df_all):,} communes ({actifs:,} avec marche actif) -> {target}")
    return target


def main() -> None:
    ingest_loyers()


if __name__ == "__main__":
    main()
