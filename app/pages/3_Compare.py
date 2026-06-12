"""Module 3 — Compare: communes side by side (prices, rents, income)."""
import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from queries import db

st.set_page_config(page_title="HOMEPEDIA — Compare", page_icon="⚖️", layout="wide")
st.title("⚖️ Compare communes")

communes = db.communes_for_search()
labels = communes.apply(lambda r: f"{r['name']} ({r.department})", axis=1)
by_label = dict(zip(labels, communes["code"]))

selected = st.multiselect(
    "Communes (2 to 4)",
    labels.tolist(),
    default=[l for l in labels.tolist() if l.startswith(("Paris (", "Lyon (", "Marseille ("))][:3],
    max_selections=4,
)
if len(selected) < 2:
    st.info("Pick at least two communes.")
    st.stop()

codes = [by_label[l] for l in selected]
profiles = db.commune_profiles(codes).set_index("code").loc[codes].reset_index()

# ------------------------------------------------------------- metric cards
cols = st.columns(len(profiles))
for col, (_, p) in zip(cols, profiles.iterrows()):
    with col:
        st.subheader(p["name"])
        st.caption(p.department)
        st.metric("Population", f"{int(p.population):,}".replace(",", " "))
        if p.price_m2_apartment:
            st.metric(f"Buy — apartment €/m² ({int(p.dvf_year)})", f"{p.price_m2_apartment:,.0f} €")
        if p.rent_m2_apartment:
            st.metric("Rent — apartment €/m²/month", f"{p.rent_m2_apartment:.1f} €")
        if p.price_m2_apartment and p.rent_m2_apartment:
            yield_pct = p.rent_m2_apartment * 12 / p.price_m2_apartment * 100
            st.metric("Gross rental yield", f"{yield_pct:.1f} %")
        if p.median_income:
            st.metric("Median income / year", f"{p.median_income:,.0f} €".replace(",", " "))

# ------------------------------------------------------------- detail table
st.subheader("All indicators")
table = profiles.rename(
    columns={
        "name": "Commune",
        "department": "Department",
        "population": "Population",
        "price_m2_apartment": "Buy apart. €/m²",
        "price_m2_house": "Buy house €/m²",
        "sales_apartment": "Apart. sales",
        "rent_m2_apartment": "Rent apart. €/m²",
        "rent_m2_house": "Rent house €/m²",
        "median_income": "Median income €",
        "poverty_rate": "Poverty rate %",
    }
).drop(columns=["code", "dvf_year"])
st.dataframe(table.set_index("Commune").T, use_container_width=True)

# ------------------------------------------------------------- evolution
st.subheader("Price evolution — apartments (median €/m²)")
evo = db.price_evolution("Commune", codes, "Appartement")
evo = evo.merge(profiles[["code", "name"]], on="code")
fig = px.line(
    evo, x="year", y="median_price_m2", color="name", markers=True,
    labels={"median_price_m2": "€/m² (median)", "year": "", "name": ""},
)
fig.update_layout(height=380, margin=dict(t=20, b=20))
st.plotly_chart(fig, use_container_width=True)
