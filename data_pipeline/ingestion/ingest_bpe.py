from __future__ import annotations

"""
Ingestion de la Base Permanente des Équipements (BPE) 2024 — INSEE.
Source : https://www.insee.fr/fr/statistiques/8217525
Fichier : BPE24.zip (~157 Mo) contenant bpe24_ensemble_xy.csv

Colonnes utilisées :
  CODGEO  : code commune INSEE (5 car.)
  TYPEQU  : code type d'équipement
  NB      : nombre d'équipements (optionnel — on compte les lignes)

Mapping TYPEQU → catégorie radar :
  education  : A1xx (écoles), A2xx (collèges/lycées), A5xx (universités)
  health     : D1xx (médecins/pharmacies), D2xx (hôpitaux/cliniques)
  services   : B1xx (commerces alimentaires), C1xx (restaurants/cafés)
  green      : F1xx (équipements sportifs plein air), F3xx (parcs/jardins)
  transport  : C501 (gares), C502 (aéroports), C503 (métro/tram)

Produit : raw/bpe/bpe_scores_communes.parquet
Colonnes : code_commune, school_count, university_count, hospital_count,
           pharmacy_count, supermarket_count, restaurant_count,
           park_count, transport_count
"""

import zipfile
import io
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from data_pipeline.settings import file_path

BPE_ZIP_URL = "https://www.insee.fr/fr/statistiques/fichier/8217525/BPE24.zip"
CHUNK_SIZE = 4 * 1024 * 1024

# Mapping préfixes TYPEQU → catégorie
CATEGORY_MAP: dict[str, str] = {}

# Éducation
for prefix in ["A101","A104","A105","A106","A107",   # écoles maternelle/primaire
               "A201","A202","A203","A204","A205","A206","A207","A208",  # collèges/lycées
               "A301","A302","A303","A304","A305"]:   # enseignement supérieur
    CATEGORY_MAP[prefix] = "school_count"
for prefix in ["A401","A402","A403","A404","A405","A406","A407","A408","A501","A502","A503","A504"]:
    CATEGORY_MAP[prefix] = "university_count"

# Santé
for prefix in ["D101","D102","D103","D104","D105","D106","D107","D108","D109",
               "D110","D111","D112","D113","D114","D115","D116","D117","D118","D119",
               "D120","D121","D122","D123","D124","D125","D126","D127","D128","D129",
               "D130","D131","D201","D202","D203","D204","D205","D206","D207","D208",
               "D209","D210","D211","D212","D213","D214","D215","D231","D232","D233"]:
    CATEGORY_MAP[prefix] = "hospital_count"
for prefix in ["D301","D302","D303","D304","D305","D306","D307","D308","D309","D310"]:
    CATEGORY_MAP[prefix] = "pharmacy_count"

# Commerces / services
for prefix in ["B101","B102","B103","B201","B202","B203","B204","B205","B206",
               "B301","B302","B303","B304","B305","B306","B307","B308","B309","B310",
               "B311","B312","B313","B401","B402","B403","B404","B405","B406"]:
    CATEGORY_MAP[prefix] = "supermarket_count"
for prefix in ["C101","C102","C103","C104","C105","C106","C201","C202","C203",
               "C204","C205","C301","C302","C303","C304","C305","C306"]:
    CATEGORY_MAP[prefix] = "restaurant_count"

# Espaces verts / sport
for prefix in ["F101","F102","F103","F104","F105","F106","F107","F108","F109","F110",
               "F111","F112","F113","F114","F115","F116","F117","F118","F119","F120",
               "F201","F202","F203","F204","F205","F206","F207","F208","F209","F210",
               "F301","F302","F303","F304","F305","F306","F307","F308","F309","F310",
               "F311","F312","F313","F314","F315","F316","F317","F318","F319","F320"]:
    CATEGORY_MAP[prefix] = "park_count"

# Transport
for prefix in ["C501","C502","C503","C504","C505"]:
    CATEGORY_MAP[prefix] = "transport_count"


def _download_bpe(zip_target: Path) -> None:
    print(f"  Téléchargement BPE 2024 depuis INSEE ({BPE_ZIP_URL})...")
    with requests.get(BPE_ZIP_URL, stream=True, timeout=300,
                      headers={"User-Agent": "homepedia/1.0"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(zip_target, "wb") as fh:
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                fh.write(chunk)
                downloaded += len(chunk)
                if total:
                    print(f"\r  {downloaded / 1e6:.0f} Mo / {total / 1e6:.0f} Mo", end="", flush=True)
    print()


def ingest_bpe() -> Path:
    output = file_path("raw", "bpe", "bpe_scores_communes.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)

    zip_target = file_path("raw", "bpe", "BPE24.zip")

    if not zip_target.exists():
        _download_bpe(zip_target)
    else:
        print(f"  ZIP déjà téléchargé : {zip_target}")

    print("  Extraction et parsing...")
    with zipfile.ZipFile(zip_target) as zf:
        # Find the main CSV inside the zip
        csv_names = [n for n in zf.namelist() if n.endswith(".csv") and "ensemble" in n.lower()]
        if not csv_names:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not csv_names:
            raise ValueError(f"Aucun CSV trouvé dans {zip_target}. Contenu : {zf.namelist()}")

        csv_name = csv_names[0]
        print(f"  Lecture de {csv_name}...")
        with zf.open(csv_name) as f:
            df = pd.read_csv(f, sep=";", dtype=str, on_bad_lines="skip")

    df.columns = [c.strip().upper() for c in df.columns]
    print(f"  {len(df):,} lignes | colonnes : {list(df.columns)}")

    # Identify commune code column
    code_col = next((c for c in df.columns if c in ("CODGEO", "DEPCOM", "CODE_COMMUNE", "INSEE_COM", "COM")), None)
    if code_col is None:
        raise ValueError(f"Colonne code commune introuvable. Colonnes disponibles : {list(df.columns)}")
    df["code_commune"] = df[code_col].astype(str).str.strip().str.zfill(5)
    df["TYPEQU"] = df["TYPEQU"].astype(str).str.strip().str.upper()

    # Map TYPEQU → category
    df["category"] = df["TYPEQU"].map(CATEGORY_MAP)
    df = df.dropna(subset=["category"])
    print(f"  {len(df):,} lignes après filtrage sur les catégories pertinentes")

    # Count per commune per category
    counts = (
        df.groupby(["code_commune", "category"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    # Ensure all expected columns are present
    expected_cols = ["school_count","university_count","hospital_count","pharmacy_count",
                     "supermarket_count","restaurant_count","park_count","transport_count"]
    for col in expected_cols:
        if col not in counts.columns:
            counts[col] = 0

    counts = counts[["code_commune"] + expected_cols]
    counts.to_parquet(output, index=False)

    print(f"\n  BPE scores : {len(counts):,} communes -> {output}")
    print(f"  Exemple :\n{counts.head(3).to_string(index=False)}")

    output.with_suffix(".metadata.txt").write_text(
        "\n".join([
            "source=https://www.insee.fr/fr/statistiques/8217525",
            f"communes={len(counts)}",
            f"imported_at={datetime.now(timezone.utc).isoformat()}",
        ]),
        encoding="utf-8",
    )
    return output


if __name__ == "__main__":
    ingest_bpe()
