from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from data_pipeline.settings import file_path


PERSONA_WEIGHTS = {
    "Etudiant": {
        "affordability_score": 0.30,
        "transport_score": 0.25,
        "education_score": 0.25,
        "services_score": 0.10,
        "network_score": 0.10,
        "green_score": 0.00,
        "health_score": 0.00,
    },
    "Jeune actif": {
        "affordability_score": 0.25,
        "transport_score": 0.20,
        "network_score": 0.20,
        "services_score": 0.20,
        "green_score": 0.10,
        "education_score": 0.05,
        "health_score": 0.00,
    },
    "Famille": {
        "affordability_score": 0.25,
        "green_score": 0.20,
        "services_score": 0.20,
        "education_score": 0.20,
        "transport_score": 0.10,
        "health_score": 0.05,
        "network_score": 0.00,
    },
    "Personne agee": {
        "health_score": 0.30,
        "services_score": 0.25,
        "transport_score": 0.15,
        "affordability_score": 0.15,
        "green_score": 0.10,
        "network_score": 0.05,
        "education_score": 0.00,
    },
    "Investisseur": {
        "investment_potential_score": 0.35,
        "price_growth_score": 0.25,
        "liquidity_score": 0.20,
        "transport_score": 0.10,
        "network_score": 0.05,
        "services_score": 0.05,
    },
}


