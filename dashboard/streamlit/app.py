from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_ROOT = PROJECT_ROOT / "data_lake" / "gold" / "real_estate"
CATALOG_PATH = PROJECT_ROOT / "data_lake" / "gold" / "external_catalog" / "documents_csv_profiles.json"


st.set_page_config(page_title="HOMEPEDIA", layout="wide")
st.title("HOMEPEDIA")

page = st.sidebar.radio("Page", ["Real estate MVP", "Documents CSV catalog"])

if page == "Documents CSV catalog":
    if not CATALOG_PATH.exists():
        st.info("No Documents CSV catalog found. Run `python -m data_pipeline.profiling.profile_documents` first.")
        st.stop()

    profiles = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    overview = pd.DataFrame(
        [
            {
                "file": profile["file_name"],
                "rows": profile["row_count"],
                "size_mb": round(profile["size_bytes"] / 1024 / 1024, 1),
                "domain": profile.get("domain", "Unknown"),
                "homepedia_fit": profile.get("homepedia_fit", "To classify"),
            }
            for profile in profiles
        ]
    )
    st.dataframe(overview, use_container_width=True, hide_index=True)

    selected_name = st.selectbox("Dataset", [profile["file_name"] for profile in profiles])
    selected = next(profile for profile in profiles if profile["file_name"] == selected_name)
    st.subheader(selected["file_name"])
    st.write(selected.get("business_summary", "No summary available."))
    st.caption(selected.get("recommended_use", ""))

    col1, col2, col3 = st.columns(3)
    col1.metric("Rows", f"{selected['row_count']:,}")
    col2.metric("Columns", f"{len(selected['columns']):,}")
    col3.metric("Size", f"{selected['size_bytes'] / 1024 / 1024:.1f} MB")

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "column": column,
                    "dtype": selected["dtypes"].get(column),
                    "sample_unique": selected["sample_unique_counts"].get(column),
                    "nulls": selected["null_counts"].get(column, 0),
                }
                for column in selected["columns"]
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    if selected.get("global_top_values"):
        top_column = st.selectbox("Top values column", list(selected["global_top_values"].keys()))
        values = selected["global_top_values"][top_column]
        chart_data = pd.DataFrame({"value": list(values.keys()), "count": list(values.values())})
        st.plotly_chart(px.bar(chart_data, x="value", y="count"), use_container_width=True)
    st.stop()

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
