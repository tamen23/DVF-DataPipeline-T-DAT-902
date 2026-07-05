from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_LAKE = PROJECT_ROOT / "data_lake" / "gold"
REAL_PATH = DATA_LAKE / "territories" / "territory_scores.parquet"
DEMO_PATH = DATA_LAKE / "demo" / "territory_scores.parquet"
# When set (e.g. http://localhost:8000), the dashboard reads through the
# FastAPI/Hive stack instead of the local parquet files.
API_URL = os.getenv("HOMEPEDIA_API_URL", "").rstrip("/")

# Taux du marché français 2024 par durée
TAUX_MARCHE = {10: 3.20, 15: 3.45, 20: 3.65, 25: 3.80, 30: 4.00}

CRITERIA_COLUMNS = {
    "Accessibilité": "affordability_score",
    "Transport": "transport_score",
    "Réseau mobile": "network_score",
    "Espaces verts": "green_score",
    "Services": "services_score",
    "Éducation": "education_score",
    "Santé": "health_score",
    "Investissement": "investment_potential_score",
}


@st.cache_data
def load_predictions() -> pd.DataFrame | None:
    """Latest ML price predictions (data_pipeline.ml.predict_prices), if any."""
    files = sorted((DATA_LAKE / "ml").glob("price_predictions_*.parquet"))
    if not files:
        return None
    return pd.read_parquet(files[-1])


@st.cache_data
def load_price_history() -> pd.DataFrame | None:
    """Historique gold DVF multi-années : une ligne par commune et par an."""
    frames = []
    for path in sorted((DATA_LAKE / "real_estate").glob("*/real_estate_commune_*.parquet")):
        try:
            year = int(path.parent.name)
        except ValueError:
            continue
        frame = pd.read_parquet(path, columns=["code_commune", "avg_price_m2", "transaction_count"])
        if frame.empty:
            continue
        frame["annee"] = year
        frames.append(frame)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


@st.cache_data
def load_listing_stats() -> pd.DataFrame | None:
    """Stats annonces silver (prix affiché du marché) agrégées toutes sources."""
    files = sorted((PROJECT_ROOT / "data_lake" / "silver" / "listings").glob("source_name=*/*.parquet"))
    if not files:
        return None
    listings = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    listings["_weighted"] = listings["avg_listing_price_m2"] * listings["listing_count"]
    grouped = listings.groupby("code_commune").agg(
        listing_count=("listing_count", "sum"), _weighted=("_weighted", "sum")
    )
    grouped["avg_listing_price_m2"] = grouped["_weighted"] / grouped["listing_count"]
    return grouped.drop(columns="_weighted").reset_index()


@st.cache_data
def load_dept_geojson() -> dict | None:
    """Contours des départements pour la choroplèthe (mis en cache par Streamlit)."""
    try:
        response = requests.get(
            "https://france-geojson.gregoiredavid.fr/repo/departements.geojson", timeout=30
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


@st.cache_data
def load_data() -> pd.DataFrame:
    if API_URL:
        try:
            response = requests.get(f"{API_URL}/territories", timeout=60)
            response.raise_for_status()
            frame = pd.DataFrame(response.json())
            if not frame.empty:
                return frame
            st.warning("L'API ne renvoie aucune donnée — repli sur les fichiers locaux.")
        except Exception as exc:
            st.warning(f"API injoignable ({exc}) — repli sur les fichiers locaux.")
    if REAL_PATH.exists():
        return pd.read_parquet(REAL_PATH)
    if DEMO_PATH.exists():
        st.warning("Données de démonstration. Lancez la pipeline pour les données réelles.")
        return pd.read_parquet(DEMO_PATH)
    st.error("Aucune donnée trouvée. Lancez la pipeline complète.")
    st.stop()


def format_eur(v: float) -> str:
    return f"{v:,.0f} €".replace(",", " ")


def mensualite(montant: float, taux_annuel: float, duree_ans: int) -> float:
    t = taux_annuel / 100 / 12
    n = duree_ans * 12
    if t == 0:
        return montant / n
    return montant * t / (1 - (1 + t) ** -n)


def taux_assurance(age: int) -> float:
    if age < 35:
        return 0.10
    if age < 45:
        return 0.20
    if age < 55:
        return 0.35
    return 0.50


def rendement_brut_commune(prix_m2: float) -> float:
    """Rendement brut locatif estimé selon le prix/m² (marché français 2024)."""
    if prix_m2 < 1_500:
        return 7.0
    if prix_m2 < 2_500:
        return 6.0
    if prix_m2 < 3_500:
        return 5.0
    if prix_m2 < 5_000:
        return 4.2
    if prix_m2 < 8_000:
        return 3.5
    return 3.0


def loyer_estime(prix_m2: float, surface: float, meuble: bool = False,
                 loyer_m2_reel: float | None = None) -> float:
    """Loyer estimé : utilise le loyer réel ANIL si disponible, sinon estimation par rendement."""
    if loyer_m2_reel and not pd.isna(loyer_m2_reel) and loyer_m2_reel > 0:
        loyer_nu = loyer_m2_reel * surface
    else:
        rdt = rendement_brut_commune(prix_m2)
        loyer_nu = prix_m2 * surface * rdt / 100 / 12
    return loyer_nu * 1.15 if meuble else loyer_nu


def build_radar(row: pd.Series, title: str = "") -> go.Figure:
    labels = list(CRITERIA_COLUMNS.keys())
    values = [float(row.get(col, 0)) for col in CRITERIA_COLUMNS.values()]

    # Hover text : score percentile + vrais nombres
    _counts_detail = {
        "Espaces verts":  f"{int(row.get('park_count', 0))} parcs/jardins",
        "Transport":      f"{int(row.get('bus_stop_count', row.get('transport_count', 0)))} arrêts transport",
        "Réseau mobile":  "couverture 4G/5G",
        "Services":       f"{int(row.get('supermarket_count', 0))} commerces · {int(row.get('restaurant_count', 0))} restaurants",
        "Éducation":      f"{int(row.get('school_count', 0))} écoles · {int(row.get('university_count', 0))} universités",
        "Santé":          f"{int(row.get('hospital_count', 0))} hôpitaux · {int(row.get('pharmacy_count', 0))} pharmacies",
        "Investissement": "potentiel prix",
        "Accessibilité":  "prix au m²",
    }
    hover = [f"<b>{lbl}</b><br>Score : {v:.0f}/100<br>{_counts_detail.get(lbl, '')}"
             for lbl, v in zip(labels, values)]
    hover_closed = hover + [hover[0]]
    values_closed = values + [values[0]]
    labels_closed = labels + [labels[0]]

    fig = go.Figure(go.Scatterpolar(
        r=values_closed, theta=labels_closed,
        fill="toself", name=title,
        line_color="#42A5F5",
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover_closed,
    ))
    fig.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, 100],
                              "tickvals": [25, 50, 75, 100],
                              "ticktext": ["25%", "50%", "75%", "top"]}},
        showlegend=False, height=380,
        margin={"l": 30, "r": 30, "t": 40, "b": 30},
        title=title,
    )
    return fig


# ── Tension locative ───────────────────────────────────────────────────────────
def calcul_tension_locative(row: dict) -> dict:
    """
    Évalue le risque de vacance locative d'une commune.
    Retourne un dict avec : niveau (0-3), label, couleur, taux_vacance_estime, detail.
    """
    population = row.get("population", row.get("pop", 0)) or 0
    has_anil = bool(row.get("loyer_m2_app", 0))
    nb_transactions = row.get("transaction_count", 0) or 0
    loyer_source = row.get("_loyer_source", 0) or 0

    score = 0  # 0=excellent, 3=très mauvais

    # Population : proxy de la demande locative
    if population < 500:
        score += 3
    elif population < 2_000:
        score += 2
    elif population < 10_000:
        score += 1

    # Absence de données ANIL = marché locatif inexistant ou non suivi
    if not has_anil:
        score += 2

    # Très peu de transactions DVF = marché illiquide
    if nb_transactions < 3:
        score += 2
    elif nb_transactions < 10:
        score += 1

    # Taux de vacance estimé selon le score total
    if score >= 6:
        niveau, label, couleur = 3, "Marché inexistant", "#E53935"
        taux_vacance = 0.40  # 40% du temps vide = ~5 mois/an
    elif score >= 4:
        niveau, label, couleur = 2, "Marché tendu / saisonnier", "#FB8C00"
        taux_vacance = 0.15  # 15% = ~2 mois/an
    elif score >= 2:
        niveau, label, couleur = 1, "Marché correct", "#FDD835"
        taux_vacance = 0.08  # 8% = ~1 mois/an (standard)
    else:
        niveau, label, couleur = 0, "Marché dynamique", "#43A047"
        taux_vacance = 0.04  # 4% = ~2 semaines/an

    details = []
    if population < 500:
        details.append(f"Population : {int(population):,} hab.".replace(",", " "))
    if not has_anil:
        details.append("Aucune donnée de loyer ANIL")
    if nb_transactions < 10:
        details.append(f"Seulement {int(nb_transactions)} ventes DVF/an")

    return {
        "niveau": niveau,
        "label": label,
        "couleur": couleur,
        "taux_vacance": taux_vacance,
        "detail": " · ".join(details) if details else "Indicateurs favorables",
        "mois_vacance": round(taux_vacance * 12, 1),
    }


