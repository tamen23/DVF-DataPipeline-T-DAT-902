from __future__ import annotations

"""
Builds the gold territory layer by combining:
  - Real estate gold (DVF aggregated by commune)
  - Commune reference data (coordinates, region, department)
  - ARCEP mobile network coverage (4G/5G scores)
  - OSM POI counts (green spaces, services, education, health)
  - GTFS transit stops (transport score)
  - INSEE Filosofi income data (if available)

Output: data_lake/gold/territories/territory_scores.parquet
This file is what the Streamlit app reads.
"""

import argparse
from pathlib import Path

import pandas as pd

from data_pipeline.settings import file_path


# -------------------------------------------------------------------
# Normalisation helpers
# -------------------------------------------------------------------

def _normalize_0_100(series: pd.Series, inverse: bool = False) -> pd.Series:
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series([50.0] * len(series), index=series.index)
    normalized = (series - lo) / (hi - lo) * 100
    return (100 - normalized if inverse else normalized).round(2)


# -------------------------------------------------------------------
# Loaders
# -------------------------------------------------------------------

def _load_real_estate(year: int) -> pd.DataFrame:
    path = file_path("gold", "real_estate", str(year), f"real_estate_commune_{year}.parquet")
    if not path.exists():
        raise FileNotFoundError(
            f"Gold real estate file not found: {path}\n"
            f"Run the full DVF pipeline first:\n"
            f"  python -m data_pipeline.ingestion.ingest_dvf --year {year}\n"
            f"  python -m data_pipeline.transformation.bronze_dvf --year {year}\n"
            f"  python -m data_pipeline.cleaning.silver_dvf --year {year}\n"
            f"  python -m data_pipeline.transformation.gold_real_estate --year {year}"
        )
    return pd.read_parquet(path)


def _load_communes() -> pd.DataFrame:
    path = file_path("raw", "communes", "communes.parquet")
    if not path.exists():
        raise FileNotFoundError(
            f"Communes reference not found: {path}\n"
            "Run: python -m data_pipeline.ingestion.ingest_communes"
        )
    regions = _load_regions()
    communes = pd.read_parquet(path)
    communes = communes.merge(regions, on="code_region", how="left")
    return communes


def _load_regions() -> pd.DataFrame:
    path = file_path("raw", "communes", "regions.parquet")
    if not path.exists():
        return pd.DataFrame(columns=["code_region", "nom_region"])
    return pd.read_parquet(path)


def _load_arcep() -> pd.DataFrame | None:
    path = file_path("raw", "arcep", "couverture_mobile.csv")
    if not path.exists():
        print("  [warn] ARCEP data not found — network_score will be null. Run ingest_arcep.py to add it.")
        return None

    df = pd.read_csv(path, sep=";", dtype=str, on_bad_lines="skip")
    df.columns = [c.lower().strip() for c in df.columns]

    # ARCEP file has one row per operator per commune
    # Columns vary by year but typically include: codecommune, operateur, statut_4g, statut_5g
    code_col = next((c for c in df.columns if c in ("insee_com", "codecommune", "code_commune")), None)
    if code_col is None:
        code_col = next((c for c in df.columns if "com" in c and "insee" in c), None)
    g4_col = next((c for c in df.columns if "4g" in c), None)
    g5_col = next((c for c in df.columns if "5g" in c and "historique" not in c and "date" not in c and "m_hz" not in c), None)

    if code_col is None:
        print("  [warn] Could not identify commune code column in ARCEP file — skipping network score.")
        return None

    sub = df[[code_col]].copy()
    sub = sub.rename(columns={code_col: "code_commune"})
    sub["code_commune"] = sub["code_commune"].astype(str).str.zfill(5)

    if g4_col:
        sub["_4g"] = pd.to_numeric(df[g4_col].str.replace(",", "."), errors="coerce")
    if g5_col:
        sub["_5g"] = pd.to_numeric(df[g5_col].str.replace(",", "."), errors="coerce")

    agg: dict = {}
    if "_4g" in sub.columns:
        agg["_4g"] = "mean"
    if "_5g" in sub.columns:
        agg["_5g"] = "mean"

    if not agg:
        print("  [warn] No 4G/5G columns found in ARCEP file — skipping network score.")
        return None

    grouped = sub.groupby("code_commune").agg(agg).reset_index()
    cols = [c for c in ["_4g", "_5g"] if c in grouped.columns]
    grouped["network_score_raw"] = grouped[cols].mean(axis=1)
    return grouped[["code_commune", "network_score_raw"]]


