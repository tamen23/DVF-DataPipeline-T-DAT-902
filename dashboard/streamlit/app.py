from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_PATH = PROJECT_ROOT / "data_lake" / "gold" / "demo" / "territory_scores.parquet"

PERSONAS = {
    "Etudiant": "score_etudiant",
    "Jeune actif": "score_jeune_actif",
    "Famille": "score_famille",
    "Personne agee": "score_personne_agee",
    "Investisseur": "score_investisseur",
}

CRITERIA_COLUMNS = {
    "Affordability": "affordability_score",
    "Transport": "transport_score",
    "Network": "network_score",
    "Green spaces": "green_score",
    "Services": "services_score",
    "Education": "education_score",
    "Health": "health_score",
    "Investment": "investment_potential_score",
}


@st.cache_data
def load_data() -> pd.DataFrame:
    if not DEMO_PATH.exists():
        st.error(
            "Generated demo data is missing. Run: "
            "`python -m data_pipeline.generation.generate_demo_territories`"
        )
        st.stop()
    return pd.read_parquet(DEMO_PATH)


def format_price(value: float) -> str:
    return f"{value:,.0f} EUR/m2".replace(",", " ")


def build_radar(row: pd.Series) -> go.Figure:
    labels = list(CRITERIA_COLUMNS.keys())
    values = [row[column] for column in CRITERIA_COLUMNS.values()]
    values.append(values[0])
    labels.append(labels[0])

    fig = go.Figure(
        data=[
            go.Scatterpolar(
                r=values,
                theta=labels,
                fill="toself",
                name=row["nom_commune"],
            )
        ]
    )
    fig.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, 100]}},
        showlegend=False,
        height=420,
        margin={"l": 30, "r": 30, "t": 40, "b": 30},
    )
    return fig


st.set_page_config(page_title="HOMEPEDIA", layout="wide")

data = load_data()

st.title("HOMEPEDIA")
st.caption("Generated first version - persona-based commune recommendation")

persona = st.sidebar.selectbox("Persona", list(PERSONAS.keys()))
score_column = PERSONAS[persona]

regions = ["All"] + sorted(data["region"].unique().tolist())
selected_region = st.sidebar.selectbox("Region", regions)

max_price = int(data["avg_price_m2"].max())
price_limit = st.sidebar.slider(
    "Maximum price/m2",
    min_value=int(data["avg_price_m2"].min()),
    max_value=max_price,
    value=max_price,
    step=100,
)

minimum_score = st.sidebar.slider("Minimum score", 0, 100, 0)

filtered = data[data["avg_price_m2"] <= price_limit].copy()
if selected_region != "All":
    filtered = filtered[filtered["region"] == selected_region]
filtered = filtered[filtered[score_column] >= minimum_score]
filtered = filtered.sort_values(score_column, ascending=False)

if filtered.empty:
    st.warning("No commune matches the selected filters.")
    st.stop()

best = filtered.iloc[0]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Best commune", best["nom_commune"])
col2.metric("Persona score", f"{best[score_column]:.1f}/100")
col3.metric("Average price/m2", format_price(best["avg_price_m2"]))
col4.metric("Communes matched", f"{len(filtered):,}")

map_data = filtered.rename(columns={score_column: "persona_score"})
fig_map = px.scatter_mapbox(
    map_data,
    lat="latitude",
    lon="longitude",
    size="transaction_count",
    color="persona_score",
    hover_name="nom_commune",
    hover_data={
        "region": True,
        "avg_price_m2": ":.0f",
        "persona_score": ":.1f",
        "transport_score": ":.0f",
        "network_score": ":.0f",
        "latitude": False,
        "longitude": False,
    },
    color_continuous_scale="RdYlGn",
    zoom=4.6,
    height=460,
)
fig_map.update_layout(mapbox_style="open-street-map", margin={"l": 0, "r": 0, "t": 0, "b": 0})

left, right = st.columns([1.35, 1])
with left:
    st.subheader("Recommended communes")
    st.plotly_chart(fig_map, width="stretch")

with right:
    st.subheader("Best commune profile")
    st.plotly_chart(build_radar(best), width="stretch")

st.subheader("Ranking")
ranking_columns = [
    "nom_commune",
    "region",
    "avg_price_m2",
    "annual_price_growth",
    "transaction_count",
    score_column,
    "transport_score",
    "network_score",
    "green_score",
    "services_score",
    "education_score",
    "health_score",
]
ranking = filtered[ranking_columns].rename(
    columns={
        "nom_commune": "commune",
        "avg_price_m2": "price_m2",
        "annual_price_growth": "price_growth",
        score_column: "persona_score",
    }
)
st.dataframe(ranking, width="stretch", hide_index=True)

st.subheader("Score drivers")
criteria = ["affordability_score", "transport_score", "network_score", "green_score", "services_score"]
score_long = filtered.head(8).melt(
    id_vars=["nom_commune"],
    value_vars=criteria,
    var_name="criterion",
    value_name="score",
)
fig_scores = px.bar(
    score_long,
    x="nom_commune",
    y="score",
    color="criterion",
    barmode="group",
    title="Main criteria for top communes",
)
st.plotly_chart(fig_scores, width="stretch")