# ── Simulation 20 ans ──────────────────────────────────────────────────────────
def simulate_20ans(
    prix_bien: float,
    apport: float,
    taux: float,
    taux_assur_pct: float,
    duree: int,
    loyer_mensuel: float,
    charges_annuelles: float,
    appreciation_annuelle: float,
    apport_2eme: float,
    salaire_net_mensuel: float = 3000.0,
    taux_global_fiscal: float = 0.472,
    regime_fiscal: str = "LMNP - Réel (amortissement)",
    meuble: bool = True,
    horizon: int = 20,
    taux_vacance: float = 0.08,
) -> dict:
    """
    Simule le plan d'investissement sur 20 ans avec achats successifs.

    Cash-flow réel = loyer - crédit - charges - impôts (selon régime fiscal).

    Condition bancaire pour chaque nouvel achat (méthode classique HCSF) :
      taux_endettement = total_credits_mensuels / (salaire_brut + 70% * total_loyers) ≤ 35%
      → salaire_brut estimé = salaire_net / 0.77 (conversion charges sociales)

    Un achat supplémentaire se déclenche quand :
      1. Le cash-flow cumulé libre >= apport requis (on a les fonds)
      2. Le taux d'endettement après le nouveau crédit reste ≤ 35% (la banque accepte)
    """
    t_m = taux / 100 / 12
    t_a = taux_assur_pct / 100 / 12
    n = duree * 12
    salaire_brut_mensuel = salaire_net_mensuel / 0.77  # estimation charges patronales/salariales

    def _impot_annuel_par_bien(loyer_annuel: float, charges_b: float, interets_b: float, prix_b: float) -> float:
        """Calcule l'impôt annuel pour un bien selon le régime fiscal."""
        loyer_lmnp = loyer_annuel * (1.15 if meuble else 1.0)
        if regime_fiscal == "LMNP - Réel (amortissement)":
            amort = prix_b * 0.025 + prix_b * 0.10 * 0.20  # bien + meubles
            base = max(loyer_lmnp - charges_b - interets_b - amort, 0)
        elif regime_fiscal == "LMNP - Micro BIC (abattement 50%)":
            base = loyer_lmnp * 0.50
        elif regime_fiscal == "Nu - Régime réel":
            base = max(loyer_annuel - charges_b - interets_b, 0)
        else:  # Nu - Micro foncier
            base = loyer_annuel * 0.70
        return base * taux_global_fiscal

    class Bien:
        def __init__(self, achat_annee: int, prix: float):
            self.achat_annee = achat_annee
            self.prix = prix
            self.valeur = prix
            montant = max(prix - apport, 0)
            self.capital_rem = montant
            self.montant_initial = montant
            self.mensualite_credit = mensualite(montant, taux, duree) if montant > 0 else 0
            self.mensualite_assur = montant * t_a
            self.mensualite_totale = self.mensualite_credit + self.mensualite_assur
            self.mois_payes = 0

        def step_mois(self):
            if self.mois_payes < n and self.capital_rem > 0:
                interet = self.capital_rem * t_m
                capital_paye = self.mensualite_credit - interet
                self.capital_rem = max(self.capital_rem - capital_paye, 0)
            self.mois_payes += 1

        def credit_mensuel_actuel(self):
            return self.mensualite_totale if self.mois_payes < n else 0

        def interets_annuels(self):
            # Approximation : intérêts = capital_rem * taux
            return self.capital_rem * (taux / 100)

    biens: list[Bien] = [Bien(0, prix_bien)]
    achats = [{"annee": 0, "num_bien": 1, "prix": prix_bien}]

    cashflow_libre = 0.0
    cashflow_total_cumule = 0.0

    annees = []
    nb_biens_series = []
    patrimoine_net_series = []
    valeur_totale_series = []
    dette_totale_series = []
    cashflow_cumule_series = []
    cashflow_mensuel_net_series = []  # après impôts
    taux_endettement_series = []
    blocages_bancaires = []  # années où la banque bloque un achat

    for annee in range(1, horizon + 1):
        for _ in range(12):
            for b in biens:
                b.step_mois()

        nb = len(biens)
        # Loyers encaissés = loyer * (1 - taux_vacance) pour tenir compte des mois vides
        loyers_annuels = loyer_mensuel * 12 * nb * (1 - taux_vacance)
        credits_annuels = sum(b.credit_mensuel_actuel() * 12 for b in biens)
        charges_tot = charges_annuelles * nb
        interets_tot = sum(b.interets_annuels() for b in biens)

        # Impôts : calculés sur l'ensemble du parc
        impots_annuels = sum(
            _impot_annuel_par_bien(loyer_mensuel * 12, charges_annuelles, b.interets_annuels(), b.prix)
            for b in biens
        )

        # Cash-flow net réel après TOUT (crédit + charges + impôts)
        cashflow_annuel_net = loyers_annuels - credits_annuels - charges_tot - impots_annuels
        cashflow_total_cumule += cashflow_annuel_net
        cashflow_libre += cashflow_annuel_net

        for b in biens:
            b.valeur *= (1 + appreciation_annuelle / 100)

        valeur_totale = sum(b.valeur for b in biens)
        dette_totale = sum(b.capital_rem for b in biens)
        patrimoine = valeur_totale - dette_totale + cashflow_total_cumule

        # Taux d'endettement actuel (méthode classique HCSF)
        total_credits_mens = sum(b.credit_mensuel_actuel() for b in biens)
        total_loyers_mens = loyer_mensuel * nb
        revenus_bancaires = salaire_brut_mensuel + 0.70 * total_loyers_mens
        taux_endt = (total_credits_mens / revenus_bancaires * 100) if revenus_bancaires > 0 else 100

        # Tenter un nouvel achat si on a l'apport
        while cashflow_libre >= apport_2eme:
            # Vérification bancaire : est-ce que le nouveau crédit passe les 35% ?
            nouveau_credit_mens = mensualite(prix_bien - apport, taux, duree) + (prix_bien - apport) * t_a
            nouveaux_loyers = total_loyers_mens + loyer_mensuel
            nouveaux_credits = total_credits_mens + nouveau_credit_mens
            nouveaux_revenus = salaire_brut_mensuel + 0.70 * nouveaux_loyers
            nouveau_taux_endt = (nouveaux_credits / nouveaux_revenus * 100) if nouveaux_revenus > 0 else 100

            if nouveau_taux_endt > 35:
                # Banque refuse — on note le blocage et on arrête d'essayer cette année
                blocages_bancaires.append({
                    "annee": annee,
                    "taux_endt": round(nouveau_taux_endt, 1),
                    "nb_biens": nb,
                })
                break

            cashflow_libre -= apport_2eme
            nouveau = Bien(annee, prix_bien)
            biens.append(nouveau)
            achats.append({"annee": annee, "num_bien": len(biens), "prix": prix_bien})
            # Recalcul pour la prochaine itération du while
            total_credits_mens = sum(b.credit_mensuel_actuel() for b in biens)
            total_loyers_mens = loyer_mensuel * len(biens)
            revenus_bancaires = salaire_brut_mensuel + 0.70 * total_loyers_mens
            taux_endt = (total_credits_mens / revenus_bancaires * 100) if revenus_bancaires > 0 else 100

        annees.append(annee)
        nb_biens_series.append(len(biens))
        patrimoine_net_series.append(round(patrimoine, 0))
        valeur_totale_series.append(round(valeur_totale, 0))
        dette_totale_series.append(round(dette_totale, 0))
        cashflow_cumule_series.append(round(cashflow_total_cumule, 0))
        cashflow_mensuel_net_series.append(round(cashflow_annuel_net / 12, 0))
        taux_endettement_series.append(round(taux_endt, 1))

    mensualite_initiale = (mensualite(prix_bien - apport, taux, duree) +
                           (prix_bien - apport) * t_a) if prix_bien > apport else 0
    impot_initial = _impot_annuel_par_bien(
        loyer_mensuel * 12, charges_annuelles,
        (prix_bien - apport) * (taux / 100), prix_bien
    )
    loyer_effectif_initial = loyer_mensuel * 12 * (1 - taux_vacance)
    cf_mensuel_net_initial = (loyer_effectif_initial - mensualite_initiale * 12
                              - charges_annuelles - impot_initial) / 12

    return {
        "annees": annees,
        "valeur_bien": valeur_totale_series,
        "dette_restante": dette_totale_series,
        "patrimoine_net": patrimoine_net_series,
        "cashflow_cumule": cashflow_cumule_series,
        "cashflow_mensuel_brut": cashflow_mensuel_net_series,
        "nb_biens": nb_biens_series,
        "taux_endettement": taux_endettement_series,
        "blocages_bancaires": blocages_bancaires,
        "achats": achats[1:],
        "annee_2eme": achats[1]["annee"] if len(achats) > 1 else None,
        "mensualite_totale": mensualite_initiale,
        "cashflow_mensuel": cf_mensuel_net_initial,
    }


# ══════════════════════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="HOMEPEDIA — Investisseur", layout="wide", page_icon="🏦")

data = load_data()

# Le générateur démo et l'API n'exposent pas toujours code_departement :
# on le dérive du code INSEE (2 premiers caractères, 3 pour les DOM).
if "code_departement" not in data.columns and "code_commune" in data.columns:
    _codes = data["code_commune"].astype(str)
    data["code_departement"] = np.where(_codes.str.startswith("97"), _codes.str[:3], _codes.str[:2])

# ── Prédictions ML (optionnelles) ─────────────────────────────────────────────
predictions = load_predictions()
PREDICTION_YEAR = None
if predictions is not None and "code_commune" in data.columns:
    PREDICTION_YEAR = int(predictions["target_year"].iloc[0])
    data = data.merge(
        predictions[["code_commune", "predicted_avg_price_m2", "predicted_growth_pct"]],
        on="code_commune", how="left",
    )

# ── SIDEBAR : Profil investisseur ─────────────────────────────────────────────
st.sidebar.title("🏦 Mon profil investisseur")

# ── Persona : re-pondère le score qualité de vie du classement ────────────────
PERSONAS = {
    "Investisseur": None,  # pondération manuelle par critères (comportement historique)
    "Étudiant": "score_etudiant",
    "Jeune actif": "score_jeune_actif",
    "Famille": "score_famille",
    "Personne âgée": "score_personne_agee",
}
persona_label = st.sidebar.selectbox(
    "👤 Persona",
    list(PERSONAS),
    index=0,
    help="Chaque persona pondère différemment les critères (santé, transport, éducation…) — "
         "poids documentés dans docs/personas.md, scores précalculés dans le gold.",
)
persona_col = PERSONAS[persona_label]
if persona_col:
    st.sidebar.caption(f"Classement pondéré pour **{persona_label}**.")

mode_expert = st.sidebar.toggle("Mode expert", value=False,
    help="Activez pour accéder à tous les paramètres. En mode débutant, les valeurs sont pré-remplies avec des hypothèses standards.")

st.sidebar.markdown("---")

if not mode_expert:
    st.sidebar.markdown("### 3 infos suffisent pour démarrer")
    st.sidebar.caption("Les autres paramètres sont pré-remplis avec des valeurs standards. Activez le mode expert pour les personnaliser.")

salaire_net = st.sidebar.number_input(
    "Salaire net mensuel (€)",
    min_value=1_000, max_value=20_000, value=3_000, step=100,
    help="Votre salaire net après impôts. Sert à calculer combien la banque peut vous prêter (règle des 33% : votre mensualité ne peut pas dépasser 1/3 de votre salaire).",
)
apport = st.sidebar.number_input(
    "Apport disponible (€)",
    min_value=0, max_value=500_000, value=20_000, step=1_000,
    help="La somme que vous avez économisée et que vous pouvez investir directement. Plus l'apport est élevé, moins vous empruntez et plus votre cash-flow est positif.",
)

meuble = st.sidebar.toggle(
    "Location meublée",
    value=True,
    help="Un bien meublé se loue ~15% plus cher qu'un bien nu et permet le régime LMNP au réel (amortissement du bien + meubles → impôt quasi nul les 10 premières années). Recommandé pour les studios et T2.",
)

if mode_expert:
    age = st.sidebar.number_input("Votre âge", min_value=18, max_value=65, value=30, step=1,
        help="Sert à calculer le taux d'assurance emprunteur, qui augmente avec l'âge.")
    duree = st.sidebar.select_slider(
        "Durée du prêt",
        options=[10, 15, 20, 25], value=20,
        help="Plus la durée est longue, plus la mensualité est basse — mais plus vous payez d'intérêts au total.",
    )
    surface = st.sidebar.slider("Surface recherchée (m²)", min_value=20, max_value=120, value=50, step=5)
    taux_credit_manuel = st.sidebar.number_input(
        "Taux du crédit (%)",
        min_value=0.5, max_value=8.0,
        value=float(TAUX_MARCHE.get(duree, 3.65)),
        step=0.05, format="%.2f",
        help="Taux nominal annuel hors assurance. Le taux marché 2025 est affiché par défaut selon la durée.",
    )
    frais_notaire_pct = st.sidebar.slider(
        "Frais de notaire (%)",
        min_value=2.0, max_value=9.0, value=7.5, step=0.5,
        help="Environ 7–8% pour l'ancien, 2–3% pour le neuf. Inclus dans le coût total mais non financés par la banque en général.",
    )
else:
    age = 30
    duree = 20
    surface = 45
    taux_credit_manuel = None   # None = valeur marché automatique
    frais_notaire_pct  = 7.5

st.sidebar.markdown("---")

if mode_expert:
    st.sidebar.markdown("### Charges estimées")
    charges_copro = st.sidebar.number_input("Copropriété (€/an)", 0, 5_000, 1_200, 100,
        help="Charges de copropriété annuelles (eau, entretien parties communes, syndic). Demandez le montant exact au vendeur.")
    taxe_fonciere_fixe = st.sidebar.number_input("Taxe foncière (€/an)", 0, 5_000, 0, 50,
        help="Laissez à 0 pour utiliser le taux réel DGFiP par commune (recommandé). Saisissez une valeur pour forcer un montant fixe.")
    frais_gestion_pct = st.sidebar.slider("Gestion locative (%)", 0, 12, 0,
        help="Commission d'une agence si vous ne gérez pas vous-même (généralement 6–8%). Mettez 0 si vous gérez directement.")
else:
    charges_copro     = 1_200
    taxe_fonciere_fixe = 0   # 0 = calculée par commune via taux DGFiP
    frais_gestion_pct = 0
    st.sidebar.caption("💡 Charges standard : 1 200 €/an copro · taxe foncière calculée par commune (taux réel DGFiP) · gestion en direct")

# taxe_fonciere_fixe = 0 → on calcule par commune | >0 → valeur uniforme
_use_taux_reel = (taxe_fonciere_fixe == 0)
charges_copro_annuelles = charges_copro  # sans taxe foncière (ajoutée par commune)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔎 Département cible")

dept_df = (
    data[["code_departement", "region"]]
    .dropna(subset=["code_departement"])
    .drop_duplicates("code_departement")
    .sort_values("code_departement")
)
DEPT_NOMS = {
    "01":"Ain","02":"Aisne","03":"Allier","04":"Alpes-de-Haute-Provence","05":"Hautes-Alpes",
    "06":"Alpes-Maritimes","07":"Ardèche","08":"Ardennes","09":"Ariège","10":"Aube",
    "11":"Aude","12":"Aveyron","13":"Bouches-du-Rhône","14":"Calvados","15":"Cantal",
    "16":"Charente","17":"Charente-Maritime","18":"Cher","19":"Corrèze","2A":"Corse-du-Sud",
    "2B":"Haute-Corse","21":"Côte-d'Or","22":"Côtes-d'Armor","23":"Creuse","24":"Dordogne",
    "25":"Doubs","26":"Drôme","27":"Eure","28":"Eure-et-Loir","29":"Finistère",
    "30":"Gard","31":"Haute-Garonne","32":"Gers","33":"Gironde","34":"Hérault",
    "35":"Ille-et-Vilaine","36":"Indre","37":"Indre-et-Loire","38":"Isère","39":"Jura",
    "40":"Landes","41":"Loir-et-Cher","42":"Loire","43":"Haute-Loire","44":"Loire-Atlantique",
    "45":"Loiret","46":"Lot","47":"Lot-et-Garonne","48":"Lozère","49":"Maine-et-Loire",
    "50":"Manche","51":"Marne","52":"Haute-Marne","53":"Mayenne","54":"Meurthe-et-Moselle",
    "55":"Meuse","56":"Morbihan","57":"Moselle","58":"Nièvre","59":"Nord",
    "60":"Oise","61":"Orne","62":"Pas-de-Calais","63":"Puy-de-Dôme","64":"Pyrénées-Atlantiques",
    "65":"Hautes-Pyrénées","66":"Pyrénées-Orientales","67":"Bas-Rhin","68":"Haut-Rhin","69":"Rhône",
    "70":"Haute-Saône","71":"Saône-et-Loire","72":"Sarthe","73":"Savoie","74":"Haute-Savoie",
    "75":"Paris","76":"Seine-Maritime","77":"Seine-et-Marne","78":"Yvelines","79":"Deux-Sèvres",
    "80":"Somme","81":"Tarn","82":"Tarn-et-Garonne","83":"Var","84":"Vaucluse",
    "85":"Vendée","86":"Vienne","87":"Haute-Vienne","88":"Vosges","89":"Yonne",
    "90":"Territoire de Belfort","91":"Essonne","92":"Hauts-de-Seine","93":"Seine-Saint-Denis",
    "94":"Val-de-Marne","95":"Val-d'Oise",
}
dept_options = {
    f"{DEPT_NOMS.get(code, code)} ({code})": code
    for code in dept_df["code_departement"].tolist()
    if code in DEPT_NOMS
}
dept_options_sorted = dict(sorted(dept_options.items()))
selected_dept_label = st.sidebar.selectbox(
    "Département", options=[""] + list(dept_options_sorted.keys()), index=0
)
selected_dept = dept_options_sorted.get(selected_dept_label, "")
selected_search = ""  # communes sélectionnées via le classement critères