COMMUNES = [
    {
        "code_commune": "75056",
        "nom_commune": "Paris",
        "departement": "Paris",
        "region": "Ile-de-France",
        "latitude": 48.8566,
        "longitude": 2.3522,
        "population": 2102650,
        "avg_price_m2": 10380,
        "transaction_count": 62000,
        "annual_price_growth": 0.018,
        "transport_score": 98,
        "network_score": 96,
        "green_score": 48,
        "services_score": 99,
        "education_score": 98,
        "health_score": 97,
        "leisure_score": 99,
    },
    {
        "code_commune": "91228",
        "code_postal": "91000",
        "nom_commune": "Evry-Courcouronnes",
        "departement": "Essonne",
        "region": "Ile-de-France",
        "latitude": 48.6238,
        "longitude": 2.4297,
        "population": 67030,
        "avg_price_m2": 2860,
        "transaction_count": 2600,
        "annual_price_growth": 0.027,
        "transport_score": 70,
        "network_score": 89,
        "green_score": 67,
        "services_score": 74,
        "education_score": 78,
        "health_score": 75,
        "leisure_score": 72,
    },
    {
        "code_commune": "92012",
        "code_postal": "92100",
        "nom_commune": "Boulogne-Billancourt",
        "departement": "Hauts-de-Seine",
        "region": "Ile-de-France",
        "latitude": 48.8397,
        "longitude": 2.2399,
        "population": 121580,
        "avg_price_m2": 9110,
        "transaction_count": 6200,
        "annual_price_growth": 0.016,
        "transport_score": 91,
        "network_score": 95,
        "green_score": 58,
        "services_score": 94,
        "education_score": 91,
        "health_score": 90,
        "leisure_score": 88,
    },
    {
        "code_commune": "93066",
        "code_postal": "93200",
        "nom_commune": "Saint-Denis",
        "departement": "Seine-Saint-Denis",
        "region": "Ile-de-France",
        "latitude": 48.9362,
        "longitude": 2.3574,
        "population": 113940,
        "avg_price_m2": 4350,
        "transaction_count": 5400,
        "annual_price_growth": 0.034,
        "transport_score": 89,
        "network_score": 92,
        "green_score": 45,
        "services_score": 83,
        "education_score": 76,
        "health_score": 79,
        "leisure_score": 81,
    },
    {
        "code_commune": "94028",
        "code_postal": "94000",
        "nom_commune": "Creteil",
        "departement": "Val-de-Marne",
        "region": "Ile-de-France",
        "latitude": 48.7904,
        "longitude": 2.4556,
        "population": 92340,
        "avg_price_m2": 5120,
        "transaction_count": 4100,
        "annual_price_growth": 0.025,
        "transport_score": 84,
        "network_score": 91,
        "green_score": 63,
        "services_score": 85,
        "education_score": 81,
        "health_score": 88,
        "leisure_score": 78,
    },
    {
        "code_commune": "69123",
        "nom_commune": "Lyon",
        "departement": "Rhone",
        "region": "Auvergne-Rhone-Alpes",
        "latitude": 45.7640,
        "longitude": 4.8357,
        "population": 522250,
        "avg_price_m2": 5350,
        "transaction_count": 18500,
        "annual_price_growth": 0.026,
        "transport_score": 88,
        "network_score": 93,
        "green_score": 62,
        "services_score": 91,
        "education_score": 93,
        "health_score": 90,
        "leisure_score": 92,
    },
    {
        "code_commune": "31555",
        "nom_commune": "Toulouse",
        "departement": "Haute-Garonne",
        "region": "Occitanie",
        "latitude": 43.6047,
        "longitude": 1.4442,
        "population": 504080,
        "avg_price_m2": 3760,
        "transaction_count": 16200,
        "annual_price_growth": 0.036,
        "transport_score": 78,
        "network_score": 90,
        "green_score": 70,
        "services_score": 84,
        "education_score": 91,
        "health_score": 85,
        "leisure_score": 87,
    },
    {
        "code_commune": "44109",
        "nom_commune": "Nantes",
        "departement": "Loire-Atlantique",
        "region": "Pays de la Loire",
        "latitude": 47.2184,
        "longitude": -1.5536,
        "population": 323200,
        "avg_price_m2": 4210,
        "transaction_count": 12400,
        "annual_price_growth": 0.028,
        "transport_score": 82,
        "network_score": 89,
        "green_score": 78,
        "services_score": 86,
        "education_score": 83,
        "health_score": 83,
        "leisure_score": 86,
    },
    {
        "code_commune": "33063",
        "nom_commune": "Bordeaux",
        "departement": "Gironde",
        "region": "Nouvelle-Aquitaine",
        "latitude": 44.8378,
        "longitude": -0.5792,
        "population": 261800,
        "avg_price_m2": 4690,
        "transaction_count": 11200,
        "annual_price_growth": 0.021,
        "transport_score": 80,
        "network_score": 88,
        "green_score": 65,
        "services_score": 87,
        "education_score": 82,
        "health_score": 84,
        "leisure_score": 90,
    },
    {
        "code_commune": "13055",
        "nom_commune": "Marseille",
        "departement": "Bouches-du-Rhone",
        "region": "Provence-Alpes-Cote d'Azur",
        "latitude": 43.2965,
        "longitude": 5.3698,
        "population": 873000,
        "avg_price_m2": 3350,
        "transaction_count": 21200,
        "annual_price_growth": 0.033,
        "transport_score": 72,
        "network_score": 87,
        "green_score": 61,
        "services_score": 82,
        "education_score": 78,
        "health_score": 86,
        "leisure_score": 89,
    },
    {
        "code_commune": "59350",
        "nom_commune": "Lille",
        "departement": "Nord",
        "region": "Hauts-de-France",
        "latitude": 50.6292,
        "longitude": 3.0573,
        "population": 236710,
        "avg_price_m2": 3630,
        "transaction_count": 9800,
        "annual_price_growth": 0.024,
        "transport_score": 84,
        "network_score": 88,
        "green_score": 58,
        "services_score": 84,
        "education_score": 89,
        "health_score": 82,
        "leisure_score": 82,
    },
    {
        "code_commune": "67482",
        "nom_commune": "Strasbourg",
        "departement": "Bas-Rhin",
        "region": "Grand Est",
        "latitude": 48.5734,
        "longitude": 7.7521,
        "population": 291310,
        "avg_price_m2": 3940,
        "transaction_count": 8700,
        "annual_price_growth": 0.029,
        "transport_score": 86,
        "network_score": 86,
        "green_score": 73,
        "services_score": 82,
        "education_score": 87,
        "health_score": 81,
        "leisure_score": 80,
    },
    {
        "code_commune": "35238",
        "nom_commune": "Rennes",
        "departement": "Ille-et-Vilaine",
        "region": "Bretagne",
        "latitude": 48.1173,
        "longitude": -1.6778,
        "population": 225080,
        "avg_price_m2": 4320,
        "transaction_count": 7600,
        "annual_price_growth": 0.041,
        "transport_score": 81,
        "network_score": 87,
        "green_score": 77,
        "services_score": 80,
        "education_score": 88,
        "health_score": 79,
        "leisure_score": 79,
    },
    {
        "code_commune": "34172",
        "nom_commune": "Montpellier",
        "departement": "Herault",
        "region": "Occitanie",
        "latitude": 43.6119,
        "longitude": 3.8772,
        "population": 302450,
        "avg_price_m2": 3890,
        "transaction_count": 9400,
        "annual_price_growth": 0.038,
        "transport_score": 76,
        "network_score": 88,
        "green_score": 69,
        "services_score": 81,
        "education_score": 90,
        "health_score": 80,
        "leisure_score": 86,
    },
    {
        "code_commune": "54395",
        "nom_commune": "Nancy",
        "departement": "Meurthe-et-Moselle",
        "region": "Grand Est",
        "latitude": 48.6921,
        "longitude": 6.1844,
        "population": 104590,
        "avg_price_m2": 2580,
        "transaction_count": 4200,
        "annual_price_growth": 0.019,
        "transport_score": 73,
        "network_score": 84,
        "green_score": 64,
        "services_score": 76,
        "education_score": 84,
        "health_score": 78,
        "leisure_score": 73,
    },
    {
        "code_commune": "87085",
        "nom_commune": "Limoges",
        "departement": "Haute-Vienne",
        "region": "Nouvelle-Aquitaine",
        "latitude": 45.8336,
        "longitude": 1.2611,
        "population": 131480,
        "avg_price_m2": 1780,
        "transaction_count": 3900,
        "annual_price_growth": 0.015,
        "transport_score": 62,
        "network_score": 80,
        "green_score": 76,
        "services_score": 70,
        "education_score": 71,
        "health_score": 76,
        "leisure_score": 68,
    },
]


