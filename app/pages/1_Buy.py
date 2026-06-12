"""Module 1 — Buy: price map (choropleth, drill-down) and commune ranking."""
import json
import sys
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from queries import db

st.set_page_config(page_title="HOMEPEDIA — Buy", page_icon="🏠", layout="wide")
st.title("🏠 Buy — prices in France")

years = db.available_years()
if not years:
    st.warning("No indicators yet — run the dvf_pipeline DAG first.")
    st.stop()

# ---------------------------------------------------------------- selectors
col1, col2, col3, col4 = st.columns(4)
with col1:
    level = st.selectbox("Level", ["Region", "Department", "Commune"], index=1)
with col2:
    year = st.selectbox("Year", years, index=len(years) - 1)
with col3:
    type_local = st.selectbox("Property type", ["Appartement", "Maison"])
with col4:
    department = None
    if level == "Commune":
        deps = db.departments_list()
        choice = st.selectbox(
            "Department", deps.apply(lambda r: f"{r.code} — {r['name']}", axis=1)
        )
        department = choice.split(" — ")[0]

if level == "Region":
    df = db.region_indicators(year, type_local)
    center, zoom = [46.6, 2.4], 5
elif level == "Department":
    df = db.department_indicators(year, type_local)
    center, zoom = [46.6, 2.4], 5
else:
    df = db.commune_indicators(department, year, type_local)
    center, zoom = None, 9  # computed from data below

df = df.dropna(subset=["geometry"])
if df.empty:
    st.info("No sales for this selection.")
    st.stop()

# ---------------------------------------------------------------- choropleth
geojson = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": json.loads(row.geometry),
            "properties": {
                "code": row.code,
                "name": row["name"],
                "median_price_m2": row.median_price_m2,
                "nb_sales": int(row.nb_sales),
            },
        }
        for _, row in df.iterrows()
    ],
}

if center is None:  # center commune view on the department
    first = json.loads(df.iloc[0].geometry)["coordinates"]
    flat = first
    while isinstance(flat[0], list):
        flat = flat[0]
    center = [flat[1], flat[0]]

m = folium.Map(location=center, zoom_start=zoom, tiles="cartodbpositron")
folium.Choropleth(
    geo_data=geojson,
    data=df,
    columns=["code", "median_price_m2"],
    key_on="feature.properties.code",
    fill_color="YlOrRd",
    fill_opacity=0.75,
    line_opacity=0.3,
    legend_name=f"Median price €/m² — {type_local}, {year}",
    nan_fill_color="lightgray",
).add_to(m)
folium.GeoJson(
    geojson,
    style_function=lambda f: {"fillOpacity": 0, "weight": 0},
    tooltip=folium.GeoJsonTooltip(
        fields=["name", "median_price_m2", "nb_sales"],
        aliases=["", "€/m² (median)", "sales"],
    ),
).add_to(m)

left, right = st.columns([3, 2])
with left:
    st_folium(m, height=560, use_container_width=True, returned_objects=[])

# ---------------------------------------------------------------- ranking
with right:
    st.subheader(f"Ranking — median €/m² ({type_local}, {year})")
    ranking = (
        df[["name", "median_price_m2", "nb_sales", "median_price"]]
        .sort_values("median_price_m2", ascending=False)
        .reset_index(drop=True)
    )
    ranking.index += 1
    st.dataframe(
        ranking.rename(
            columns={
                "name": "Area",
                "median_price_m2": "€/m² (median)",
                "nb_sales": "Sales",
                "median_price": "Median price €",
            }
        ),
        height=520,
        use_container_width=True,
    )

# ---------------------------------------------------------------- evolution
st.subheader("Price evolution")
if len(years) < 2:
    st.info("Evolution needs several years of data — set DVF_YEARS and re-run the pipeline.")
else:
    import plotly.express as px

    top_default = (
        df.sort_values("nb_sales", ascending=False)["name"].head(5).tolist()
    )
    selected = st.multiselect(
        "Areas to compare", df["name"].sort_values().tolist(), default=top_default
    )
    if selected:
        codes = df[df["name"].isin(selected)]["code"].tolist()
        evo = db.price_evolution(level, codes, type_local)
        evo = evo.merge(df[["code", "name"]], on="code")
        fig = px.line(
            evo,
            x="year",
            y="median_price_m2",
            color="name",
            markers=True,
            labels={"median_price_m2": "€/m² (median)", "year": "", "name": ""},
        )
        fig.update_layout(height=380, margin=dict(t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
