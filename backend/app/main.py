from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from backend.app.database import execute_query

app = FastAPI(title="HOMEPEDIA API", version="0.2.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/regions")
def regions():
    return execute_query("SELECT code_region, nom_region FROM regions ORDER BY nom_region")


@app.get("/departements")
def departements(code_region: str | None = None):
    if code_region:
        return execute_query(
            "SELECT code_departement, nom_departement, code_region FROM departements WHERE code_region = '{}' ORDER BY code_departement".format(code_region)
        )
    return execute_query("SELECT code_departement, nom_departement, code_region FROM departements ORDER BY code_departement")


@app.get("/communes")
def communes(code_departement: str | None = None, limit: int = Query(default=500, le=5000)):
    if code_departement:
        return execute_query(
            "SELECT code_commune, nom_commune, latitude, longitude, population FROM communes WHERE code_departement = '{}' ORDER BY nom_commune LIMIT {}".format(code_departement, limit)
        )
    return execute_query(f"SELECT code_commune, nom_commune, latitude, longitude, population FROM communes ORDER BY nom_commune LIMIT {limit}")


@app.get("/scores")
def scores(code_commune: str | None = None, region: str | None = None, limit: int = Query(default=100, le=5000)):
    where_clauses = []
    if code_commune:
        where_clauses.append(f"code_commune = '{code_commune}'")
    if region:
        where_clauses.append(f"region = '{region}'")
    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    return execute_query(f"SELECT * FROM gold_territory_scores {where} ORDER BY score_etudiant DESC LIMIT {limit}")


@app.get("/ranking")
def ranking(
    persona: str = Query(default="etudiant", description="etudiant | jeune_actif | famille | personne_agee | investisseur"),
    region: str | None = None,
    max_price_m2: float | None = None,
    limit: int = Query(default=50, le=500),
):
    score_col = f"score_{persona}"
    valid_personas = ["etudiant", "jeune_actif", "famille", "personne_agee", "investisseur"]
    if persona not in valid_personas:
        raise HTTPException(status_code=400, detail=f"Invalid persona. Choose from: {valid_personas}")

    where_clauses = []
    if region:
        where_clauses.append(f"region = '{region}'")
    if max_price_m2:
        where_clauses.append(f"avg_price_m2 <= {max_price_m2}")
    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    return execute_query(
        f"""
        SELECT code_commune, nom_commune, region, avg_price_m2,
               {score_col} AS persona_score,
               transport_score, network_score, green_score,
               education_score, health_score, affordability_score
        FROM gold_territory_scores
        {where}
        ORDER BY {score_col} DESC
        LIMIT {limit}
        """
    )


@app.get("/commune/{code_commune}")
def commune_detail(code_commune: str):
    results = execute_query(
        f"SELECT * FROM vw_commune_full WHERE code_commune = '{code_commune}' LIMIT 1"
    )
    if not results:
        raise HTTPException(status_code=404, detail="Commune not found")
    return results[0]


@app.get("/compare")
def compare(codes: str = Query(description="Comma-separated commune codes, e.g. 75056,69123")):
    code_list = [c.strip() for c in codes.split(",")]
    codes_str = ", ".join(f"'{c}'" for c in code_list)
    return execute_query(
        f"""
        SELECT code_commune, nom_commune, region, avg_price_m2,
               affordability_score, transport_score, network_score,
               green_score, education_score, health_score,
               score_etudiant, score_jeune_actif, score_famille,
               score_personne_agee, score_investisseur
        FROM gold_territory_scores
        WHERE code_commune IN ({codes_str})
        ORDER BY nom_commune
        """
    )


@app.get("/stats/real-estate")
def real_estate_stats(code_commune: str, year: int | None = None):
    where = f"WHERE code_commune = '{code_commune}'"
    if year:
        where += f" AND year = {year}"
    return execute_query(
        f"SELECT * FROM gold_real_estate {where} ORDER BY year DESC"
    )


@app.get("/listings")
def listings(code_commune: str | None = None, source: str | None = None):
    where_clauses = []
    if code_commune:
        where_clauses.append(f"code_commune = '{code_commune}'")
    if source:
        where_clauses.append(f"source_name = '{source}'")
    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    return execute_query(f"SELECT * FROM silver_listings {where} ORDER BY avg_listing_price_m2 DESC LIMIT 100")
