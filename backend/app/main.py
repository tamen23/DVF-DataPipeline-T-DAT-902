from __future__ import annotations

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.database import get_db


app = FastAPI(title="HOMEPEDIA API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/regions")
def regions(db: Session = Depends(get_db)):
    return db.execute(text("SELECT id, code_region, nom_region FROM regions ORDER BY nom_region")).mappings().all()


@app.get("/departements")
def departements(region_id: int | None = None, db: Session = Depends(get_db)):
    query = "SELECT id, code_departement, nom_departement, region_id FROM departements"
    params = {}
    if region_id is not None:
        query += " WHERE region_id = :region_id"
        params["region_id"] = region_id
    query += " ORDER BY code_departement"
    return db.execute(text(query), params).mappings().all()


@app.get("/communes")
def communes(departement_id: int | None = None, db: Session = Depends(get_db)):
    query = "SELECT id, code_commune, nom_commune, population FROM communes"
    params = {}
    if departement_id is not None:
        query += " WHERE departement_id = :departement_id"
        params["departement_id"] = departement_id
    query += " ORDER BY nom_commune LIMIT 500"
    return db.execute(text(query), params).mappings().all()


@app.get("/stats/real-estate")
def real_estate_stats(commune_id: int, year: int | None = None, db: Session = Depends(get_db)):
    query = """
        SELECT
            commune_id,
            EXTRACT(YEAR FROM date_mutation)::INTEGER AS year,
            COUNT(*) AS transaction_count,
            AVG(valeur_fonciere)::NUMERIC(14, 2) AS avg_price,
            AVG(prix_m2)::NUMERIC(14, 2) AS avg_price_m2
        FROM real_estate_transactions
        WHERE commune_id = :commune_id
    """
    params = {"commune_id": commune_id}
    if year is not None:
        query += " AND EXTRACT(YEAR FROM date_mutation)::INTEGER = :year"
        params["year"] = year
    query += " GROUP BY commune_id, EXTRACT(YEAR FROM date_mutation) ORDER BY year"
    return db.execute(text(query), params).mappings().all()


@app.get("/stats/network")
def network_stats(commune_id: int, db: Session = Depends(get_db)):
    query = """
        SELECT operator, coverage_4g_score, coverage_5g_score, source
        FROM network_coverage
        WHERE commune_id = :commune_id
        ORDER BY operator
    """
    return db.execute(text(query), {"commune_id": commune_id}).mappings().all()


@app.get("/stats/transport")
def transport_stats(commune_id: int, db: Session = Depends(get_db)):
    query = """
        SELECT transport_score, nearest_station_distance, source
        FROM transport_access
        WHERE commune_id = :commune_id
        ORDER BY id DESC
        LIMIT 1
    """
    return db.execute(text(query), {"commune_id": commune_id}).mappings().all()


@app.get("/scores")
def scores(commune_id: int, year: int | None = None, db: Session = Depends(get_db)):
    query = "SELECT * FROM territorial_scores WHERE commune_id = :commune_id"
    params = {"commune_id": commune_id}
    if year is not None:
        query += " AND year = :year"
        params["year"] = year
    return db.execute(text(query), params).mappings().all()


@app.get("/ranking")
def ranking(year: int, limit: int = 50, db: Session = Depends(get_db)):
    query = """
        SELECT c.code_commune, c.nom_commune, s.year, s.global_score
        FROM territorial_scores s
        JOIN communes c ON c.id = s.commune_id
        WHERE s.year = :year
        ORDER BY s.global_score DESC
        LIMIT :limit
    """
    return db.execute(text(query), {"year": year, "limit": limit}).mappings().all()


@app.get("/compare")
def compare(commune_id_1: int, commune_id_2: int, year: int | None = None, db: Session = Depends(get_db)):
    query = """
        SELECT
            c.id AS commune_id,
            c.code_commune,
            c.nom_commune,
            s.year,
            s.real_estate_score,
            s.network_score,
            s.transport_score,
            s.socio_economic_score,
            s.global_score
        FROM communes c
        LEFT JOIN territorial_scores s ON s.commune_id = c.id
        WHERE c.id IN (:commune_id_1, :commune_id_2)
    """
    params = {"commune_id_1": commune_id_1, "commune_id_2": commune_id_2}
    if year is not None:
        query += " AND s.year = :year"
        params["year"] = year
    query += " ORDER BY c.nom_commune"
    return db.execute(text(query), params).mappings().all()
