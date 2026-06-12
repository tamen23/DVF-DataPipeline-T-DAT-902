"""Read-only access to the gold tables — the app never computes, only reads."""
import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


@st.cache_resource
def _engine():
    return create_engine(
        "postgresql+psycopg2://{u}:{p}@{h}:5432/{db}".format(
            u=os.environ["POSTGRES_USER"],
            p=os.environ["POSTGRES_PASSWORD"],
            h=os.environ["POSTGRES_HOST"],
            db=os.environ["POSTGRES_DB"],
        )
    )


@st.cache_data(ttl=600)
def available_years() -> list[int]:
    df = pd.read_sql(
        "SELECT DISTINCT year FROM gold.dvf_department_year ORDER BY year", _engine()
    )
    return df["year"].tolist()


@st.cache_data(ttl=600)
def department_indicators(year: int, type_local: str) -> pd.DataFrame:
    """Department-level indicators + simplified geometry as GeoJSON."""
    sql = text(
        """
        SELECT d.code, d.name, g.nb_sales, g.median_price_m2, g.avg_price_m2,
               g.median_price, ST_AsGeoJSON(d.geom, 5) AS geometry
        FROM gold.dvf_department_year g
        JOIN referential.department d ON d.code = g.code_departement
        WHERE g.year = :year AND g.type_local = :type_local
        """
    )
    return pd.read_sql(sql, _engine(), params={"year": year, "type_local": type_local})


@st.cache_data(ttl=600)
def region_indicators(year: int, type_local: str) -> pd.DataFrame:
    sql = text(
        """
        SELECT r.code, r.name, g.nb_sales, g.median_price_m2, g.avg_price_m2,
               g.median_price, ST_AsGeoJSON(r.geom, 5) AS geometry
        FROM gold.dvf_region_year g
        JOIN referential.region r ON r.code = g.region_code
        WHERE g.year = :year AND g.type_local = :type_local
        """
    )
    return pd.read_sql(sql, _engine(), params={"year": year, "type_local": type_local})


@st.cache_data(ttl=600)
def commune_indicators(department: str, year: int, type_local: str) -> pd.DataFrame:
    """Commune-level indicators for ONE department (keeps the map light)."""
    sql = text(
        """
        SELECT c.code_insee AS code, c.name, g.nb_sales, g.median_price_m2,
               g.avg_price_m2, g.median_price, ST_AsGeoJSON(c.geom, 5) AS geometry
        FROM gold.dvf_commune_year g
        JOIN referential.commune c ON c.code_insee = g.code_commune
        WHERE c.department_code = :dep AND g.year = :year AND g.type_local = :type_local
        """
    )
    return pd.read_sql(
        sql, _engine(), params={"dep": department, "year": year, "type_local": type_local}
    )


@st.cache_data(ttl=600)
def departments_list() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT code, name FROM referential.department ORDER BY code", _engine()
    )


@st.cache_data(ttl=600)
def communes_for_search(min_population: int = 2000) -> pd.DataFrame:
    """Communes selectable in the Compare page (kept light for the browser)."""
    sql = text(
        """
        SELECT c.code_insee AS code, c.name, d.name AS department, c.population
        FROM referential.commune c
        JOIN referential.department d ON d.code = c.department_code
        WHERE c.population >= :pop
        ORDER BY c.population DESC
        """
    )
    return pd.read_sql(sql, _engine(), params={"pop": min_population})


@st.cache_data(ttl=600)
def commune_profiles(codes: list[str]) -> pd.DataFrame:
    """One row per commune: latest prices, rents, income, population."""
    sql = text(
        """
        WITH latest AS (SELECT max(year) AS y FROM gold.dvf_commune_year)
        SELECT c.code_insee AS code, c.name, d.name AS department, c.population,
               app.median_price_m2  AS price_m2_apartment,
               app.nb_sales         AS sales_apartment,
               mai.median_price_m2  AS price_m2_house,
               l.rent_m2_apartment, l.rent_m2_house,
               f.median_income, f.poverty_rate,
               (SELECT y FROM latest) AS dvf_year
        FROM referential.commune c
        JOIN referential.department d ON d.code = c.department_code
        LEFT JOIN gold.dvf_commune_year app
               ON app.code_commune = c.code_insee
              AND app.type_local = 'Appartement' AND app.year = (SELECT y FROM latest)
        LEFT JOIN gold.dvf_commune_year mai
               ON mai.code_commune = c.code_insee
              AND mai.type_local = 'Maison' AND mai.year = (SELECT y FROM latest)
        LEFT JOIN gold.loyers_commune l    ON l.code_insee = c.code_insee
        LEFT JOIN gold.filosofi_commune f  ON f.code_insee = c.code_insee
        WHERE c.code_insee = ANY(:codes)
        """
    )
    return pd.read_sql(sql, _engine(), params={"codes": codes})


_EVOLUTION_TABLES = {
    "Region": ("gold.dvf_region_year", "region_code"),
    "Department": ("gold.dvf_department_year", "code_departement"),
    "Commune": ("gold.dvf_commune_year", "code_commune"),
}


@st.cache_data(ttl=600)
def price_evolution(level: str, codes: list[str], type_local: str) -> pd.DataFrame:
    """Median €/m² per year for the given areas (one line per area)."""
    table, code_col = _EVOLUTION_TABLES[level]
    sql = text(
        f"""
        SELECT {code_col} AS code, year, median_price_m2, nb_sales
        FROM {table}
        WHERE {code_col} = ANY(:codes) AND type_local = :type_local
        ORDER BY year
        """
    )
    return pd.read_sql(
        sql, _engine(), params={"codes": codes, "type_local": type_local}
    )
