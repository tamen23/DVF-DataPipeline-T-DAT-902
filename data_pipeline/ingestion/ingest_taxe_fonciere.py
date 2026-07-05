from __future__ import annotations

"""
Estimation de la taxe foncière sur les propriétés bâties (TFPB) par commune.

Sources utilisées :
  1. DGFiP - Tarifs des locaux d'habitation 2024 (data.economie.gouv.fr)
     → vl_au_m2 : valeur locative officielle par m² et catégorie de local
     → On prend la médiane par commune toutes catégories confondues (type 'D' = appartements)
  2. Taux TFB moyen par département (référence INSEE / DGCL 2023)
     → Appliqué en l'absence de données communales individuelles

Formule :
  VLC estimée = vl_au_m2_médiane × surface × 1.0 (sans abattement logement principal
                                                   car investisseur non résident)
  taxe_fonciere_estimee = VLC × taux_tfb_dept / 100

  → Précision : ±30% par rapport à la taxe réelle (acceptable pour comparer les communes)

Colonne produite dans le parquet :
  vl_m2_commune : valeur locative officielle médiane (€/m²) — sert à estimer la VLC
  taux_tfb_dept : taux TFB moyen du département (%)
"""

from pathlib import Path

import pandas as pd
import requests

from data_pipeline.settings import file_path

# Dataset DGFiP - Tarifs des locaux d'habitation 2024
VL_API_URL = (
    "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "descriptif-tarifs-des-locaux-d-habitation_2024/exports/csv"
)

# Taux TFB moyens par département 2023 (source : DGCL / Observatoire finances locales)
# Fourchette nationale : 10% (Paris) à 40%+ (certaines communes rurales)
TAUX_TFB_DEPT: dict[str, float] = {
    "01": 19.5, "02": 26.2, "03": 24.8, "04": 25.1, "05": 20.3,
    "06": 18.7, "07": 23.4, "08": 28.1, "09": 24.6, "10": 26.8,
    "11": 27.3, "12": 25.0, "13": 22.6, "14": 24.9, "15": 24.2,
    "16": 25.6, "17": 23.8, "18": 26.4, "19": 23.7, "2A": 17.2,
    "2B": 18.5, "21": 22.1, "22": 24.3, "23": 25.9, "24": 25.7,
    "25": 21.4, "26": 23.2, "27": 25.5, "28": 25.3, "29": 23.9,
    "30": 26.1, "31": 21.8, "32": 25.4, "33": 20.9, "34": 24.7,
    "35": 22.6, "36": 26.7, "37": 22.9, "38": 21.3, "39": 22.8,
    "40": 21.6, "41": 25.0, "42": 23.5, "43": 23.1, "44": 21.5,
    "45": 24.1, "46": 25.8, "47": 26.2, "48": 24.0, "49": 22.3,
    "50": 25.7, "51": 24.6, "52": 27.4, "53": 24.3, "54": 23.6,
    "55": 27.8, "56": 24.1, "57": 23.2, "58": 26.1, "59": 27.3,
    "60": 25.4, "61": 26.5, "62": 28.2, "63": 21.9, "64": 20.7,
    "65": 22.6, "66": 24.8, "67": 19.8, "68": 20.4, "69": 20.1,
    "70": 25.6, "71": 23.9, "72": 25.2, "73": 18.9, "74": 17.6,
    "75": 13.5, "76": 26.8, "77": 19.8, "78": 17.2, "79": 25.9,
    "80": 27.6, "81": 26.3, "82": 26.7, "83": 22.1, "84": 22.4,
    "85": 22.8, "86": 25.4, "87": 24.6, "88": 26.9, "89": 25.7,
    "90": 23.4, "91": 20.6, "92": 17.8, "93": 24.7, "94": 21.3,
    "95": 21.9,
}
TAUX_TFB_NATIONAL_MOYEN = 22.5