def _load_osm() -> pd.DataFrame | None:
    path = file_path("raw", "osm", "osm_poi_counts.parquet")
    if not path.exists():
        print("  [warn] OSM data not found — green/education/health/services scores will be neutral.")
        print("         Run: python -m data_pipeline.ingestion.ingest_osm")
        return None
    df = pd.read_parquet(path)
    if df.empty or "code_commune" not in df.columns:
        print("  [warn] OSM data is empty — green/education/health/services scores will be neutral.")
        return None
    return df


def _load_gtfs() -> pd.DataFrame | None:
    path = file_path("raw", "gtfs", "stops_per_commune.parquet")
    if not path.exists():
        print("  [warn] GTFS data not found — transport_score will be neutral.")
        print("         Run: python -m data_pipeline.ingestion.ingest_gtfs")
        return None
    return pd.read_parquet(path)


def _load_loyers() -> pd.DataFrame | None:
    path = file_path("raw", "loyers", "loyers_communes_2024.parquet")
    if not path.exists():
        print("  [warn] Loyers data not found — loyer_reel_m2 will be null. Run ingest_loyers.py to add it.")
        return None
    df = pd.read_parquet(path)
    df = df.rename(columns={"INSEE_C": "code_commune"})
    df["code_commune"] = df["code_commune"].astype(str).str.zfill(5)
    return df[[
        "code_commune",
        "loyer_m2_app", "loyer_m2_app_min", "loyer_m2_app_max",
        "loyer_m2_app12", "loyer_m2_app3",
        "nb_annonces_app", "qualite_app",
        "marche_locatif_actif",
    ]]


def _load_taxe_fonciere() -> pd.DataFrame | None:
    path = file_path("raw", "taxe_fonciere", "taux_tfb_communes.parquet")
    if not path.exists():
        print("  [warn] Taxe foncière non disponible — run ingest_taxe_fonciere.py")
        return None
    df = pd.read_parquet(path)
    df["code_commune"] = df["code_commune"].astype(str).str.zfill(5)
    cols = ["code_commune", "taux_tfb_dept"]
    if "vl_m2_commune" in df.columns:
        cols.append("vl_m2_commune")
    return df[[c for c in cols if c in df.columns]]


def _load_filosofi() -> pd.DataFrame | None:
    import zipfile
    import io

    path = file_path("raw", "insee", "filosofi")
    zips = list(path.glob("**/*.zip")) if path.exists() else []
    if not zips:
        print("  [warn] INSEE Filosofi data not found — income score will be null. Run ingest_insee.py to add it.")
        return None

    # Try to open the most recent zip
    zips.sort()
    zf_path = zips[-1]
    try:
        with zipfile.ZipFile(zf_path) as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv") and "COMMUNES" in n.upper()]
            if not csv_names:
                csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            if not csv_names:
                return None
            with zf.open(csv_names[0]) as f:
                df = pd.read_csv(f, sep=";", dtype=str, on_bad_lines="skip")
    except Exception as e:
        print(f"  [warn] Could not read Filosofi zip: {e}")
        return None

    df.columns = [c.lower().strip() for c in df.columns]
    code_col = next((c for c in df.columns if c in ("codgeo", "code_commune", "com")), None)
    income_col = next((c for c in df.columns if "q2" in c or "med" in c or "revenu" in c.lower()), None)

    if code_col is None or income_col is None:
        return None

    out = df[[code_col, income_col]].copy()
    out.columns = ["code_commune", "median_income_raw"]
    out["code_commune"] = out["code_commune"].astype(str).str.zfill(5)
    out["median_income_raw"] = pd.to_numeric(out["median_income_raw"].str.replace(",", "."), errors="coerce")
    return out.dropna(subset=["median_income_raw"])


# -------------------------------------------------------------------
# Persona scoring
# -------------------------------------------------------------------

