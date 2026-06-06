from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_ROOT = PROJECT_ROOT / "data_lake" / "gold" / "real_estate"


st.set_page_config(page_title="HOMEPEDIA", layout="wide")
st.title("HOMEPEDIA")

years = sorted([path.name for path in GOLD_ROOT.glob("*") if path.is_dir()])
if not years:
    st.info("No gold data found. Run the DVF pipeline first.")
    st.stop()

year = st.sidebar.selectbox("Year", years, index=len(years) - 1)
path = GOLD_ROOT / year / f"real_estate_commune_{year}.parquet"
data = pd.read_parquet(path)

query = st.sidebar.text_input("Commune")
if query:
    data = data[data["nom_commune"].str.contains(query, case=False, na=False)]

max_transactions = int(data["transaction_count"].max()) if not data.empty else 1
min_transactions = st.sidebar.slider(
    "Minimum transactions",
    min_value=1,
    max_value=max(1, max_transactions),
    value=1,
)
data = data[data["transaction_count"] >= min_transactions]

col1, col2, col3 = st.columns(3)
col1.metric("Communes", f"{data['code_commune'].nunique():,}")
avg_price_m2 = data["avg_price_m2"].mean()
col2.metric("Average price/m2", "N/A" if pd.isna(avg_price_m2) else f"{avg_price_m2:,.0f} EUR")
col3.metric("Transactions", f"{data['transaction_count'].sum():,}")

top = data.sort_values("avg_price_m2", ascending=False).head(30)
fig = px.bar(top, x="nom_commune", y="avg_price_m2", title="Top communes by average price/m2")
st.plotly_chart(fig, use_container_width=True)

st.dataframe(
    data.sort_values("transaction_count", ascending=False),
    use_container_width=True,
    hide_index=True,
)