st.sidebar.markdown("---")
st.sidebar.markdown("### 💶 Régime fiscal")

if mode_expert:
    st.sidebar.caption("Impacte le rendement net réel après impôts")
    regime_fiscal = st.sidebar.selectbox(
        "Régime d'imposition",
        options=[
            "LMNP - Réel (amortissement)",
            "LMNP - Micro BIC (abattement 50%)",
            "Nu - Régime réel",
            "Nu - Micro foncier (abattement 30%)",
        ],
        index=0,
        help="LMNP Réel = meilleur pour débuter : vous amortissez le bien et les meubles → impôt souvent 0€ pendant 10–15 ans.",
    )
    tmi = st.sidebar.select_slider(
        "Tranche marginale d'imposition (TMI)",
        options=[0, 11, 30, 41, 45],
        value=30,
        format_func=lambda x: f"{x}%",
        help="Votre tranche d'imposition sur le revenu. Vérifiez sur votre avis d'imposition.",
    )
else:
    regime_fiscal = "LMNP - Réel (amortissement)"
    tmi = 30
    st.sidebar.caption("✅ Régime appliqué : **LMNP Réel** (amortissement du bien + meubles → impôt quasi nul les premières années)")

taux_global_fiscal = (tmi + 17.2) / 100

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔍 Fiabilité des prix")
st.sidebar.caption("Filtre basé sur le nombre de ventes DVF enregistrées dans la commune")

fiabilite_min = st.sidebar.radio(
    "Afficher uniquement les communes avec",
    options=["Toutes", "≥ 10 ventes (fiable)", "≥ 30 ventes (très fiable)"],
    index=0,
    help="Moins de ventes = prix/m² moins fiable statistiquement. Recommandé : ≥ 10 ventes.",
)
_fiabilite_seuil = 0 if fiabilite_min == "Toutes" else (10 if "10" in fiabilite_min else 30)

# Poids égaux pour le score qualité (critères non pondérables manuellement)
w_transport = w_vert = w_commerces = w_mobile = w_education = w_sante = 1

# ── CALCUL CAPACITÉ D'EMPRUNT ─────────────────────────────────────────────────
taux_base = taux_credit_manuel if taux_credit_manuel is not None else TAUX_MARCHE.get(duree, 3.65)
taux_assur_pct = taux_assurance(age)
# Frais de notaire : payés cash sur l'apport (la banque ne les finance pas)
# Apport réel sur le bien = apport total - frais de notaire réservés
# Les frais de notaire sont calculés sur le prix du bien au moment de la simulation
# Pour le calcul de la carte : on utilise le ratio frais_notaire_pct pour estimer l'apport disponible
_apport_frais_notaire_ratio = frais_notaire_pct / 100  # ex: 0.075 pour 7.5%
mensualite_max = salaire_net * 0.33  # règle des 33%
mensualite_assur_ratio = taux_assur_pct / 100 / 12

# Capacité emprunt : résout mensualite(M, taux, duree) + M*assur/12 = mensualite_max
# => M * [taux_m/(1-(1+taux_m)^-n) + assur_m] = mensualite_max
taux_m = taux_base / 100 / 12
n_m = duree * 12
facteur = taux_m / (1 - (1 + taux_m) ** -n_m) + mensualite_assur_ratio
capacite_emprunt = mensualite_max / facteur
prix_max_bien = capacite_emprunt + apport

# Mensualité réelle avec ce bien
mensualite_credit_val = mensualite(capacite_emprunt, taux_base, duree)
mensualite_assur_val = capacite_emprunt * mensualite_assur_ratio
mensualite_totale_val = mensualite_credit_val + mensualite_assur_val

# ── TITRE ──────────────────────────────────────────────────────────────────────
st.title("🏦 HOMEPEDIA — Où investir en France ?")

if not mode_expert:
    st.info(
        "👋 **Bienvenue !** Cette plateforme vous aide à trouver où investir dans l'immobilier locatif en France.  \n"
        "**Comment ça marche en 3 étapes :**  \n"
        "1️⃣ **Renseignez votre salaire et votre apport** dans la barre à gauche — on calcule automatiquement ce que la banque peut vous prêter  \n"
        "2️⃣ **Choisissez un département** — la carte et le tableau vous montrent les meilleures communes où le loyer couvre votre crédit  \n"
        "3️⃣ **Cliquez sur une commune** dans le tableau pour voir son profil complet et simuler votre investissement sur 20 ans  \n\n"
        "💡 *L'objectif : trouver un appartement dont le loyer couvre entièrement votre mensualité de crédit — vous constituez un patrimoine sans effort.*"
    )
else:
    st.markdown(
        "**Objectif :** trouver un appartement dont le loyer couvre entièrement la mensualité du crédit "
        "— et simuler le chemin vers votre 2ème achat."
    )

# ── BLOC CAPACITÉ ──────────────────────────────────────────────────────────────
st.subheader("Étape 1 — Votre capacité d'emprunt")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Capacité d'emprunt", format_eur(capacite_emprunt))
c2.metric("Prix max du bien", format_eur(prix_max_bien),
          delta=f"apport {format_eur(apport)}", delta_color="off")
c3.metric("Mensualité max (33%)", format_eur(mensualite_max))
c4.metric("Mensualité réelle", format_eur(mensualite_totale_val),
          delta=f"dont assurance {mensualite_assur_val:.0f} €", delta_color="off")
c5.metric("Taux retenu", f"{taux_base}%", delta=f"sur {duree} ans", delta_color="off")

st.info(
    f"Avec **{format_eur(salaire_net)}/mois** de salaire, votre mensualité max est "
    f"**{format_eur(mensualite_max)}** (règle des 33%). Vous pouvez emprunter jusqu'à "
    f"**{format_eur(capacite_emprunt)}**, soit un bien à **{format_eur(prix_max_bien)}** avec votre apport."
)

st.divider()

# ── FILTRAGE COMMUNES AUTOFINANCÉES ───────────────────────────────────────────
st.subheader("Étape 2 — Communes où votre investissement s'autofinance")

# Calcule les métriques sur TOUTES les communes (avant filtre budget)
df_all = data.copy()
df_all["prix_bien_possible"] = df_all["avg_price_m2"] * surface
df_all["loyer_estime"] = df_all.apply(
    lambda r: loyer_estime(
        r["avg_price_m2"], surface, meuble,
        loyer_m2_reel=r.get("loyer_m2_app12") if surface <= 50 else r.get("loyer_m2_app3") if surface >= 65 else r.get("loyer_m2_app")
    ), axis=1
)
df_all["loyer_source"] = df_all.apply(
    lambda r: "ANIL 2024" if pd.notna(r.get("loyer_m2_app")) and r.get("loyer_m2_app", 0) > 0 else "Estimation",
    axis=1
)
df_all["frais_gestion"] = df_all["loyer_estime"] * frais_gestion_pct / 100 * 12

# Taxe foncière : estimation par commune via VLC DGFiP + taux dept, ou valeur fixe
if _use_taux_reel and "taux_tfb_dept" in df_all.columns and df_all["taux_tfb_dept"].notna().any():
    # VLC = vl_m2_commune (officielle DGFiP) ou fallback loyer ANIL × 0.5
    if "vl_m2_commune" in df_all.columns and df_all["vl_m2_commune"].notna().any():
        _vl_ref = df_all["vl_m2_commune"].fillna(
            df_all["loyer_m2_app"].fillna(df_all["avg_price_m2"] * 0.004) * 0.5
        )
    else:
        _vl_ref = df_all["loyer_m2_app"].fillna(df_all["avg_price_m2"] * 0.004) * 0.5
    _vlc = _vl_ref * surface * 12
    _taux = df_all["taux_tfb_dept"].fillna(22.5) / 100
    df_all["taxe_fonciere_estimee"] = (_vlc * _taux).round(0)
else:
    df_all["taxe_fonciere_estimee"] = taxe_fonciere_fixe if not _use_taux_reel else 700

df_all["charges_tot_annuelles"] = charges_copro_annuelles + df_all["taxe_fonciere_estimee"] + df_all["frais_gestion"]
# Frais de notaire = prix_bien × taux_notaire (payés sur l'apport)
# Apport disponible pour le bien = apport total - frais de notaire
df_all["frais_notaire"] = df_all["prix_bien_possible"] * _apport_frais_notaire_ratio
df_all["apport_sur_bien"] = (apport - df_all["frais_notaire"]).clip(lower=0)
df_all["montant_emprunte"] = (df_all["prix_bien_possible"] - df_all["apport_sur_bien"]).clip(lower=0)
df_all["mensualite_commune"] = df_all["montant_emprunte"].apply(
    lambda m: mensualite(m, taux_base, duree) + m * mensualite_assur_ratio
)
# ── CALCUL FISCAL ─────────────────────────────────────────────────────────────
df_all["interets_annuels"] = df_all["montant_emprunte"] * taux_base / 100

_loyer_nu_annuel   = df_all["loyer_estime"] * 12
_loyer_lmnp_annuel = df_all["loyer_estime"] * 1.15 * 12
_loyer_regime = _loyer_lmnp_annuel if "LMNP" in regime_fiscal else _loyer_nu_annuel

_amort_bien    = df_all["prix_bien_possible"] * 0.025
_amort_meubles = df_all["prix_bien_possible"] * 0.10 * 0.20

if regime_fiscal == "LMNP - Réel (amortissement)":
    _base = (_loyer_lmnp_annuel - df_all["charges_tot_annuelles"]
             - df_all["interets_annuels"] - _amort_bien - _amort_meubles).clip(lower=0)
    df_all["impot_annuel"] = _base * taux_global_fiscal
elif regime_fiscal == "LMNP - Micro BIC (abattement 50%)":
    _base = _loyer_lmnp_annuel * 0.50
    df_all["impot_annuel"] = _base * taux_global_fiscal
elif regime_fiscal == "Nu - Régime réel":
    _base = (_loyer_nu_annuel - df_all["charges_tot_annuelles"]
             - df_all["interets_annuels"]).clip(lower=0)
    df_all["impot_annuel"] = _base * taux_global_fiscal
else:  # Nu - Micro foncier
    _base = _loyer_nu_annuel * 0.70
    df_all["impot_annuel"] = _base * taux_global_fiscal

# Cash-flow brut = loyer (selon régime) - mensualité - charges  [AVANT impôts]
df_all["cashflow_mensuel"] = (
    _loyer_regime / 12
    - df_all["mensualite_commune"]
    - df_all["charges_tot_annuelles"] / 12
)

# Cash-flow net = loyer (selon régime) - mensualité - charges - impôts  [APRÈS impôts]
# Par construction : net ≤ brut toujours
df_all["cashflow_net_fiscal"] = (
    df_all["cashflow_mensuel"] - df_all["impot_annuel"] / 12
)

df_all["rendement_brut"] = df_all.apply(lambda r: rendement_brut_commune(r["avg_price_m2"]), axis=1)
df_all["rendement_net"] = (
    (_loyer_regime - df_all["charges_tot_annuelles"]) / df_all["prix_bien_possible"].clip(lower=1) * 100
).clip(lower=0)
df_all["rendement_net_fiscal"] = (
    (_loyer_regime - df_all["charges_tot_annuelles"] - df_all["impot_annuel"])
    / df_all["prix_bien_possible"].clip(lower=1) * 100
).clip(lower=0)

# Score qualité de vie pondéré par les critères sidebar
_weights = {
    "transport_score":  w_transport,
    "green_score":      w_vert,
    "services_score":   w_commerces,
    "network_score":    w_mobile,
    "education_score":  w_education,
    "health_score":     w_sante,
}
_total_w = sum(_weights.values()) or 1
df_all["critere_score"] = sum(
    (df_all[col] if col in df_all.columns else 50) * w / _total_w
    for col, w in _weights.items()
)

# Persona sélectionné : le score qualité de vie devient le score persona
# précalculé dans le gold (pondérations de docs/personas.md).
if persona_col and persona_col in df_all.columns:
    df_all["critere_score"] = df_all[persona_col].fillna(50)

# Filtre budget uniquement pour le tableau/ranking
df = df_all[df_all["prix_bien_possible"] <= prix_max_bien * 1.1].copy()

# Communes autofinancées = cash-flow >= 0 (dans le budget)
autofinancees = df[df["cashflow_mensuel"] >= 0].copy()
deficitaires = df[df["cashflow_mensuel"] < 0].copy()

col_map, col_radar = st.columns([1.6, 1])