PERSONA_WEIGHTS = {
    "Etudiant": {
        "affordability_score": 0.30,
        "transport_score": 0.25,
        "education_score": 0.25,
        "services_score": 0.10,
        "network_score": 0.10,
    },
    "Jeune actif": {
        "affordability_score": 0.25,
        "transport_score": 0.20,
        "network_score": 0.20,
        "services_score": 0.20,
        "green_score": 0.15,
    },
    "Famille": {
        "affordability_score": 0.25,
        "green_score": 0.20,
        "services_score": 0.20,
        "education_score": 0.20,
        "transport_score": 0.15,
    },
    "Personne agee": {
        "health_score": 0.30,
        "services_score": 0.25,
        "transport_score": 0.15,
        "affordability_score": 0.20,
        "green_score": 0.10,
    },
    "Investisseur": {
        "investment_potential_score": 0.40,
        "affordability_score": 0.20,
        "transport_score": 0.20,
        "network_score": 0.20,
    },
}


def _compute_persona_scores(frame: pd.DataFrame) -> pd.DataFrame:
    for persona, weights in PERSONA_WEIGHTS.items():
        score = pd.Series(0.0, index=frame.index)
        total_weight = 0.0
        for col, weight in weights.items():
            if col in frame.columns:
                score += frame[col].fillna(50) * weight
                total_weight += weight
        if total_weight > 0:
            score = score / total_weight
        col_name = f"score_{persona.lower().replace(' ', '_')}"
        frame[col_name] = score.round(2)
    return frame


# -------------------------------------------------------------------
# Main builder
# -------------------------------------------------------------------

