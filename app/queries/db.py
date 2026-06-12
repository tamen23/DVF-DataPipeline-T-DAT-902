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
