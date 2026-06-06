```markdown
# HOMEPEDIA

## Présentation

HOMEPEDIA est une plateforme Big Data d'analyse territoriale et immobilière permettant d'identifier les villes les plus attractives en France selon plusieurs critères : prix de l'immobilier, accessibilité aux transports, couverture réseau mobile et indicateurs socio-économiques.

L'objectif est d'aider les particuliers, familles, étudiants et investisseurs à prendre des décisions éclairées concernant leur lieu de résidence ou leurs investissements immobiliers.

---

## Problématique

Aujourd'hui, les données permettant d'évaluer l'attractivité d'un territoire sont dispersées entre de nombreuses sources :

- Immobilier (DVF)
- INSEE
- DataGouv
- Données géographiques
- Réseaux mobiles (4G/5G)
- Transports
- Indicateurs socio-économiques

HOMEPEDIA centralise, nettoie, analyse et visualise ces données afin de répondre à une question simple :

> **Où habiter ou investir en France selon le meilleur compromis entre coût, accessibilité et qualité de vie ?**

---

## Fonctionnalités principales

### Analyse immobilière
- Prix moyen des biens
- Prix moyen au m²
- Nombre de transactions
- Évolution des prix

### Analyse territoriale
- Population
- Densité
- Revenu médian
- Comparaison entre communes

### Analyse de l'accessibilité
- Couverture 4G / 5G
- Accessibilité aux transports
- Comparaison des territoires

### Visualisation
- Dashboard interactif
- Cartographie dynamique
- Classement des villes
- Comparaison multi-critères

---

## Architecture technique

### Data Engineering
- Python
- Pandas
- PySpark
- DBT
- Apache Airflow

### Stockage
- PostgreSQL
- PostGIS
- Data Lake (Raw / Bronze / Silver / Gold)

### Visualisation
- Power BI
- Streamlit
- Plotly

### Infrastructure
- Docker
- Docker Compose

---

## Sources de données

- DVF (Demandes de Valeurs Foncières)
- INSEE
- DataGouv
- Données géographiques françaises
- Données réseaux mobiles
- Données transports

---

## Objectifs du projet

### Version 1 (MVP)
- Intégration des données DVF
- Calcul des indicateurs immobiliers
- Cartographie des prix
- Dashboard Power BI
- Classement des communes

### Version 2
- Intégration des données réseau mobile
- Intégration des données transports
- Score d'attractivité territorial

### Version 3
- Analyse de texte
- IA et prédictions
- Déploiement cloud

---

## Équipe

| Membre | Rôle |
|----------|----------|
| Yanis | Product Owner & Architecture |
| Bilal | Data Ingestion & Data Quality |
| Lys | PySpark & Transformations |
| Paternus | PostgreSQL & Orchestration |
| Marie | Power BI & Visualisation |

---

## Résultat attendu

Une plateforme décisionnelle capable de transformer des millions de lignes de données en indicateurs clairs, visualisations interactives et recommandations territoriales permettant d'identifier les meilleures zones où vivre ou investir en France.
```