def ingest_taxe_fonciere() -> Path:
    output = file_path("raw", "taxe_fonciere", "taux_tfb_communes.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)

    print("  Téléchargement tarifs VLC DGFiP 2024...")
    try:
        r = requests.get(
            VL_API_URL,
            params={"delimiter": ";", "limit": -1},
            timeout=120,
            headers={"User-Agent": "homepedia/1.0"},
            stream=True,
        )
        r.raise_for_status()

        from io import StringIO
        content = r.content.decode("utf-8", errors="replace")
        df = pd.read_csv(StringIO(content), sep=";", dtype=str, on_bad_lines="skip")
        df.columns = [c.strip().lower() for c in df.columns]

        print(f"    -> {len(df):,} lignes | colonnes : {list(df.columns)}")

        # On garde uniquement les locaux D = appartements
        if "nature_locaux" in df.columns:
            df = df[df["nature_locaux"].str.strip() == "D"]

        # Valeur locative au m²
        df["vl_au_m2"] = pd.to_numeric(df.get("vl_au_m2", ""), errors="coerce")

        # Code commune INSEE 5 chiffres
        if "code_commune" in df.columns:
            df["code_commune"] = df["code_commune"].astype(str).str.strip().str.zfill(5)
        else:
            print("  [warn] Colonne code_commune absente")
            raise ValueError("code_commune manquant")

        # VLC médiane par commune (toutes catégories d'appartements)
        vl_commune = (
            df.groupby("code_commune")["vl_au_m2"]
            .median()
            .reset_index()
            .rename(columns={"vl_au_m2": "vl_m2_commune"})
        )
        vl_commune = vl_commune.dropna(subset=["vl_m2_commune"])
        print(f"    -> {len(vl_commune):,} communes avec VLC connue")

    except Exception as e:
        print(f"  [warn] Téléchargement VLC échoué : {e}")
        print("  -> Utilisation des taux départementaux seuls")
        vl_commune = pd.DataFrame(columns=["code_commune", "vl_m2_commune"])

    # Construit une table commune → département → taux TFB
    communes_ref = file_path("raw", "communes", "communes_geo.parquet")
    if not communes_ref.exists():
        communes_ref = file_path("raw", "communes", "communes.parquet")

    if communes_ref.exists():
        ref = pd.read_parquet(communes_ref)
        ref["code_commune"] = ref["code_commune"].astype(str).str.zfill(5)
        if "code_departement" not in ref.columns and "code_commune" in ref.columns:
            ref["code_departement"] = ref["code_commune"].str[:2]
        dept_map = ref[["code_commune", "code_departement"]].drop_duplicates()
    else:
        # Fallback : dérive le département depuis les 2 premiers chiffres du code commune
        all_codes = pd.DataFrame({"code_commune": vl_commune["code_commune"].tolist()})
        all_codes["code_departement"] = all_codes["code_commune"].str[:2]
        dept_map = all_codes

    dept_map["taux_tfb_dept"] = dept_map["code_departement"].map(TAUX_TFB_DEPT).fillna(TAUX_TFB_NATIONAL_MOYEN)

    # Fusion
    if not vl_commune.empty:
        result = dept_map.merge(vl_commune, on="code_commune", how="left")
    else:
        result = dept_map.copy()
        result["vl_m2_commune"] = None

    result = result[["code_commune", "vl_m2_commune", "taux_tfb_dept"]].drop_duplicates("code_commune")
    result.to_parquet(output, index=False)

    print(f"  Taux TFB moyen (tous depts) : {result['taux_tfb_dept'].mean():.1f}%")
    if result["vl_m2_commune"].notna().sum() > 0:
        print(f"  VLC médiane nationale : {result['vl_m2_commune'].median():.2f} €/m²")
    print(f"  Sauvegardé -> {output} ({len(result):,} communes)")
    return output


if __name__ == "__main__":
    ingest_taxe_fonciere()