with col_map:
    if selected_dept:
        dept_data = df_all[df_all["code_departement"] == selected_dept]
        center_lat = dept_data["latitude"].mean() if not dept_data.empty else 46.5
        center_lon = dept_data["longitude"].mean() if not dept_data.empty else 2.3
        zoom = 8
        map_display = dept_data.copy()
    else:
        zoom, center_lat, center_lon = 5, 46.5, 2.3
        map_display = df_all.copy()

    map_display["cashflow_affiche"] = map_display["cashflow_mensuel"].clip(-500, 500)
    map_display["_tooltip"] = map_display.apply(lambda r: (
        f"<b>{r['nom_commune']}</b> ({r.get('code_departement','')})<br>"
        f"━━━━━━━━━━━━━━━━━━━━━━<br>"
        f"💰 Cash-flow net : <b>{r['cashflow_net_fiscal']:+.0f} €/mois</b><br>"
        f"🏠 Prix du bien ({surface}m²) : <b>{r['prix_bien_possible']:,.0f} €</b><br>"
        f"🔑 Loyer estimé : <b>{r['loyer_estime']:.0f} €/mois</b><br>"
        f"📈 Rendement brut : <b>{r['rendement_brut']:.1f}%</b><br>"
        f"📊 Rendement net fiscal : <b>{r['rendement_net_fiscal']:.1f}%</b><br>"
        f"━━━━━━━━━━━━━━━━━━━━━━<br>"
        f"💳 Mensualité crédit : {r['mensualite_commune']:.0f} €/mois<br>"
        f"📉 Prix/m² : {r['avg_price_m2']:.0f} €/m²<br>"
        f"🔢 Ventes DVF : {int(r['transaction_count']) if pd.notna(r.get('transaction_count')) else '?'} transactions"
    ), axis=1)

    fig_map = px.scatter_mapbox(
        map_display,
        lat="latitude", lon="longitude",
        color="cashflow_mensuel",
        size=map_display["cashflow_mensuel"].clip(lower=10).fillna(10),
        hover_name="nom_commune",
        hover_data={
            "latitude": False, "longitude": False,
            "cashflow_mensuel": False,
            "_tooltip": True,
        },
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=0,
        range_color=[-300, 300],
        center={"lat": center_lat, "lon": center_lon},
        zoom=zoom,
        height=420,
    )
    fig_map.update_traces(hovertemplate="%{customdata[0]}<extra></extra>")
    fig_map.update_layout(
        mapbox_style="open-street-map",
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        coloraxis_colorbar={"title": "Cash-flow (€/mois)"},
    )
    st.plotly_chart(fig_map, use_container_width=True, key="map_principale")

st.caption("🟢 Vert = cash-flow positif (loyer > mensualité) · 🔴 Rouge = effort mensuel nécessaire")

st.divider()

# ── TOP 10 COMMUNES ────────────────────────────────────────────────────────────
if selected_dept:
    st.subheader(f"Top 10 communes où investir — {selected_dept_label}")
    _pool = df_all[df_all["code_departement"] == selected_dept].copy()
else:
    st.subheader("Top 10 communes où investir")
    _pool = df_all[df_all["prix_bien_possible"] <= prix_max_bien * 1.1].copy()

if _fiabilite_seuil > 0:
    _pool = _pool[_pool["transaction_count"].fillna(0) >= _fiabilite_seuil]

# Pré-calcul du niveau de risque vacance pour chaque commune du pool
if not _pool.empty:
    _pool["_risque_vacance"] = _pool.apply(
        lambda r: calcul_tension_locative(r.to_dict())["niveau"], axis=1
    )

# ── Filtres Excel-like ────────────────────────────────────────────────────────
with st.expander("🔽 Filtres avancés", expanded=False):
    fc1, fc2, fc3 = st.columns(3)
    fc4, fc5, fc6 = st.columns(3)

    with fc1:
        _cf_min_val = int(_pool["cashflow_net_fiscal"].min()) if not _pool.empty else -1000
        _cf_max_val = int(_pool["cashflow_net_fiscal"].max()) if not _pool.empty else 1000
        _cf_filter_min = st.slider(
            "💰 Cash-flow net minimum (€/mois)",
            min_value=_cf_min_val, max_value=_cf_max_val,
            value=_cf_min_val, step=10,
            help="Masquer les communes dont le cash-flow net est inférieur à cette valeur",
        )

    with fc2:
        _rdt_min = float(_pool["rendement_net_fiscal"].min()) if not _pool.empty else 0.0
        _rdt_max = float(_pool["rendement_net_fiscal"].max()) if not _pool.empty else 15.0
        _rdt_filter_min = st.slider(
            "📈 Rendement net minimum (%)",
            min_value=round(_rdt_min, 1), max_value=round(_rdt_max, 1),
            value=round(_rdt_min, 1), step=0.1,
            help="Ex : mettre à 5% pour ne voir que les communes avec rendement net ≥ 5%",
        )

    with fc3:
        _prix_min_val = int(_pool["prix_bien_possible"].min()) if not _pool.empty else 0
        _prix_max_val = int(_pool["prix_bien_possible"].max()) if not _pool.empty else 500_000
        _prix_range = st.slider(
            f"🏠 Budget ({surface}m²) (€)",
            min_value=_prix_min_val, max_value=_prix_max_val,
            value=(_prix_min_val, _prix_max_val), step=1_000,
            help="Filtrer sur la fourchette de prix d'achat",
        )

    with fc4:
        _risque_options = {
            "🟢 Marché dynamique (~4%)": 0,
            "🟡 Marché correct (~8%)": 1,
            "🟠 Saisonnier (~15%)": 2,
            "🔴 Marché inexistant (~40%)": 3,
        }
        _risque_choix = st.multiselect(
            "🏘️ Risque de vacance locative",
            options=list(_risque_options.keys()),
            default=list(_risque_options.keys()),
            help="Décochez 🔴 pour exclure les communes où personne ne loue",
        )
        _risque_niveaux = [_risque_options[r] for r in _risque_choix] if _risque_choix else [0, 1, 2, 3]

    with fc5:
        _only_positive_cf = st.checkbox(
            "✅ Cash-flow positif uniquement",
            value=False,
            help="Afficher uniquement les communes où l'investissement s'autofinance (cash-flow net ≥ 0)",
        )

    with fc6:
        _only_anil = st.checkbox(
            "✅ Données loyer fiables uniquement",
            value=False,
            help="Afficher uniquement les communes avec données ANIL 2024 (loyer ✓ ou ~). Exclut les loyers estimés (*)",
        )

    _nb_resultats = 20  # fixé à 20, plus pertinent qu'un filtre

    st.markdown("**🎯 Qualité de vie minimale (scores /100)**")
    _radar_cols = st.columns(6)
    _radar_filtres = {}
    _radar_labels = [
        ("Transport", "transport_score", "🚌"),
        ("Éducation", "education_score", "🎓"),
        ("Santé", "health_score", "🏥"),
        ("Services", "services_score", "🛒"),
        ("Espaces verts", "green_score", "🌳"),
        ("Réseau mobile", "network_score", "📶"),
    ]
    for col, (label, col_name, icon) in zip(_radar_cols, _radar_labels):
        with col:
            _radar_filtres[col_name] = st.slider(
                f"{icon} {label}", min_value=0, max_value=100, value=0, step=5,
                help=f"Afficher uniquement les communes avec un score {label} ≥ cette valeur",
            )

# Application des filtres
if not _pool.empty:
    _mask = (
        (_pool["cashflow_net_fiscal"] >= _cf_filter_min) &
        (_pool["rendement_net_fiscal"] >= _rdt_filter_min) &
        (_pool["prix_bien_possible"].between(*_prix_range)) &
        (_pool["_risque_vacance"].isin(_risque_niveaux))
    )
    if _only_positive_cf:
        _mask = _mask & (_pool["cashflow_net_fiscal"] >= 0)
    if _only_anil:
        _mask = _mask & (_pool["loyer_m2_app"].fillna(0) > 0)
    # Filtres radar qualité de vie
    for _col_name, _min_val in _radar_filtres.items():
        if _min_val > 0 and _col_name in _pool.columns:
            _mask = _mask & (_pool[_col_name].fillna(0) >= _min_val)
    _pool = _pool[_mask]

if _pool.empty:
    st.warning("Aucune commune trouvée avec ces filtres. Essayez d'élargir les critères.")
    top = pd.DataFrame()
