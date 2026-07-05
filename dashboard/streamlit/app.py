from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_LAKE = PROJECT_ROOT / "data_lake" / "gold"
REAL_PATH = DATA_LAKE / "territories" / "territory_scores.parquet"
DEMO_PATH = DATA_LAKE / "demo" / "territory_scores.parquet"

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
def load_data() -> pd.DataFrame:
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
    values_closed = values + [values[0]]
    labels_closed = labels + [labels[0]]
    fig = go.Figure(go.Scatterpolar(
        r=values_closed, theta=labels_closed,
        fill="toself", name=title,
        line_color="#42A5F5",
    ))
    fig.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, 100]}},
        showlegend=False, height=380,
        margin={"l": 30, "r": 30, "t": 40, "b": 30},
        title=title,
    )
    return fig


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

    for annee in range(1, 21):
        for _ in range(12):
            for b in biens:
                b.step_mois()

        nb = len(biens)
        loyers_annuels = loyer_mensuel * 12 * nb
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
    cf_mensuel_net_initial = (loyer_mensuel * 12 - mensualite_initiale * 12
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

# ── SIDEBAR : Profil investisseur ─────────────────────────────────────────────
st.sidebar.title("🏦 Mon profil investisseur")

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

if mode_expert:
    age = st.sidebar.number_input("Votre âge", min_value=18, max_value=65, value=30, step=1,
        help="Sert à calculer le taux d'assurance emprunteur, qui augmente avec l'âge.")
    duree = st.sidebar.select_slider(
        "Durée du prêt",
        options=[10, 15, 20, 25], value=20,
        help="Plus la durée est longue, plus la mensualité est basse — mais plus vous payez d'intérêts au total.",
    )
    surface = st.sidebar.slider("Surface recherchée (m²)", min_value=20, max_value=120, value=50, step=5)
    meuble = st.sidebar.toggle("Location meublée (+15%)", value=True,
        help="Un bien meublé se loue environ 15% plus cher et permet le régime LMNP (moins d'impôts). Recommandé pour les petites surfaces.")
else:
    age = 30
    duree = 20
    surface = 45
    meuble = True

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
taux_base = TAUX_MARCHE.get(duree, 3.65)
taux_assur_pct = taux_assurance(age)
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
st.title("🏦 HOMEPEDIA — Stratégie investisseur")

if not mode_expert:
    st.info(
        "👋 **Bienvenue !** Cette plateforme vous aide à trouver où investir dans l'immobilier locatif en France.  \n"
        "**Comment ça marche en 3 étapes :**  \n"
        "1️⃣ **Renseignez votre salaire et votre apport** dans la barre à gauche — on calcule automatiquement ce que la banque peut vous prêter  \n"
        "2️⃣ **Choisissez un département** — la carte et le tableau vous montrent les meilleures communes où le loyer couvre votre crédit  \n"
        "3️⃣ **Cliquez sur une commune** dans le tableau pour voir son profil complet et simuler votre investissement sur 20 ans  \n\n"
        "💡 *L'objectif : trouver un appartement dont le loyer couvre entièrement votre mensualité de crédit — vous constituez un patrimoine sans effort.*"
    )
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
c5.metric("Taux retenu", f"{taux_base}% sur {duree} ans")

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
df_all["montant_emprunte"] = (df_all["prix_bien_possible"] - apport).clip(lower=0)
df_all["mensualite_commune"] = df_all["montant_emprunte"].apply(
    lambda m: mensualite(m, taux_base, duree) + m * mensualite_assur_ratio
)
df_all["cashflow_mensuel"] = df_all["loyer_estime"] - df_all["mensualite_commune"] - df_all["charges_tot_annuelles"] / 12
df_all["rendement_brut"] = df_all.apply(lambda r: rendement_brut_commune(r["avg_price_m2"]), axis=1)
df_all["rendement_net"] = (
    (df_all["loyer_estime"] * 12 - df_all["charges_tot_annuelles"]) / df_all["prix_bien_possible"].clip(lower=1) * 100
).clip(lower=0)

# ── CALCUL FISCAL ─────────────────────────────────────────────────────────────
# Intérêts crédit année 1 (approximation : taux × capital emprunté)
df_all["interets_annuels"] = df_all["montant_emprunte"] * taux_base / 100

# Loyer annuel selon régime (meublé +15% pour LMNP)
_loyer_nu_annuel   = df_all["loyer_estime"] * 12
_loyer_lmnp_annuel = df_all["loyer_estime"] * 1.15 * 12

# Amortissements LMNP réel :
#   - Bien     : 2.5%/an du prix d'achat (structure sur 40 ans)
#   - Meubles  : 20%/an sur 10% du prix  (renouvellement tous les 5 ans)
_amort_bien    = df_all["prix_bien_possible"] * 0.025
_amort_meubles = df_all["prix_bien_possible"] * 0.10 * 0.20

if regime_fiscal == "LMNP - Réel (amortissement)":
    # Base imposable = loyer meublé - charges - intérêts - amortissements
    _base = (_loyer_lmnp_annuel - df_all["charges_tot_annuelles"]
             - df_all["interets_annuels"] - _amort_bien - _amort_meubles).clip(lower=0)
    df_all["impot_annuel"] = _base * taux_global_fiscal

elif regime_fiscal == "LMNP - Micro BIC (abattement 50%)":
    # Abattement 50% sur loyer meublé, pas de déduction charges réelles
    _base = _loyer_lmnp_annuel * 0.50
    df_all["impot_annuel"] = _base * taux_global_fiscal

elif regime_fiscal == "Nu - Régime réel":
    # Loyer nu - charges réelles - intérêts déductibles
    _base = (_loyer_nu_annuel - df_all["charges_tot_annuelles"]
             - df_all["interets_annuels"]).clip(lower=0)
    df_all["impot_annuel"] = _base * taux_global_fiscal

else:  # Nu - Micro foncier (abattement 30%)
    # Abattement 30% sur loyer nu
    _base = _loyer_nu_annuel * 0.70
    df_all["impot_annuel"] = _base * taux_global_fiscal

# Loyer retenu selon régime (meublé ou nu)
_loyer_regime = _loyer_lmnp_annuel if "LMNP" in regime_fiscal else _loyer_nu_annuel

df_all["rendement_net_fiscal"] = (
    (_loyer_regime - df_all["charges_tot_annuelles"] - df_all["impot_annuel"])
    / df_all["prix_bien_possible"].clip(lower=1) * 100
).clip(lower=0)

df_all["cashflow_net_fiscal"] = (
    (_loyer_regime - df_all["charges_tot_annuelles"] - df_all["impot_annuel"]) / 12
    - df_all["mensualite_commune"]
)

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
    fig_map = px.scatter_mapbox(
        map_display,
        lat="latitude", lon="longitude",
        color="cashflow_mensuel",
        size=map_display["cashflow_mensuel"].clip(lower=10).fillna(10),
        hover_name="nom_commune",
        hover_data={
            "avg_price_m2": ":.0f",
            "loyer_estime": ":.0f",
            "mensualite_commune": ":.0f",
            "cashflow_mensuel": ":.0f",
            "rendement_brut": ":.1f",
            "latitude": False, "longitude": False,
        },
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=0,
        range_color=[-300, 300],
        center={"lat": center_lat, "lon": center_lon},
        zoom=zoom,
        height=420,
    )
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

if _pool.empty:
    st.warning("Aucune commune trouvée. Essayez d'augmenter l'apport ou allonger la durée.")
    top = pd.DataFrame()
else:
    cf_min, cf_max = _pool["cashflow_mensuel"].min(), _pool["cashflow_mensuel"].max()
    cf_range = cf_max - cf_min if cf_max != cf_min else 1
    _pool["cf_norm"] = (_pool["cashflow_mensuel"] - cf_min) / cf_range * 100
    _pool["score_final"] = _pool["critere_score"] * 0.5 + _pool["cf_norm"] * 0.5
    top = _pool.sort_values("score_final", ascending=False).head(10)

    top_display = top[[
        "nom_commune", "avg_price_m2", "prix_bien_possible",
        "loyer_estime", "cashflow_mensuel", "cashflow_net_fiscal",
        "nb_annonces_app", "rendement_brut", "rendement_net_fiscal",
        "impot_annuel", "annual_price_growth", "transaction_count",
    ]].rename(columns={
        "nom_commune": "Commune",
        "avg_price_m2": "Prix/m² (DVF)",
        "prix_bien_possible": f"Prix bien ({surface}m²)",
        "loyer_estime": "Loyer/mois",
        "cashflow_mensuel": "Cash-flow brut/mois",
        "cashflow_net_fiscal": "Cash-flow net fiscal/mois",
        "nb_annonces_app": "Annonces loc. (ANIL)",
        "rendement_brut": "Rendement brut",
        "rendement_net_fiscal": "Rendement net fiscal",
        "impot_annuel": "Impôt/an",
        "annual_price_growth": "Évol. prix/an",
        "transaction_count": "Fiabilité prix",
    }).copy()

    top_display["Prix/m² (DVF)"] = top_display["Prix/m² (DVF)"].apply(lambda x: f"{x:,.0f} €".replace(",", " "))
    top_display[f"Prix bien ({surface}m²)"] = top_display[f"Prix bien ({surface}m²)"].apply(lambda x: f"{x:,.0f} €".replace(",", " "))
    top_display["Loyer/mois"] = top_display["Loyer/mois"].apply(lambda x: f"{x:.0f} €")
    top_display["Cash-flow brut/mois"] = top_display["Cash-flow brut/mois"].apply(lambda x: f"+{x:.0f} €" if x >= 0 else f"{x:.0f} €")
    top_display["Cash-flow net fiscal/mois"] = top_display["Cash-flow net fiscal/mois"].apply(lambda x: f"+{x:.0f} €" if x >= 0 else f"{x:.0f} €")
    top_display["Annonces loc. (ANIL)"] = top_display["Annonces loc. (ANIL)"].apply(
        lambda x: f"{int(x)} annonces" if pd.notna(x) and x > 0 else "⚠️ aucune donnée"
    )
    top_display["Rendement brut"] = top_display["Rendement brut"].apply(lambda x: f"{x:.1f}%")
    top_display["Rendement net fiscal"] = top_display["Rendement net fiscal"].apply(lambda x: f"{x:.1f}%")
    top_display["Impôt/an"] = top_display["Impôt/an"].apply(lambda x: f"{x:,.0f} €".replace(",", " "))
    top_display["Évol. prix/an"] = top_display["Évol. prix/an"].apply(
        lambda x: f"▲ +{x*100:.1f}%" if pd.notna(x) and x > 0 else (f"▼ {x*100:.1f}%" if pd.notna(x) else "N/A")
    )
    top_display["Nb ventes (DVF)"] = top_display["Fiabilité prix"].apply(
        lambda x: int(x) if pd.notna(x) else 0
    )
    top_display = top_display.drop(columns=["Fiabilité prix"])

    st.caption("Classement : 50% cash-flow + 50% critères qualité (pondérés par vos curseurs) · Cliquez une ligne pour mettre à jour le radar")
    selection = st.dataframe(
        top_display, hide_index=True, use_container_width=True,
        on_select="rerun", selection_mode="single-row",
    )

    # Radar dans col_radar (à côté de la carte), commune pilotée par la sélection du tableau
    selected_rows = selection.selection.get("rows", []) if selection else []
    radar_idx = selected_rows[0] if selected_rows else 0
    radar_row = top.iloc[radar_idx]
    radar_commune = radar_row["nom_commune"]
    with col_radar:
        st.markdown(f"**Profil qualité de vie**")
        st.markdown(f"📍 *{radar_commune}*")
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
    st.markdown("#### Objectif prochain achat")
    apport_2eme = st.number_input(
        "Apport nécessaire pour le 2ème bien (€)",
        min_value=5_000, max_value=200_000, value=20_000, step=1_000,
        help="Quand votre cash-flow cumulé atteint ce montant, vous pouvez solliciter un 2ème crédit",
    )

sim = simulate_20ans(
    prix_bien=sim_prix,
    apport=apport,
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
)

with sim_col2:
    st.markdown("#### Résultats")

    cf_mensuel = sim["cashflow_mensuel"]
    nb_achats = len(sim["achats"])
    r1, r2, r3, r4 = st.columns(4)
    r1.metric(
        "Cash-flow net/mois (bien 1)",
        f"{cf_mensuel:+.0f} €",
        delta="après impôts ✅" if cf_mensuel >= 0 else "effort mensuel ⚠️",
        delta_color="normal" if cf_mensuel >= 0 else "inverse",
        help="Loyer − crédit − charges − impôts",
    )
    r2.metric("Patrimoine net à 20 ans", format_eur(sim["patrimoine_net"][-1]))
    r3.metric("Biens acquis en 20 ans", f"{1 + nb_achats} biens",
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
    if "listings" not in st.session_state:
        st.session_state.listings = None
    if "listings_commune" not in st.session_state:
        st.session_state.listings_commune = None

    from scraper_service import fetch_listings

    btn_achat, btn_location = st.columns(2)
    with btn_achat:
        if st.button("🏠 Annonces d'achat", type="primary", use_container_width=True):
            with st.spinner(f"Recherche achat pour {sim_commune}..."):
                st.session_state.listings = fetch_listings(
                    code_commune=code_commune, nom_commune=sim_commune,
                    postal_code=postal_code, pages=2, mode="achat",
                )
                st.session_state.listings_commune = sim_commune
    with btn_location:
        if st.button("🔑 Annonces de location", use_container_width=True,
                     help="Voir ce que les locataires paient dans cette commune"):
            with st.spinner(f"Recherche location pour {sim_commune}..."):
                st.session_state.listings = fetch_listings(
                    code_commune=code_commune, nom_commune=sim_commune,
                    postal_code=postal_code, pages=2, mode="location",
                )
                st.session_state.listings_commune = sim_commune

if st.session_state.get("listings") is not None:
    result = st.session_state.listings
    listings = result["listings"]
    sources_status = result["sources_status"]
    commune_name = st.session_state.get("listings_commune", "")

    st.subheader(f"Annonces — {commune_name} ({len(listings)} trouvées)")

    for source, (status, message) in sources_status.items():
        if status == "ok":
            st.success(f"✅ **{source}** — {message}")
        elif status == "fallback":
            st.info(f"ℹ️ **{source}** (fallback) — {message}")
        else:
            st.warning(f"⚠️ **{source}** bloqué — {message}")

    blocked = [s for s, (st_, _) in sources_status.items() if st_ == "blocked"]
    if blocked:
        c_sl, c_lbc = st.columns(2)
        c_sl.link_button("🏠 Rechercher sur SeLoger", result["seloger_url"])
        c_lbc.link_button("🟡 Rechercher sur LeBonCoin", result["leboncoin_url"])

    for listing in listings[:20]:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            with c1:
                source = listing.get("source", "")
                emoji = "🏠" if source == "SeLoger" else "🟡" if source == "LeBonCoin" else "🏘️"
                prop_type = listing.get("property_type", "Logement")
                city = listing.get("city") or commune_name
                st.markdown(f"**{emoji} {source}** — {prop_type} à {city}")
                if listing.get("url"):
                    st.markdown(f"[Voir l'annonce]({listing['url']})")
            with c2:
                price = listing.get("price")
                st.metric("Prix", f"{price:,.0f} €".replace(",", " ") if price else "N/A")
            with c3:
                surface_l = listing.get("surface_m2")
                st.metric("Surface", f"{surface_l:.0f} m²" if surface_l else "N/A")
            with c4:
                pm2 = listing.get("price_m2")
                st.metric("Prix/m²", f"{pm2:,.0f} €".replace(",", " ") if pm2 else "N/A")