def normalize_inverse(series: pd.Series) -> pd.Series:
    return 100 - normalize_positive(series)


def normalize_positive(series: pd.Series) -> pd.Series:
    minimum = series.min()
    maximum = series.max()
    if maximum == minimum:
        return pd.Series([100.0] * len(series), index=series.index)
    return ((series - minimum) / (maximum - minimum) * 100).round(2)


def build_demo_territories() -> pd.DataFrame:
    frame = pd.DataFrame(COMMUNES)
    frame["affordability_score"] = normalize_inverse(frame["avg_price_m2"])
    frame["price_growth_score"] = normalize_positive(frame["annual_price_growth"])
    frame["liquidity_score"] = normalize_positive(frame["transaction_count"])
    frame["investment_potential_score"] = (
        0.45 * frame["price_growth_score"]
        + 0.35 * frame["liquidity_score"]
        + 0.20 * frame["transport_score"]
    ).round(2)

    for persona, weights in PERSONA_WEIGHTS.items():
        score = pd.Series([0.0] * len(frame), index=frame.index)
        for column, weight in weights.items():
            score += frame[column] * weight
        frame[f"score_{persona.lower().replace(' ', '_')}"] = score.round(2)

    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HOMEPEDIA demo territory data.")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    output = Path(args.output) if args.output else file_path("gold", "demo", "territory_scores.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)
    frame = build_demo_territories()
    frame.to_parquet(output, index=False)
    print(f"Wrote generated territory demo data to {output} ({len(frame)} rows)")


if __name__ == "__main__":
    main()