else:
    # ── Scoring réaliste investisseur ─────────────────────────────────────────
    # 1. Cash-flow ajusté vacance : on déduit les mois vides estimés
    _pool["_taux_vacance"] = _pool.apply(
        lambda r: calcul_tension_locative(r.to_dict())["taux_vacance"], axis=1
    )
    # CF net fiscal ajusté = CF net fiscal × (1 − taux_vacance)
    # Le loyer manquant pendant la vacance s'applique sur le revenu locatif
    _pool["_cf_net_ajuste"] = (
        _pool["cashflow_net_fiscal"] -
        _pool["loyer_estime"] * _pool["_taux_vacance"]
    )
    # Rendement net ajusté vacance = rendement_net × (1 − taux_vacance)
    _pool["_rdt_net_ajuste"] = _pool["rendement_net_fiscal"] * (1 - _pool["_taux_vacance"])

    # 2. Normalisation percentile (0→100) des 3 composantes du score
    def _pct_rank(s):
        return s.rank(method="average", na_option="keep", pct=True).fillna(0.5) * 100

    _pool["_score_cf"]   = _pct_rank(_pool["_cf_net_ajuste"])    # 40% — cash-flow réel après vacance
    _pool["_score_rdt"]  = _pct_rank(_pool["_rdt_net_ajuste"])   # 30% — rendement net après vacance
    _pool["_score_qdv"]  = _pct_rank(_pool["critere_score"])     # 30% — qualité de vie

    _pool["score_final"] = (
        _pool["_score_cf"]  * 0.40 +
        _pool["_score_rdt"] * 0.30 +
        _pool["_score_qdv"] * 0.30
    )

    top = _pool.sort_values("score_final", ascending=False).head(_nb_resultats)

    # Score investisseur /10 visible dans le tableau
    s_min, s_max = _pool["score_final"].min(), _pool["score_final"].max()
    s_range = s_max - s_min if s_max != s_min else 1
    top = top.copy()
    top["_score_10"] = ((top["score_final"] - s_min) / s_range * 9 + 1).round(1)

    # Vacance locative par commune (label pour affichage)
    top["_vacance_label"] = top.apply(
        lambda r: calcul_tension_locative(r.to_dict())["label"], axis=1
    )

    # Ordre investisseur : ce qui compte le plus en premier
    # Commune avec code département
    top = top.copy()
    top["_commune_dept"] = top.apply(
        lambda r: f"{r['nom_commune']} ({r.get('code_departement', '')})", axis=1
    )

    ranking_columns = [
        "_score_10",
        "_commune_dept",
        "cashflow_net_fiscal",
        "cashflow_mensuel",
        "prix_bien_possible",
        "loyer_estime",
        "loyer_m2_app",
        "nb_annonces_app",
        "rendement_net_fiscal",
        "rendement_brut",
        "_vacance_label",
        "avg_price_m2",
        "annual_price_growth",
        "impot_annuel",
        "transaction_count",
    ]
    if PREDICTION_YEAR and "predicted_avg_price_m2" in top.columns:
        ranking_columns.insert(ranking_columns.index("avg_price_m2") + 1, "predicted_avg_price_m2")

    # Colonnes absentes selon la source (démo/API vs pipeline complète) : NaN,
    # les formateurs ci-dessous affichent alors "N/A" / "pas de données".
    for _col in ranking_columns:
        if _col not in top.columns:
            top[_col] = float("nan")

    top_display = top[ranking_columns].rename(columns={
        "_score_10":            "Score",
        "_commune_dept":        "Commune",
        "cashflow_net_fiscal":  "Cash-flow net/mois",
        "cashflow_mensuel":     "Cash-flow brut/mois",
        "prix_bien_possible":   f"Prix bien ({surface}m²)",
        "loyer_estime":         "Loyer/mois",
        "loyer_m2_app":         "_loyer_source",
        "nb_annonces_app":      "_nb_annonces",
        "rendement_net_fiscal": "Rendement net",
        "rendement_brut":       "Rendement brut",
        "_vacance_label":       "Vacance locative",
        "avg_price_m2":         "Prix/m²",
        "predicted_avg_price_m2": f"Prix estimé {PREDICTION_YEAR} (IA)",
        "annual_price_growth":  "Évol. prix/an",
        "impot_annuel":         "Impôt/an",
        "transaction_count":    "Nb ventes",
    }).copy()

    top_display["Score"]                 = top_display["Score"].apply(
        lambda x: f"⭐ {int(x)}/10" if x == int(x) else f"⭐ {x:.1f}/10"
    )
    top_display["Cash-flow net/mois"]    = top_display["Cash-flow net/mois"].apply(lambda x: f"{x:+.0f} €")
    top_display["Cash-flow brut/mois"]   = top_display["Cash-flow brut/mois"].apply(lambda x: f"{x:+.0f} €")
    top_display[f"Prix bien ({surface}m²)"] = top_display[f"Prix bien ({surface}m²)"].apply(lambda x: f"{x:,.0f} €".replace(",", " "))

    # Loyer : affiche le montant + indique la source
    def _fmt_loyer(row):
        loyer = row["Loyer/mois"]
        has_anil = pd.notna(row["_loyer_source"]) and row["_loyer_source"] > 0
        nb = row["_nb_annonces"]
        if has_anil and pd.notna(nb) and nb >= 5:
            return f"{loyer:.0f} € ✓"      # données ANIL fiables
        elif has_anil:
            return f"{loyer:.0f} € ~"      # ANIL mais peu d'annonces
        else:
            return f"{loyer:.0f} € *"      # estimation par rendement

    top_display["Loyer/mois"] = top_display.apply(_fmt_loyer, axis=1)

    # Marché locatif : toujours afficher quelque chose d'utile
    def _fmt_marche(row):
        nb = row["_nb_annonces"]
        has_anil = pd.notna(row["_loyer_source"]) and row["_loyer_source"] > 0
        if pd.notna(nb) and nb >= 30:
            return f"{int(nb)} annonces 🔥"
        elif pd.notna(nb) and nb >= 5:
            return f"{int(nb)} annonces"
        elif pd.notna(nb) and nb > 0:
            return f"{int(nb)} annonce(s) — loyer estimé"
        elif has_anil:
            return "< 5 annonces — loyer estimé"
        else:
            return "Pas de données ANIL — loyer calculé"

    top_display["Marché locatif"] = top_display.apply(_fmt_marche, axis=1)
    top_display = top_display.drop(columns=["_loyer_source", "_nb_annonces"])
    top_display["Rendement net"]         = top_display["Rendement net"].apply(
        lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A"
    )
    top_display["Rendement brut"]        = top_display["Rendement brut"].apply(
        lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A"
    )
    top_display["Prix/m²"]              = top_display["Prix/m²"].apply(lambda x: f"{x:,.0f} €".replace(",", " "))
    if PREDICTION_YEAR and f"Prix estimé {PREDICTION_YEAR} (IA)" in top_display.columns:
        top_display[f"Prix estimé {PREDICTION_YEAR} (IA)"] = top_display[f"Prix estimé {PREDICTION_YEAR} (IA)"].apply(
            lambda x: f"{x:,.0f} €".replace(",", " ") if pd.notna(x) else "N/A"
        )
    top_display["Évol. prix/an"]        = top_display["Évol. prix/an"].apply(
        lambda x: "N/A" if not pd.notna(x) or abs(x) > 0.20
        else (f"▲ +{x*100:.1f}%" if x > 0 else f"▼ {x*100:.1f}%")
    )
    top_display["Impôt/an"]             = top_display["Impôt/an"].apply(lambda x: f"{x:,.0f} €".replace(",", " "))
    top_display["Nb ventes"]            = top_display["Nb ventes"].apply(lambda x: int(x) if pd.notna(x) else 0)

    # Encadré "Meilleure opportunité" — commune #1 du classement
    _best = top.iloc[0]
    _best_cf = _best["cashflow_net_fiscal"]
    _best_rdt = _best["rendement_net_fiscal"]
    _best_vacance = calcul_tension_locative(_best.to_dict())
    _best_prix_fmt = f"{int(_best['prix_bien_possible']):,}".replace(',', ' ')
    _best_score = top.iloc[0]["_score_10"]
    _cf_color = "#43A047" if _best_cf >= 0 else "#E53935"
    _vacance_color = _best_vacance["couleur"]
    st.markdown(
        f'<div style="background:#1B2B1B;border:1px solid #43A047;border-radius:8px;padding:12px 20px;margin-bottom:12px">'
        f'<b style="color:#A5D6A7">🏆 Meilleure opportunité selon votre profil :</b> '
        f'<b style="color:white;font-size:1.1em">{_best["nom_commune"]}</b> '
        f'({_best.get("code_departement", "")})'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'<span style="color:{_cf_color}"><b>Cash-flow : {_best_cf:+.0f} €/mois</b></span>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'<span style="color:#90CAF9">Rendement net : <b>{_best_rdt:.1f}%</b></span>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'<span style="color:{_vacance_color}">Vacance : <b>{_best_vacance["label"]}</b></span>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'<span style="color:#FFF9C4">Prix : <b>{_best_prix_fmt} €</b></span>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;⭐ <b>{"" + str(int(_best_score)) if _best_score == int(_best_score) else f"{_best_score:.1f}"}/10</b>'
        f'<br><small style="color:#81C784">👇 Cliquez cette ligne dans le tableau pour lancer la simulation 20 ans</small>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.caption("⭐ Score = 40% cash-flow net (vacance déduite) + 30% rendement net (vacance déduite) + 30% qualité de vie · Cliquez une ligne pour simuler sur 20 ans")
    selection = st.dataframe(
        top_display, hide_index=True, use_container_width=True,
        on_select="rerun", selection_mode="multi-row",
        column_config={
            "Score": st.column_config.TextColumn(
                "Score",
                help="⭐ Note globale /10 calculée sur le cash-flow net et la qualité de vie (transports, écoles, santé, commerces). Plus c'est élevé, meilleur est l'investissement.",
            ),
            "Vacance locative": st.column_config.TextColumn(
                "Vacance locative",
                help="🏘️ Risque que le bien reste vide. Marché dynamique = facile à louer. Marché inexistant = personne ne cherche à louer ici, risque très élevé.",
            ),
            "Cash-flow net/mois": st.column_config.TextColumn(
                "Cash-flow net/mois",
                help="💰 Ce qui reste dans votre poche chaque mois après avoir tout payé : crédit + charges + taxe foncière + copropriété + impôts. C'est le vrai indicateur de rentabilité.",
            ),
            "Cash-flow brut/mois": st.column_config.TextColumn(
                "Cash-flow brut/mois",
                help="📊 Loyer − mensualité crédit − charges. Avant impôts. Utile pour comparer rapidement les communes entre elles.",
            ),
            f"Prix bien ({surface}m²)": st.column_config.TextColumn(
                f"Prix bien ({surface}m²)",
                help=f"🏠 Prix d'achat estimé pour {surface}m² dans cette commune (prix/m² DVF × surface). Vérifie avec les annonces réelles.",
            ),
            "Loyer/mois": st.column_config.TextColumn(
                "Loyer/mois",
                help="🔑 Loyer mensuel estimé. ✓ = données ANIL 2024 fiables (≥5 annonces). ~ = ANIL disponible mais peu d'annonces. * = aucune donnée ANIL : loyer calculé par rendement moyen du marché (moins précis, vérifiez sur SeLoger).",
            ),
            "Rendement net": st.column_config.TextColumn(
                "Rendement net",
                help="📈 (Loyers annuels − charges − impôts) / Prix d'achat. Le rendement réel après fiscalité. Visez > 5% pour un bon investissement.",
            ),
            "Rendement brut": st.column_config.TextColumn(
                "Rendement brut",
                help="📉 Loyers annuels / Prix d'achat, sans déduire les charges ni les impôts. Indicateur rapide — toujours plus élevé que le net.",
            ),
            "Marché locatif": st.column_config.TextColumn(
                "Marché locatif",
                help="🏘️ Nombre d'annonces de location recensées par l'ANIL sur cette commune. 🔥 = marché très actif (≥30 annonces). Quand il n'y a pas de données ANIL, le loyer est calculé par estimation — vérifiez sur SeLoger ou LeBonCoin avant d'investir.",
            ),
            "Prix/m²": st.column_config.TextColumn(
                "Prix/m²",
                help="🔢 Prix médian au m² issu des Demandes de Valeurs Foncières (DVF) — transactions immobilières officielles enregistrées par l'État.",
            ),
            "Impôt/an": st.column_config.TextColumn(
                "Impôt/an",
                help="🧾 Impôt annuel estimé selon votre régime fiscal (LMNP réel, micro BIC...). En LMNP réel avec amortissement, il est souvent proche de 0€ les 10 premières années.",
            ),
            "Évol. prix/an": st.column_config.TextColumn(
                "Évol. prix/an",
                help="📅 Évolution annuelle du prix au m² (DVF). ▲ = marché qui prend de la valeur. N/A = données insuffisantes ou valeur aberrante (> ±20%/an).",
            ),
            "Nb ventes": st.column_config.NumberColumn(
                "Nb ventes",
                help="✅ Nombre de transactions DVF sur cette commune. < 10 ventes = prix peu fiable. > 30 ventes = prix solide.",
                format="%d ventes",
            ),
        },
    )

    # Radar — 1 ou 2 communes selon la sélection
    selected_rows = selection.selection.get("rows", []) if selection else []

    if len(selected_rows) == 2:
        # Comparaison côte à côte
        row_a = top.iloc[selected_rows[0]]
        row_b = top.iloc[selected_rows[1]]
        with col_radar:
            st.markdown("**Comparaison qualité de vie**")
            fig_cmp = go.Figure()
            for row, color, dash in [(row_a, "#42A5F5", "solid"), (row_b, "#FF7043", "dot")]:
                labels = list(CRITERIA_COLUMNS.keys())
                values = [float(row.get(col, 0)) for col in CRITERIA_COLUMNS.values()]
                values_c = values + [values[0]]
                labels_c = labels + [labels[0]]
                _counts_detail = {
                    "Espaces verts":  f"{int(row.get('park_count', 0))} parcs",
                    "Transport":      f"{int(row.get('bus_stop_count', row.get('transport_count', 0)))} arrêts",
                    "Réseau mobile":  "4G/5G",
                    "Services":       f"{int(row.get('supermarket_count', 0))} commerces",
                    "Éducation":      f"{int(row.get('school_count', 0))} écoles",
                    "Santé":          f"{int(row.get('hospital_count', 0))} hôpitaux",
                    "Investissement": "potentiel",
                    "Accessibilité":  "prix/m²",
                }
                hover = [f"<b>{lbl}</b><br>{row['nom_commune']} : {v:.0f}/100<br>{_counts_detail.get(lbl,'')}"
                         for lbl, v in zip(labels, values)]
                fig_cmp.add_trace(go.Scatterpolar(
                    r=values_c, theta=labels_c,
                    fill="toself", name=row["nom_commune"],
                    line={"color": color, "dash": dash},
                    fillcolor=color.replace(")", ",0.15)").replace("rgb", "rgba") if "rgb" in color else color + "26",
                    hovertemplate="%{customdata}<extra></extra>",
                    customdata=hover + [hover[0]],
                ))
            fig_cmp.update_layout(
                polar={"radialaxis": {"visible": True, "range": [0, 100],
                                      "tickvals": [25, 50, 75, 100],
                                      "ticktext": ["25%", "50%", "75%", "top"]}},
                showlegend=True,
                legend={"orientation": "h", "y": -0.15},
                height=380,
                margin={"l": 30, "r": 30, "t": 20, "b": 40},
            )
            st.plotly_chart(fig_cmp, use_container_width=True, key="radar_top10")

            # Tableau comparatif chiffres clés
            st.markdown("**Comparaison chiffrée**")
            cmp_data = {
                "Indicateur": ["Cash-flow net/mois", "Loyer estimé", "Prix du bien", "Rendement net", "Rendement brut", "Impôt/an"],
                row_a["nom_commune"]: [
                    f"{row_a['cashflow_net_fiscal']:+.0f} €",
                    f"{row_a['loyer_estime']:.0f} €",
                    f"{row_a['prix_bien_possible']:,.0f} €".replace(",", " "),
                    f"{row_a['rendement_net_fiscal']:.1f}%",
                    f"{row_a['rendement_brut']:.1f}%",
                    f"{row_a['impot_annuel']:,.0f} €".replace(",", " "),
                ],
                row_b["nom_commune"]: [
                    f"{row_b['cashflow_net_fiscal']:+.0f} €",
                    f"{row_b['loyer_estime']:.0f} €",
                    f"{row_b['prix_bien_possible']:,.0f} €".replace(",", " "),
                    f"{row_b['rendement_net_fiscal']:.1f}%",
                    f"{row_b['rendement_brut']:.1f}%",
                    f"{row_b['impot_annuel']:,.0f} €".replace(",", " "),
                ],
            }
            st.dataframe(pd.DataFrame(cmp_data), hide_index=True, use_container_width=True)

    else:
        # Radar simple (1 commune, par défaut la meilleure)
        radar_idx = selected_rows[0] if selected_rows else 0
        radar_row = top.iloc[radar_idx]
        radar_commune = radar_row["nom_commune"]
        with col_radar:
            st.markdown("**Profil qualité de vie**")
            st.markdown(f"📍 *{radar_commune}*")
            st.caption("💡 Pour comparer plusieurs communes : section ⚖️ Comparateur en bas de page")
            st.plotly_chart(build_radar(radar_row, radar_commune), use_container_width=True, key="radar_top10")

st.divider()

# ── SIMULATION 20 ANS ──────────────────────────────────────────────────────────
st.subheader("Étape 3 — Plan d'investissement sur 20 ans")

# Commune de référence : commune cherchée > meilleure du département > meilleure du top
if selected_search and selected_search in df_all["nom_commune"].values:
    sim_row = df_all[df_all["nom_commune"] == selected_search].iloc[0]
    sim_commune = selected_search
elif selected_dept:
    dept_top = df_all[df_all["code_departement"] == selected_dept].sort_values("cashflow_mensuel", ascending=False)
    if not dept_top.empty:
        sim_row = dept_top.iloc[0]
        sim_commune = sim_row["nom_commune"]
    elif not top.empty:
        sim_row = top.iloc[0]
        sim_commune = sim_row["nom_commune"]
    else:
        sim_row = df_all.sort_values("cashflow_mensuel", ascending=False).iloc[0]
        sim_commune = sim_row["nom_commune"]
elif not top.empty:
    sim_row = top.iloc[0]
    sim_commune = sim_row["nom_commune"]
else:
    sim_row = df_all.sort_values("cashflow_mensuel", ascending=False).iloc[0]
    sim_commune = sim_row["nom_commune"]

sim_col1, sim_col2 = st.columns([1, 1.6])

with sim_col1:
    st.markdown(f"#### Paramètres — *{sim_commune}*")

    _sim_prix_val = max(10_000, int(sim_row["prix_bien_possible"]))
    sim_prix = st.number_input(
        "Prix du bien (€)", min_value=10_000, max_value=1_000_000,
        value=_sim_prix_val, step=5_000,
    )
    sim_loyer = st.number_input(
        "Loyer mensuel estimé (€)", min_value=200, max_value=5_000,
        value=int(sim_row["loyer_estime"]), step=25,
    )
    sim_appreciation = st.slider(
        "Appréciation annuelle du bien (%)", min_value=-2.0, max_value=5.0,
        value=float(round(sim_row.get("annual_price_growth", 0.01) * 100
                          if pd.notna(sim_row.get("annual_price_growth")) else 1.0, 1)),
        step=0.1,
        help="YoY de la commune — modifiable",
    )
    _sim_charges_default = int(
        sim_row.get("charges_tot_annuelles", charges_copro_annuelles + 700)
        if pd.notna(sim_row.get("charges_tot_annuelles", None))
        else charges_copro_annuelles + 700
    )
    sim_charges = st.number_input(
        "Charges annuelles totales (€)", min_value=0, max_value=15_000,
        value=_sim_charges_default, step=100,
    )
    duree_simulation = st.select_slider(
        "Durée de la simulation",
        options=[10, 15, 20, 25, 30],
        value=20,
        format_func=lambda x: f"{x} ans",
        help="Horizon de votre investissement. La banque vous demandera souvent un plan sur 20-25 ans.",
    )
    st.markdown("#### Objectif prochain achat")
    apport_2eme = st.number_input(
        "Apport nécessaire pour le 2ème bien (€)",
        min_value=5_000, max_value=200_000, value=20_000, step=1_000,
        help="Quand votre cash-flow cumulé atteint ce montant, vous pouvez solliciter un 2ème crédit",
    )

    st.markdown("#### Risque de vacance locative")
    _tension = calcul_tension_locative(sim_row.to_dict())
    _couleur_badge = _tension["couleur"]
    _label_badge = _tension["label"]
    _mois_vides = _tension["mois_vacance"]
    st.markdown(
        f'<div style="background:{_couleur_badge}22;border-left:4px solid {_couleur_badge};'
        f'padding:8px 12px;border-radius:4px;margin-bottom:8px">'
        f'<b style="color:{_couleur_badge}">{"🟢" if _tension["niveau"]==0 else "🟡" if _tension["niveau"]==1 else "🟠" if _tension["niveau"]==2 else "🔴"} {_label_badge}</b><br>'
        f'<small>{_tension["detail"]}<br>Vacance estimée : <b>{_mois_vides:.1f} mois/an</b></small></div>',
        unsafe_allow_html=True,
    )
    taux_vacance_pct = st.slider(
        "Taux de vacance locative (%)",
        min_value=0, max_value=60,
        value=int(_tension["taux_vacance"] * 100),
        step=1,
        help="% du temps où le bien est vide (pas de loyer encaissé). "
             "Standard : 8% (1 mois/an). Petite commune : 30-50%.",
        format="%d%%",
    )
    taux_vacance = taux_vacance_pct / 100

# Apport réel sur le bien = apport - frais de notaire de ce bien
_sim_frais_notaire = sim_prix * _apport_frais_notaire_ratio
_sim_apport_sur_bien = max(apport - _sim_frais_notaire, 0)

sim = simulate_20ans(
    prix_bien=sim_prix,
    apport=_sim_apport_sur_bien,
    taux=taux_base,
    taux_assur_pct=taux_assur_pct,
    duree=duree,
    loyer_mensuel=sim_loyer,
    charges_annuelles=sim_charges,
    appreciation_annuelle=sim_appreciation,
    apport_2eme=apport_2eme,
    salaire_net_mensuel=salaire_net,
    taux_global_fiscal=taux_global_fiscal,
    regime_fiscal=regime_fiscal,
    meuble=meuble,
    horizon=duree_simulation,
    taux_vacance=taux_vacance,
)

with sim_col2:
    st.markdown("#### Résultats")

    # Résumé coût total avec frais de notaire
    _cout_total = sim_prix + _sim_frais_notaire
    st.caption(
        f"💼 Coût total d'acquisition : **{int(_cout_total):,} €** "
        f"(bien {int(sim_prix):,} € + notaire {int(_sim_frais_notaire):,} € à {frais_notaire_pct:.1f}%) "
        f"· Taux crédit : **{taux_base:.2f}%** · Apport sur le bien : **{int(_sim_apport_sur_bien):,} €**"
        .replace(",", " ")
    )

    cf_mensuel = sim["cashflow_mensuel"]
    nb_achats = len(sim["achats"])
    r1, r2, r3, r4 = st.columns(4)
    _vacance_label = f"vacance {taux_vacance_pct}% incluse"
    r1.metric(
        "Cash-flow net/mois (bien 1)",
        f"{cf_mensuel:+.0f} €",
        delta=f"après impôts + {_vacance_label} ✅" if cf_mensuel >= 0 else f"effort mensuel ({_vacance_label}) ⚠️",
        delta_color="normal" if cf_mensuel >= 0 else "inverse",
        help=f"Loyer × (1 − {taux_vacance_pct}% vacance) − crédit − charges − impôts",
    )
    r2.metric(f"Patrimoine net à {duree_simulation} ans", format_eur(sim["patrimoine_net"][-1]))
    r3.metric(f"Biens acquis en {duree_simulation} ans", f"{1 + nb_achats} bien{'s' if nb_achats else ''}",
              delta=f"+{nb_achats} via cash-flow" if nb_achats else "1 seul bien", delta_color="off")
    taux_endt_initial = sim["taux_endettement"][0] if sim["taux_endettement"] else 0
    r4.metric(
        "Taux d'endettement an 1",
        f"{taux_endt_initial:.1f}%",
        delta="✅ < 35%" if taux_endt_initial <= 35 else "⚠️ > 35%",
        delta_color="normal" if taux_endt_initial <= 35 else "inverse",
        help="Méthode classique HCSF : total crédits / (salaire brut + 70% loyers)",
    )

    if nb_achats > 0:
        st.success(
            f"🚀 Stratégie BRRRR sur 20 ans : **{1 + nb_achats} biens** acquis (impôts + règle bancaire inclus). "
            f"Le 2ème en année **{sim['achats'][0]['annee']}**"
            + (f", le {1 + nb_achats}ème en année **{sim['achats'][-1]['annee']}**." if nb_achats > 1 else ".")
        )
    elif sim["blocages_bancaires"]:
        b = sim["blocages_bancaires"][0]
        st.warning(
            f"🏦 La banque bloque le {b['nb_biens'] + 1}ème achat en année **{b['annee']}** "
            f"— taux d'endettement trop élevé ({b['taux_endt']}% > 35%). "
            f"Augmentez votre salaire ou réduisez le prix du bien."
        )
    elif cf_mensuel < 0:
        st.warning(
            f"⚠️ Effort de **{abs(cf_mensuel):.0f} €/mois** (après impôts). "
            f"Le cash-flow ne s'accumule pas assez pour financer un 2ème achat."
        )

    # Graphe principal : patrimoine 20 ans
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sim["annees"], y=sim["valeur_bien"],
        name="Valeur totale du parc", mode="lines",
        line={"color": "#42A5F5", "width": 2},
        fill="tozeroy", fillcolor="rgba(66,165,245,0.1)",
    ))
    fig.add_trace(go.Scatter(
        x=sim["annees"], y=sim["dette_restante"],
        name="Dette totale", mode="lines",
        line={"color": "#EF5350", "width": 2, "dash": "dash"},
    ))
    fig.add_trace(go.Scatter(
        x=sim["annees"], y=sim["patrimoine_net"],
        name="Patrimoine net", mode="lines+markers",
        line={"color": "#66BB6A", "width": 3},
        marker={"size": 6},
    ))
    fig.add_trace(go.Bar(
        x=sim["annees"], y=sim["cashflow_mensuel_brut"],
        name="Cash-flow mensuel brut (parc)", marker_color="rgba(255,167,38,0.6)",
        yaxis="y2",
    ))

    # Ligne verticale pour chaque achat
    colors_achats = ["gold", "orange", "tomato", "violet", "cyan"]
    for i, achat in enumerate(sim["achats"]):
        fig.add_vline(
            x=achat["annee"], line_color=colors_achats[i % len(colors_achats)],
            line_width=2, line_dash="dot",
            annotation_text=f"🏠 Bien {achat['num_bien']} (an {achat['annee']})",
            annotation_position="top left" if i % 2 == 0 else "top right",
            annotation_font_color=colors_achats[i % len(colors_achats)],
        )

    fig.update_layout(
        xaxis_title="Années",
        yaxis={"title": "Montant (€)", "side": "left"},
        yaxis2={"title": "Cash-flow mensuel (€)", "overlaying": "y", "side": "right", "showgrid": False},
        height=420,
        legend={"orientation": "h", "y": -0.2},
        margin={"l": 0, "r": 0, "t": 10, "b": 60},
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key="chart_simulation_20ans")

    # Tableau récapitulatif du plan d'achat
    st.markdown("#### Plan d'acquisition sur 20 ans")
    taux_endt_an = {a: sim["taux_endettement"][a - 1] for a in sim["annees"]}
    plan_rows = [{
        "Bien": "🏠 Bien n°1",
        "Année": "Maintenant",
        "Prix": format_eur(sim_prix),
        "Cash-flow net/mois": f"{cf_mensuel:+.0f} €",
        "Taux endettement": f"{taux_endt_an.get(1, 0):.1f}%",
        "Accord banque": "✅" if taux_endt_an.get(1, 0) <= 35 else "⚠️",
    }]
    for achat in sim["achats"]:
        te = taux_endt_an.get(achat["annee"], 0)
        plan_rows.append({
            "Bien": f"🏠 Bien n°{achat['num_bien']}",
            "Année": f"Année {achat['annee']}",
            "Prix": format_eur(achat["prix"]),
            "Cash-flow net/mois": f"{cf_mensuel:+.0f} €",
            "Taux endettement": f"{te:.1f}%",
            "Accord banque": "✅" if te <= 35 else "⚠️ > 35%",
        })
    st.dataframe(pd.DataFrame(plan_rows), hide_index=True, use_container_width=True)
    st.caption(
        "💡 **Taux d'endettement** calculé selon la méthode HCSF : "
        "total crédits / (salaire brut + 70% loyers) ≤ 35%. "
        "La banque compte vos loyers à 70% seulement (pas 100%) pour couvrir la vacance locative."
    )