def build_territory_gold(year: int) -> Path:
    print(f"\nBuilding territory gold layer for {year}...\n")

    # 1. Real estate (required)
    print("Loading real estate gold...")
    re = _load_real_estate(year)
    print(f"  {len(re):,} communes with real estate data")

    # 2. Communes reference (required)
    print("Loading communes reference...")
    communes = _load_communes()
    print(f"  {len(communes):,} communes in reference")

    # 3. Merge (drop nom_commune from real estate to avoid _x/_y suffix conflict)
    re = re.drop(columns=["nom_commune"], errors="ignore")
    frame = communes.merge(re, on="code_commune", how="inner")
    print(f"  {len(frame):,} communes after join with real estate")

    # 4. OSM scores (optional)
    print("Loading OSM POI data...")
    osm = _load_osm()
    if osm is not None:
        frame = frame.merge(osm, on="code_commune", how="left")
        pop = frame["population"].clip(lower=1).fillna(1)

        # Scores per 10k inhabitants to normalize across commune sizes
        frame["green_score"] = _normalize_0_100(
            (frame["park_count"].fillna(0) + frame["forest_count"].fillna(0)) / pop * 10_000
        )
        frame["education_score"] = _normalize_0_100(
            (frame["school_count"].fillna(0) + frame["university_count"].fillna(0)) / pop * 10_000
        )
        frame["health_score"] = _normalize_0_100(
            (frame["hospital_count"].fillna(0) + frame["pharmacy_count"].fillna(0)) / pop * 10_000
        )
        frame["services_score"] = _normalize_0_100(
            (frame["supermarket_count"].fillna(0) + frame["restaurant_count"].fillna(0)) / pop * 10_000
        )
        print(f"  OSM scores computed for {frame['green_score'].notna().sum():,} communes")
    else:
        for col in ["green_score", "education_score", "health_score", "services_score"]:
            frame[col] = 50.0

    # 5. GTFS transport scores (optional)
    print("Loading GTFS transport data...")
    gtfs = _load_gtfs()
    if gtfs is not None:
        frame = frame.merge(gtfs, on="code_commune", how="left")
        frame["transport_score"] = _normalize_0_100(frame["stop_count"].fillna(0))
        print(f"  transport_score computed for {frame['transport_score'].notna().sum():,} communes")
    else:
        frame["transport_score"] = 50.0

    # 6. ARCEP network scores (optional)
    print("Loading ARCEP network data...")
    arcep = _load_arcep()
    if arcep is not None:
        frame = frame.merge(arcep, on="code_commune", how="left")
        frame["network_score"] = _normalize_0_100(frame["network_score_raw"].fillna(frame["network_score_raw"].median()))
        frame = frame.drop(columns=["network_score_raw"])
        print(f"  network_score computed for {frame['network_score'].notna().sum():,} communes")
    else:
        frame["network_score"] = 50.0  # neutral fallback

    # 7. Loyers réels ANIL (optional)
    print("Loading loyers réels ANIL...")
    loyers = _load_loyers()
    if loyers is not None:
        frame = frame.merge(loyers, on="code_commune", how="left")
        frame["marche_locatif_actif"] = frame["marche_locatif_actif"].fillna(False)
        print(f"  loyer_m2_app disponible pour {frame['loyer_m2_app'].notna().sum():,} communes")
    else:
        frame["loyer_m2_app"] = None
        frame["loyer_m2_app12"] = None
        frame["loyer_m2_app3"] = None
        frame["nb_annonces_app"] = 0
        frame["marche_locatif_actif"] = False

    # 8. Taxe foncière (optional)
    print("Loading taxe foncière bâtie...")
    taxe = _load_taxe_fonciere()
    if taxe is not None:
        frame = frame.merge(taxe, on="code_commune", how="left")
        print(f"  taux_tfb_dept disponible pour {frame['taux_tfb_dept'].notna().sum():,} communes")
    else:
        frame["taux_tfb_dept"] = None
        frame["vl_m2_commune"] = None

    # 9. INSEE income scores (optional)
    print("Loading INSEE Filosofi data...")
    filosofi = _load_filosofi()
    if filosofi is not None:
        frame = frame.merge(filosofi, on="code_commune", how="left")
        frame["income_score"] = _normalize_0_100(frame["median_income_raw"].fillna(frame["median_income_raw"].median()))
        frame = frame.drop(columns=["median_income_raw"])
        print(f"  income_score computed for {frame['income_score'].notna().sum():,} communes")
    else:
        frame["income_score"] = 50.0

    # 6. Scores derived from real estate data
    frame["affordability_score"] = _normalize_0_100(frame["avg_price_m2"], inverse=True)
    frame["investment_potential_score"] = _normalize_0_100(
        frame.get("price_m2_yoy_variation", pd.Series(0.0, index=frame.index)).fillna(0)
    )

    # 7. Placeholder scores for data not yet ingested (neutral = 50)
    for col in ["transport_score", "green_score", "services_score", "education_score", "health_score"]:
        if col not in frame.columns:
            frame[col] = 50.0

    # 8. Rename columns to match Streamlit expectations
    frame = frame.rename(columns={
        "nom_region": "region",
        "transaction_count": "transaction_count",
        "price_m2_yoy_variation": "annual_price_growth",
    })

    if "annual_price_growth" not in frame.columns:
        frame["annual_price_growth"] = 0.0

    # 9. Persona scores
    frame = _compute_persona_scores(frame)

    # 10. Keep relevant columns
    keep = [
        "code_commune", "nom_commune", "code_departement", "code_region", "region",
        "latitude", "longitude", "population",
        "avg_price_m2", "avg_price", "median_price_m2", "transaction_count", "annual_price_growth",
        "affordability_score", "transport_score", "network_score", "green_score",
        "services_score", "education_score", "health_score", "investment_potential_score", "income_score",
        "score_etudiant", "score_jeune_actif", "score_famille", "score_personne_agee", "score_investisseur",
        "loyer_m2_app", "loyer_m2_app_min", "loyer_m2_app_max",
        "loyer_m2_app12", "loyer_m2_app3",
        "nb_annonces_app", "marche_locatif_actif",
        "taux_tfb_dept", "vl_m2_commune",
    ]
    frame = frame[[c for c in keep if c in frame.columns]]
    frame = frame.dropna(subset=["latitude", "longitude", "avg_price_m2"])

    output = file_path("gold", "territories", "territory_scores.parquet")
    frame.to_parquet(output, index=False)
    print(f"\nTerritory gold written to {output} ({len(frame):,} communes)")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build territory gold layer from real data sources.")
    parser.add_argument("--year", required=True, type=int, help="Reference year for real estate data.")
    args = parser.parse_args()
    build_territory_gold(args.year)


if __name__ == "__main__":
    main()
