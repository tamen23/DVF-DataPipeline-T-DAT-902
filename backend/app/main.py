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
    where = ""
    params: dict = {}
    if code_region:
        where = "WHERE code_region = %(code_region)s"
        params["code_region"] = code_region
    return execute_query(
        f"SELECT code_departement, nom_departement, code_region FROM departements {where} ORDER BY code_departement",
        params,
    )


@app.get("/communes")
def communes(code_departement: str | None = None, limit: int = Query(default=500, le=5000)):
    where = ""
    params: dict = {"limit": limit}
    if code_departement:
        where = "WHERE code_departement = %(code_departement)s"
        params["code_departement"] = code_departement
    return execute_query(
        f"SELECT code_commune, nom_commune, latitude, longitude, population FROM communes {where} ORDER BY nom_commune LIMIT %(limit)s",
        params,
    )


@app.get("/territories")
def territories():
    """Full gold_territory_scores dump — used by the Streamlit dashboard and BI tools."""
    return execute_query("SELECT * FROM gold_territory_scores")


@app.get("/scores")
def scores(code_commune: str | None = None, region: str | None = None, limit: int = Query(default=100, le=5000)):
    where_clauses = []
    params: dict = {"limit": limit}
    if code_commune:
        where_clauses.append("code_commune = %(code_commune)s")
        params["code_commune"] = code_commune
    if region:
        where_clauses.append("region = %(region)s")
        params["region"] = region
    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    return execute_query(
        f"SELECT * FROM gold_territory_scores {where} ORDER BY score_etudiant DESC LIMIT %(limit)s",
        params,
    )


@app.get("/ranking")
def ranking(
    persona: str = Query(default="etudiant", description="etudiant | jeune_actif | famille | personne_agee | investisseur"),
    region: str | None = None,
    max_price_m2: float | None = None,
    limit: int = Query(default=50, le=500),
):
    valid_personas = ["etudiant", "jeune_actif", "famille", "personne_agee", "investisseur"]
    if persona not in valid_personas:
        raise HTTPException(status_code=400, detail=f"Invalid persona. Choose from: {valid_personas}")
    score_col = f"score_{persona}"

    where_clauses = []
    params: dict = {"limit": limit}
    if region:
        where_clauses.append("region = %(region)s")
        params["region"] = region
    if max_price_m2 is not None:
        where_clauses.append("avg_price_m2 <= %(max_price_m2)s")
        params["max_price_m2"] = max_price_m2
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
        LIMIT %(limit)s
        """,
        params,
    )


@app.get("/commune/{code_commune}")
def commune_detail(code_commune: str):
    results = execute_query(
        "SELECT * FROM vw_commune_full WHERE code_commune = %(code_commune)s LIMIT 1",
        {"code_commune": code_commune},
    )
    if not results:
        raise HTTPException(status_code=404, detail="Commune not found")
    return results[0]


@app.get("/compare")
def compare(codes: str = Query(description="Comma-separated commune codes, e.g. 75056,69123")):
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(status_code=400, detail="No commune codes provided")
    params = {f"code_{i}": code for i, code in enumerate(code_list)}
    placeholders = ", ".join(f"%(code_{i})s" for i in range(len(code_list)))
    return execute_query(
        f"""
        SELECT code_commune, nom_commune, region, avg_price_m2,
               affordability_score, transport_score, network_score,
               green_score, education_score, health_score,
               score_etudiant, score_jeune_actif, score_famille,
               score_personne_agee, score_investisseur
        FROM gold_territory_scores
        WHERE code_commune IN ({placeholders})
        ORDER BY nom_commune
        """,
        params,
    )


@app.get("/stats/real-estate")
def real_estate_stats(code_commune: str, year: int | None = None):
    where = "WHERE code_commune = %(code_commune)s"
    params: dict = {"code_commune": code_commune}
    if year is not None:
        where += " AND year = %(year)s"
        params["year"] = year
    return execute_query(
        f"SELECT * FROM gold_real_estate {where} ORDER BY year DESC",
        params,
    )


@app.get("/listings")
def listings(code_commune: str | None = None, source: str | None = None):
    where_clauses = []
    params: dict = {}
    if code_commune:
        where_clauses.append("code_commune = %(code_commune)s")
        params["code_commune"] = code_commune
    if source:
        where_clauses.append("source_name = %(source)s")
        params["source"] = source
    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    return execute_query(
        f"SELECT * FROM silver_listings {where} ORDER BY avg_listing_price_m2 DESC LIMIT 100",
        params,
    )