st.divider()

# ── EXPORT PDF ────────────────────────────────────────────────────────────────
st.subheader("📄 Rapport d'investissement")
st.caption("Générez un rapport professionnel à présenter à votre banque ou conseiller.")

if st.button("📥 Générer mon rapport d'investissement", type="primary", use_container_width=False):
    from datetime import date as _date
    import base64, json

    _radar_fig = build_radar(sim_row, sim_commune)
    _sim_fig_html = ""

    # Build simulation chart HTML for embedding
    _sf = go.Figure()
    _sf.add_trace(go.Scatter(x=sim["annees"], y=sim["valeur_bien"], name="Valeur du parc",
        line={"color": "#42A5F5", "width": 2}, fill="tozeroy", fillcolor="rgba(66,165,245,0.08)"))
    _sf.add_trace(go.Scatter(x=sim["annees"], y=sim["dette_restante"], name="Dette totale",
        line={"color": "#EF5350", "width": 2, "dash": "dash"}))
    _sf.add_trace(go.Scatter(x=sim["annees"], y=sim["patrimoine_net"], name="Patrimoine net",
        line={"color": "#66BB6A", "width": 3}, marker={"size": 5}))
    for i, achat in enumerate(sim["achats"]):
        _sf.add_vline(x=achat["annee"], line_color="gold", line_width=1, line_dash="dot",
            annotation_text=f"Bien {achat['num_bien']}", annotation_font_color="gold")
    _sf.update_layout(height=350, margin={"l":0,"r":0,"t":10,"b":40}, hovermode="x unified",
        legend={"orientation":"h","y":-0.2},
        xaxis_title=f"Années (sur {duree_simulation} ans)", yaxis_title="Montant (€)")

    _radar_html = _radar_fig.to_html(include_plotlyjs=False, full_html=False, config={"displayModeBar": False})
    _sim_html   = _sf.to_html(include_plotlyjs=False, full_html=False, config={"displayModeBar": False})

    _plan_rows_html = "".join(
        f"<tr><td>{r['Bien']}</td><td>{r['Année']}</td><td>{r['Prix']}</td>"
        f"<td>{r['Cash-flow net/mois']}</td><td>{r['Taux endettement']}</td><td>{r['Accord banque']}</td></tr>"
        for r in plan_rows
    )

    _yoy = sim_row.get("annual_price_growth")
    _yoy_str = f"{_yoy*100:+.1f}%/an" if pd.notna(_yoy) else "N/A"
    _regime_court = regime_fiscal.split("(")[0].strip()

    html_report = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Rapport Investissement — {sim_commune}</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1a1a2e; background: #fff; padding: 32px; font-size: 13px; }}
  h1 {{ font-size: 22px; color: #1565C0; border-bottom: 3px solid #1565C0; padding-bottom: 8px; margin-bottom: 4px; }}
  h2 {{ font-size: 15px; color: #1565C0; margin: 20px 0 8px; border-left: 4px solid #42A5F5; padding-left: 10px; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }}
  .header-right {{ text-align: right; color: #666; font-size: 11px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }}
  .kpi {{ background: #f0f7ff; border-radius: 8px; padding: 12px; text-align: center; border: 1px solid #bbdefb; }}
  .kpi-value {{ font-size: 20px; font-weight: 700; color: #1565C0; }}
  .kpi-value.positive {{ color: #2e7d32; }}
  .kpi-value.negative {{ color: #c62828; }}
  .kpi-label {{ font-size: 10px; color: #555; margin-top: 4px; }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 16px 0; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 12px; }}
  th {{ background: #1565C0; color: white; padding: 7px 10px; text-align: left; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #e0e0e0; }}
  tr:nth-child(even) td {{ background: #f5f9ff; }}
  .disclaimer {{ font-size: 10px; color: #999; margin-top: 24px; padding-top: 12px; border-top: 1px solid #eee; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 10px; font-weight: 600; }}
  .badge-green {{ background: #e8f5e9; color: #2e7d32; }}
  .badge-blue {{ background: #e3f2fd; color: #1565C0; }}
  @media print {{
    body {{ padding: 16px; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🏦 Rapport d'investissement immobilier</h1>
    <div style="color:#555;margin-top:6px;">Commune analysée : <strong>{sim_commune}</strong> &nbsp;·&nbsp; Département {sim_row.get('code_departement','')} &nbsp;·&nbsp; {surface}m² · {'Meublé' if meuble else 'Nu'}</div>
  </div>
  <div class="header-right">
    Généré le {_date.today().strftime('%d/%m/%Y')}<br>
    <span style="color:#1565C0;font-weight:600;">HOMEPEDIA</span><br>
    Profil : {salaire_net:,} €/mois · Apport {apport:,} €<br>
    Régime : {_regime_court}
  </div>
</div>

<h2>Indicateurs clés</h2>
<div class="kpis">
  <div class="kpi">
    <div class="kpi-value {'positive' if sim['cashflow_mensuel'] >= 0 else 'negative'}">{sim['cashflow_mensuel']:+.0f} €</div>
    <div class="kpi-label">Cash-flow net/mois (après impôts)</div>
  </div>
  <div class="kpi">
    <div class="kpi-value">{sim_prix:,.0f} €</div>
    <div class="kpi-label">Prix d'achat ({surface}m²)</div>
  </div>
  <div class="kpi">
    <div class="kpi-value">{sim_loyer:,.0f} €</div>
    <div class="kpi-label">Loyer mensuel estimé</div>
  </div>
  <div class="kpi">
    <div class="kpi-value">{sim_row.get('rendement_net_fiscal', 0):.1f}%</div>
    <div class="kpi-label">Rendement net fiscal</div>
  </div>
  <div class="kpi">
    <div class="kpi-value">{sim['patrimoine_net'][-1]:,.0f} €</div>
    <div class="kpi-label">Patrimoine net à {duree_simulation} ans</div>
  </div>
  <div class="kpi">
    <div class="kpi-value">{1 + len(sim['achats'])}</div>
    <div class="kpi-label">Biens acquis sur {duree_simulation} ans</div>
  </div>
  <div class="kpi">
    <div class="kpi-value">{sim_row.get('avg_price_m2', 0):,.0f} €/m²</div>
    <div class="kpi-label">Prix marché (DVF)</div>
  </div>
  <div class="kpi">
    <div class="kpi-value">{_yoy_str}</div>
    <div class="kpi-label">Évolution prix</div>
  </div>
</div>

<h2>Financement</h2>
<table>
  <tr><th>Paramètre</th><th>Valeur</th><th>Paramètre</th><th>Valeur</th></tr>
  <tr><td>Prix du bien</td><td><strong>{sim_prix:,.0f} €</strong></td><td>Apport personnel</td><td><strong>{apport:,.0f} €</strong></td></tr>
  <tr><td>Montant emprunté</td><td><strong>{max(sim_prix - apport, 0):,.0f} €</strong></td><td>Durée du crédit</td><td><strong>{duree} ans</strong></td></tr>
  <tr><td>Mensualité crédit</td><td><strong>{sim['mensualite_totale']:,.0f} €/mois</strong></td><td>Taux d'endettement an 1</td><td><strong>{sim['taux_endettement'][0]:.1f}% {'✅' if sim['taux_endettement'][0] <= 35 else '⚠️'}</strong></td></tr>
  <tr><td>Charges annuelles</td><td>{sim_charges:,.0f} €/an</td><td>Régime fiscal</td><td>{_regime_court}</td></tr>
</table>

<div class="two-col">
  <div>
    <h2>Profil qualité de vie</h2>
    {_radar_html}
  </div>
  <div>
    <h2>Plan d'acquisition sur {duree_simulation} ans</h2>
    <table>
      <tr><th>Bien</th><th>Année</th><th>Prix</th><th>CF net/mois</th><th>Endettement</th><th>Banque</th></tr>
      {_plan_rows_html}
    </table>
    <br>
    <h2>Résumé à {duree_simulation} ans</h2>
    <table>
      <tr><th>Indicateur</th><th>Valeur</th></tr>
      <tr><td>Patrimoine net total</td><td><strong>{sim['patrimoine_net'][-1]:,.0f} €</strong></td></tr>
      <tr><td>Cash-flow cumulé</td><td>{sim['cashflow_cumule'][-1]:,.0f} €</td></tr>
      <tr><td>Valeur totale du parc</td><td>{sim['valeur_bien'][-1]:,.0f} €</td></tr>
      <tr><td>Dette totale restante</td><td>{sim['dette_restante'][-1]:,.0f} €</td></tr>
      <tr><td>Nombre de biens</td><td>{sim['nb_biens'][-1]} bien(s)</td></tr>
    </table>
  </div>
</div>

<h2>Évolution du patrimoine sur {duree_simulation} ans</h2>
{_sim_html}

<div class="disclaimer">
  <strong>Avertissement :</strong> Ce rapport est généré automatiquement par HOMEPEDIA à titre indicatif. Les estimations de loyer (ANIL 2024), de prix (DVF 2023), de fiscalité et de cash-flow sont des projections basées sur des hypothèses moyennes. Elles ne constituent pas un conseil en investissement. Consultez un conseiller en gestion de patrimoine (CGP) avant tout achat. Les performances passées ne préjugent pas des performances futures.
</div>

<div class="no-print" style="margin-top:20px;text-align:center;color:#888;font-size:11px;">
  💡 Pour sauvegarder en PDF : Fichier → Imprimer → Enregistrer en PDF (ou Ctrl+P)
</div>
</body>
</html>"""

    b64 = base64.b64encode(html_report.encode("utf-8")).decode()
    filename = f"rapport_investissement_{sim_commune.replace(' ','_')}_{_date.today()}.html"
    st.download_button(
        label="⬇️ Télécharger le rapport (HTML → imprimer en PDF)",
        data=html_report.encode("utf-8"),
        file_name=filename,
        mime="text/html",
        type="secondary",
    )
    st.info("💡 Une fois téléchargé, ouvrez le fichier dans Chrome et faites **Ctrl+P → Enregistrer en PDF** pour obtenir un PDF professionnel.")

st.divider()

# ── PROFIL DE LA COMMUNE ───────────────────────────────────────────────────────
st.subheader(f"Profil investissement — {sim_commune}")

prof_col1, prof_col2 = st.columns([1, 1])
with prof_col1:
    st.plotly_chart(build_radar(sim_row, sim_commune), use_container_width=True, key="radar_simulation")

with prof_col2:
    st.markdown("#### Indicateurs clés")
    kpi1, kpi2 = st.columns(2)
    kpi1.metric("Prix/m²", f"{sim_row['avg_price_m2']:.0f} €/m²")
    kpi2.metric("Score investissement", f"{sim_row.get('investment_potential_score', 0):.0f}/100")
    kpi3, kpi4 = st.columns(2)
    yoy = sim_row.get("annual_price_growth")
    kpi3.metric("Évolution prix (YoY)", f"{yoy*100:+.1f}%" if pd.notna(yoy) else "N/A")
    kpi4.metric("Rendement brut estimé", f"{rendement_brut_commune(sim_row['avg_price_m2']):.1f}%")
    kpi5, kpi6 = st.columns(2)
    kpi5.metric("Réseau mobile", f"{sim_row.get('network_score', 0):.0f}/100")
    kpi6.metric("Transport", f"{sim_row.get('transport_score', 0):.0f}/100")

    if PREDICTION_YEAR and pd.notna(sim_row.get("predicted_avg_price_m2")):
        kpi7, kpi8 = st.columns(2)
        kpi7.metric(
            f"Prix estimé {PREDICTION_YEAR} (IA)",
            f"{sim_row['predicted_avg_price_m2']:.0f} €/m²",
            delta=f"{sim_row['predicted_growth_pct']:+.1f}%",
            help="Prédiction RandomForest entraînée sur l'historique DVF (data_pipeline.ml.predict_prices).",
        )
        kpi8.metric("Croissance prédite", f"{sim_row['predicted_growth_pct']:+.1f}%")

    _lstats = load_listing_stats()
    if _lstats is not None and pd.notna(sim_row.get("avg_price_m2")):
        _lrow = _lstats[_lstats["code_commune"].astype(str) == str(sim_row.get("code_commune", ""))]
        if not _lrow.empty:
            _prix_annonces = float(_lrow.iloc[0]["avg_listing_price_m2"])
            _ecart = (_prix_annonces - sim_row["avg_price_m2"]) / sim_row["avg_price_m2"] * 100
            kpi9, kpi10 = st.columns(2)
            kpi9.metric(
                "Prix annonces (marché affiché)", f"{_prix_annonces:.0f} €/m²",
                help="Moyenne des annonces scrapées (silver_listings), pondérée par le nombre d'annonces.",
            )
            kpi10.metric(
                "Écart annonces vs ventes DVF", f"{_ecart:+.0f}%",
                help="Écart entre le prix affiché sur les portails et les ventes réellement actées (DVF).",
            )

    st.markdown("#### Annonces disponibles")
    code_commune = str(sim_row.get("code_commune", ""))
    dept = str(sim_row.get("code_departement", ""))
    if dept.startswith("97"):
        fallback_postal = dept.ljust(5, "0")  # DOM: "971" -> "97100"
    elif dept.upper() in ("2A", "2B"):
        fallback_postal = "20000"  # Corse: postal codes start with 20
    else:
        fallback_postal = dept.zfill(2) + "000"
    postal_code = str(sim_row.get("code_postal", fallback_postal))
    import re as _re
    _slug = _re.sub(r"[^a-z0-9]+", "-", sim_commune.lower().strip()).strip("-")

    # URLs fallback (liens directs)
    # LeBonCoin filtre par ville__code_insee (format interne LBC)
    _lbc_location_id = f"{sim_commune.lower().replace(' ', '-')}__{code_commune}"
    _urls_achat = {
        "SeLoger":   f"https://www.seloger.com/list.htm?ci={code_commune}&idtt=2&idtypebien=1,2&tri=d_dt_crea",
        "BienIci":   f"https://www.bienici.com/recherche/achat/ville-{_slug}_{code_commune}?typesBiens=flat,house",
        "LeBonCoin": f"https://www.leboncoin.fr/recherche?category=9&locations={_lbc_location_id}",
    }
    _urls_location = {
        "SeLoger":   f"https://www.seloger.com/list.htm?ci={code_commune}&idtt=1&idtypebien=1,2&tri=d_dt_crea",
        "BienIci":   f"https://www.bienici.com/recherche/location/ville-{_slug}_{code_commune}?typesBiens=flat,house",
        "LeBonCoin": f"https://www.leboncoin.fr/recherche?category=10&locations={_lbc_location_id}",
    }

    loyer_ref = sim_row.get("loyer_estime", 0)
    has_anil = pd.notna(sim_row.get("loyer_m2_app")) and sim_row.get("loyer_m2_app", 0) > 0

    if "listings" not in st.session_state:
        st.session_state.listings = None
    if "listings_commune" not in st.session_state:
        st.session_state.listings_commune = None
    if "listings_mode" not in st.session_state:
        st.session_state.listings_mode = None

    # Le dossier du script n'est pas toujours sur sys.path selon le lanceur
    # (streamlit run vs AppTest) : on l'ajoute explicitement.
    import sys
    _script_dir = str(Path(__file__).resolve().parent)
    if _script_dir not in sys.path:
        sys.path.insert(0, _script_dir)
    from scraper_service import fetch_listings

    tab_achat, tab_location = st.tabs(["🏠 Acheter", "🔑 Louer (vérifier le loyer)"])

    with tab_achat:
        col_btn, col_links = st.columns([1, 2])
        with col_btn:
            if st.button("🔍 Charger les annonces BienIci", type="primary", use_container_width=True,
                         help="Scraping en temps réel via navigateur headless (~15s)"):
                with st.spinner(f"Scraping BienIci pour {sim_commune}... (~15s)"):
                    st.session_state.listings = fetch_listings(
                        code_commune=code_commune, nom_commune=sim_commune,
                        postal_code=postal_code, commune_slug=_slug, mode="achat",
                    )
                    st.session_state.listings_commune = sim_commune
                    st.session_state.listings_mode = "achat"
        with col_links:
            st.caption("Ou ouvrir directement :")
            icons = {"SeLoger": "🏠", "BienIci": "🔵", "LeBonCoin": "🟡"}
            link_cols = st.columns(3)
            for lc, (portail, url) in zip(link_cols, _urls_achat.items()):
                lc.link_button(f"{icons[portail]} {portail}", url, use_container_width=True)
        st.info(
            f"💡 Filtrez sur **{surface}m²** et un budget de "
            f"**{int(sim_row['prix_bien_possible']):,} €**.".replace(",", " ")
        )

    with tab_location:
        col_btn2, col_links2 = st.columns([1, 2])
        with col_btn2:
            if st.button("🔍 Charger les locations BienIci", use_container_width=True,
                         help="Scraping en temps réel via navigateur headless (~15s)"):
                with st.spinner(f"Scraping BienIci location pour {sim_commune}..."):
                    st.session_state.listings = fetch_listings(
                        code_commune=code_commune, nom_commune=sim_commune,
                        postal_code=postal_code, commune_slug=_slug, mode="location",
                    )
                    st.session_state.listings_commune = sim_commune
                    st.session_state.listings_mode = "location"
        with col_links2:
            st.caption("Ou ouvrir directement :")
            link_cols2 = st.columns(3)
            for lc, (portail, url) in zip(link_cols2, _urls_location.items()):
                lc.link_button(f"{icons[portail]} {portail}", url, use_container_width=True)
        if has_anil:
            st.success(
                f"✅ Loyer ANIL 2024 : **{loyer_ref:.0f} €/mois** "
                f"({sim_row.get('loyer_m2_app', 0):.1f} €/m²). Confirmez avec les annonces réelles."
            )
        else:
            st.warning(
                f"⚠️ Pas de données ANIL pour {sim_commune}. Loyer estimé : **{loyer_ref:.0f} €/mois**. "
                f"Vérifiez sur les portails ci-dessus."
            )

    # Affichage des résultats du scraping
    if (st.session_state.get("listings") is not None
            and st.session_state.get("listings_commune") == sim_commune):
        result = st.session_state.listings
        listings = result["listings"]
        sources_status = result["sources_status"]
        _mode_label = "achat" if st.session_state.listings_mode == "achat" else "location"

        st.markdown(f"**Résultats BienIci — {sim_commune}** ({len(listings)} annonces · {_mode_label})")

        for source, (status, message) in sources_status.items():
            if status == "ok":
                st.success(f"✅ **{source}** — {message}")
            elif status == "fallback":
                st.info(f"ℹ️ **{source}** — {message}")
            else:
                st.warning(f"⚠️ **{source}** — {message}")

        for listing in listings[:15]:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                with c1:
                    st.markdown(f"**🔵 BienIci** — {listing.get('title', 'Appartement')} à {listing.get('city', sim_commune)}")
                    if listing.get("url"):
                        st.markdown(f"[Voir l'annonce ↗]({listing['url']})")
                with c2:
                    price = listing.get("price")
                    st.metric("Prix", f"{price:,.0f} €".replace(",", " ") if price else "N/A")
                with c3:
                    surf = listing.get("surface_m2")
                    st.metric("Surface", f"{surf:.0f} m²" if surf else "N/A")
                with c4:
                    pm2 = listing.get("price_m2")
                    st.metric("Prix/m²", f"{pm2:,.0f} €".replace(",", " ") if pm2 else "N/A")

# ── COMMUNES SIMILAIRES (IA k-NN) ──────────────────────────────────────────────
st.markdown(f"#### 🤝 Communes similaires à {sim_commune} (IA)")
try:
    import sys as _sys
    if str(PROJECT_ROOT) not in _sys.path:
        _sys.path.insert(0, str(PROJECT_ROOT))
    from data_pipeline.ml.similar_communes import find_similar

    similar = find_similar(data, str(sim_row.get("code_commune", "")), top=5)
    if similar.empty:
        st.caption("Pas assez de données de scores pour calculer des communes similaires.")
    else:
        sim_cols = st.columns(len(similar))
        for col, (_, srow) in zip(sim_cols, similar.iterrows()):
            price = srow.get("avg_price_m2")
            col.metric(
                srow["nom_commune"],
                f"{price:.0f} €/m²" if pd.notna(price) else "—",
                delta=f"similarité {srow['similarity']:.0f}/100",
                delta_color="off",
            )
        st.caption(
            "Recommandation k-NN sur les vecteurs de scores territoriaux "
            "(transport, réseau, espaces verts, services, éducation, santé…) — "
            "data_pipeline.ml.similar_communes."
        )
except ImportError:
    st.caption("scikit-learn non installé — `pip install scikit-learn` pour activer les recommandations.")

# ── ANALYSE TEXTUELLE (NLP) ────────────────────────────────────────────────────
st.markdown(f"#### 💬 Analyse textuelle des annonces — {sim_commune}")
_nlp_path = DATA_LAKE / "nlp" / "text_analysis.parquet"
if not _nlp_path.exists():
    st.caption(
        "Pas d'analyse textuelle disponible — lancez le pipeline Kafka puis "
        "`python -m data_pipeline.nlp.analyze_listings_text`."
    )
else:
    _nlp = pd.read_parquet(_nlp_path)
    _row = _nlp[_nlp["code_commune"].astype(str) == str(sim_row.get("code_commune", ""))]
    if _row.empty:
        st.caption("Aucun texte collecté pour cette commune (lancez les scrapers Kafka dessus).")
    else:
        _row = _row.iloc[0]
        nlp_col1, nlp_col2 = st.columns([1, 2])
        with nlp_col1:
            _emoji = {"positif": "😊", "neutre": "😐", "négatif": "😟"}.get(_row["sentiment_label"], "😐")
            st.metric(
                "Sentiment des annonces",
                f"{_emoji} {_row['sentiment_label'].capitalize()}",
                delta=f"score {_row['sentiment_score']:+.2f}",
                delta_color="off",
                help="Score lexical français entre -1 et +1 calculé sur titres et descriptions "
                     "(data_pipeline.nlp.analyze_listings_text).",
            )
            st.metric("Textes analysés", f"{int(_row['n_texts'])} annonces")
        with nlp_col2:
            try:
                import json as _json
                from wordcloud import WordCloud
                _freq = _json.loads(_row["top_words"])
                if _freq:
                    _wc = WordCloud(width=640, height=280, background_color="white",
                                    colormap="viridis").generate_from_frequencies(_freq)
                    st.image(_wc.to_array(), use_container_width=True)
            except ImportError:
                st.caption("`pip install wordcloud` pour afficher le nuage de mots.")

# ── ÉVOLUTION DU PRIX (historique DVF + prédiction IA) ────────────────────────
_history = load_price_history()
if _history is not None:
    _hist_commune = _history[
        _history["code_commune"].astype(str) == str(sim_row.get("code_commune", ""))
    ].sort_values("annee")
    if len(_hist_commune) >= 2:
        st.markdown(f"#### 📈 Évolution du prix au m² — {sim_commune}")
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Scatter(
            x=_hist_commune["annee"], y=_hist_commune["avg_price_m2"],
            mode="lines+markers", name="Prix DVF constaté",
            line=dict(color="#1E88E5", width=3),
        ))
        if PREDICTION_YEAR and pd.notna(sim_row.get("predicted_avg_price_m2")):
            _last = _hist_commune.iloc[-1]
            fig_hist.add_trace(go.Scatter(
                x=[_last["annee"], PREDICTION_YEAR],
                y=[_last["avg_price_m2"], sim_row["predicted_avg_price_m2"]],
                mode="lines+markers", name=f"Prédiction IA {PREDICTION_YEAR}",
                line=dict(color="#FB8C00", width=2, dash="dash"),
                marker=dict(symbol="diamond", size=10),
            ))
        fig_hist.update_layout(
            height=340, margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title="Année", yaxis_title="Prix moyen (€/m²)",
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig_hist, use_container_width=True, key="price_history")
        st.caption("Historique des ventes DVF (gold multi-années) ; en pointillé, la prédiction RandomForest.")

# ── COMPARATEUR DE COMMUNES ────────────────────────────────────────────────────
st.divider()
st.subheader("⚖️ Comparateur de communes")
_compare_choices = st.multiselect(
    "Choisissez 2 à 4 communes à comparer",
    sorted(data["nom_commune"].dropna().unique().tolist()),
    max_selections=4,
)
if len(_compare_choices) >= 2:
    _comp = data[data["nom_commune"].isin(_compare_choices)].drop_duplicates("nom_commune")

    comp_col1, comp_col2 = st.columns([1.2, 1])
    with comp_col1:
        _comp_rows = {
            "Prix/m² (DVF)": _comp["avg_price_m2"].map(lambda x: f"{x:,.0f} €".replace(",", " ") if pd.notna(x) else "N/A"),
            "Population": _comp["population"].map(lambda x: f"{x:,.0f}".replace(",", " ") if pd.notna(x) else "N/A"),
        }
        if PREDICTION_YEAR and "predicted_avg_price_m2" in _comp.columns:
            _comp_rows[f"Prix estimé {PREDICTION_YEAR} (IA)"] = _comp["predicted_avg_price_m2"].map(
                lambda x: f"{x:,.0f} €".replace(",", " ") if pd.notna(x) else "N/A")
        for _label, _col in CRITERIA_COLUMNS.items():
            if _col in _comp.columns:
                _comp_rows[_label] = _comp[_col].map(lambda x: f"{x:.0f}/100" if pd.notna(x) else "N/A")
        if persona_col and persona_col in _comp.columns:
            _comp_rows[f"Score {persona_label}"] = _comp[persona_col].map(
                lambda x: f"{x:.0f}/100" if pd.notna(x) else "N/A")
        st.dataframe(
            pd.DataFrame(_comp_rows, index=_comp["nom_commune"]).T,
            use_container_width=True,
        )
    with comp_col2:
        fig_comp = go.Figure()
        _axes = [label for label, col in CRITERIA_COLUMNS.items() if col in _comp.columns]
        for _, _crow in _comp.iterrows():
            fig_comp.add_trace(go.Scatterpolar(
                r=[_crow.get(CRITERIA_COLUMNS[a], 0) or 0 for a in _axes],
                theta=_axes, fill="toself", name=_crow["nom_commune"], opacity=0.55,
            ))
        fig_comp.update_layout(
            polar=dict(radialaxis=dict(range=[0, 100], showticklabels=False)),
            height=380, margin=dict(l=40, r=40, t=30, b=30),
            legend=dict(orientation="h", y=-0.1),
        )
        st.plotly_chart(fig_comp, use_container_width=True, key="radar_compare")

# ── ANALYSE PAR TERRITOIRE (région / département / carte) ─────────────────────
st.divider()
st.subheader("🗺️ Analyse par territoire")
tab_region, tab_dept_view, tab_choro = st.tabs(["Par région", "Par département", "Carte des prix"])

with tab_region:
    if "region" in df_all.columns and df_all["region"].notna().any():
        _reg = df_all.groupby("region").agg(
            communes=("code_commune", "nunique"),
            population=("population", "sum"),
            prix_m2_moyen=("avg_price_m2", "mean"),
            score_qualite=("critere_score", "mean"),
        ).sort_values("prix_m2_moyen", ascending=False).reset_index()
        _reg_display = _reg.copy()
        _reg_display["population"] = _reg_display["population"].map(lambda x: f"{x:,.0f}".replace(",", " "))
        _reg_display["prix_m2_moyen"] = _reg_display["prix_m2_moyen"].map(lambda x: f"{x:,.0f} €".replace(",", " "))
        _reg_display["score_qualite"] = _reg_display["score_qualite"].map(lambda x: f"{x:.0f}/100")
        st.dataframe(_reg_display.rename(columns={
            "region": "Région", "communes": "Communes", "population": "Population",
            "prix_m2_moyen": "Prix/m² moyen", "score_qualite": "Qualité de vie",
        }), hide_index=True, use_container_width=True)
        st.plotly_chart(
            px.bar(_reg, x="region", y="prix_m2_moyen", height=320,
                   labels={"region": "", "prix_m2_moyen": "Prix moyen (€/m²)"}),
            use_container_width=True, key="bar_regions",
        )
    else:
        st.caption("Pas de colonne région dans les données chargées.")

with tab_dept_view:
    _dep = df_all.dropna(subset=["code_departement"]).groupby("code_departement").agg(
        communes=("code_commune", "nunique"),
        population=("population", "sum"),
        prix_m2_moyen=("avg_price_m2", "mean"),
    ).sort_values("prix_m2_moyen", ascending=False).reset_index()
    _dep_display = _dep.copy()
    _dep_display["population"] = _dep_display["population"].map(lambda x: f"{x:,.0f}".replace(",", " "))
    _dep_display["prix_m2_moyen"] = _dep_display["prix_m2_moyen"].map(lambda x: f"{x:,.0f} €".replace(",", " "))
    st.dataframe(_dep_display.rename(columns={
        "code_departement": "Département", "communes": "Communes",
        "population": "Population", "prix_m2_moyen": "Prix/m² moyen",
    }), hide_index=True, use_container_width=True, height=320)

with tab_choro:
    _geojson = load_dept_geojson()
    if _geojson is None:
        st.caption("Contours des départements indisponibles (pas de connexion) — la carte à bulles reste disponible plus haut.")
    else:
        _dep_map = data.dropna(subset=["code_departement"]).groupby("code_departement", as_index=False).agg(
            prix_m2_moyen=("avg_price_m2", "mean"),
        )
        fig_choro = px.choropleth_mapbox(
            _dep_map, geojson=_geojson, locations="code_departement",
            featureidkey="properties.code", color="prix_m2_moyen",
            color_continuous_scale="YlOrRd",
            labels={"prix_m2_moyen": "Prix €/m²"},
            center={"lat": 46.5, "lon": 2.3}, zoom=4.6, opacity=0.75, height=520,
        )
        fig_choro.update_layout(mapbox_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig_choro, use_container_width=True, key="choropleth_depts")
        st.caption("Prix moyen au m² par département (choroplèthe) — moyenne des communes chargées.")
