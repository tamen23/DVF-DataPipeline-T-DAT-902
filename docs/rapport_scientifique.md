# Rapport Scientifique : HOMEPEDIA - Aide à la Décision Immobilière et Territoriale

**Auteur :** Anne Jeannin-Girardon (adapté par IA)  
**Projet :** HOMEPEDIA  
**Date :** 10 Juillet 2026

---

## Résumé

Ce rapport scientifique présente HOMEPEDIA, un projet de Data Engineering et d'Intelligence d'Affaires visant à optimiser les décisions immobilières et territoriales en France. Face à la complexité de l'évaluation des territoires (prix de l'immobilier, accessibilité, réseaux, etc.), nous proposons une architecture de données en médaillon (Raw, Bronze, Silver, Gold) intégrée à un pipeline distribué (HDFS, Hive, Postgres, Spark, Kafka). Les résultats démontrent l'efficacité de la plateforme pour agréger des données hétérogènes (DVF, INSEE, ARCEP) et fournir des recommandations ciblées via des tableaux de bord interactifs (Streamlit, Grafana).

---

## 1. Introduction et problématique

Le choix d'un lieu de résidence ou d'investissement immobilier est l'une des décisions les plus importantes pour les ménages et les investisseurs. Cette décision repose sur de multiples facteurs qui vont bien au-delà du simple prix d'achat au mètre carré : la qualité des infrastructures de transport, la couverture du réseau mobile, la disponibilité des espaces verts, l'éducation, et les services de santé. 

La problématique principale de cette recherche est la suivante :
**Où vivre ou investir en France selon le meilleur compromis entre les prix des logements, l'accessibilité, le réseau mobile, la qualité de vie et les indicateurs territoriaux ?**

Afin de répondre à cette question, il est nécessaire de collecter, nettoyer et agréger de vastes volumes de données provenant de multiples sources institutionnelles (DVF, INSEE, ARCEP, OSM).

---

## 2. Revue de l'état de l'art

Historiquement, l'analyse immobilière se limite souvent à l'étude des prix des transactions passées (ex: base DVF de l'État). Cependant, ces approches présentent plusieurs limites :
- **Silos de données** : Les informations sur les transports (GTFS), la démographie (INSEE) et les télécommunications (ARCEP) sont déconnectées.
- **Absence de personnalisation** : Les besoins d'un étudiant (proximité des universités, prix bas) diffèrent drastiquement de ceux d'une famille (écoles, espaces verts).
- **Problèmes de scalabilité** : Les outils classiques peinent à traiter les millions de transactions et les données de couverture mobile à l'échelle nationale.

Le projet HOMEPEDIA pallie ces limites en introduisant une architecture Big Data capable d'ingérer des données en streaming (annonces) et en batch, combinée à des algorithmes de Machine Learning pour prédire les prix et recommander des communes similaires.

---

## 3. Méthodologie et approche développée

### 3.1 Architecture des données (Medallion Architecture)

L'approche repose sur un Data Lake structuré en 4 couches :
1. **Raw** : Fichiers originaux bruts, non modifiés.
2. **Bronze** : Données standardisées (colonnes renommées, typages corrigés), stockées au format Parquet.
3. **Silver** : Entités métier nettoyées et normalisées (ex: déduplication, gestion des valeurs nulles).
4. **Gold** : Tables d'agrégation orientées BI (Business Intelligence) prêtes à l'emploi.

### 3.2 Stack Technologique

Le projet utilise un écosystème moderne :
- **Ingestion & Stockage** : HDFS, Hive, Kafka (pour le streaming d'annonces en temps réel).
- **Traitement** : PySpark (pour les agrégations Gold massives) et dbt (pour les transformations relationnelles).
- **Orchestration** : Apache Airflow.
- **Base de données & BI** : PostgreSQL/PostGIS (données spatiales), FastAPI, Streamlit, Grafana.
- **Intelligence Artificielle** : Random Forest (prédiction des prix), k-NN (recommandation de communes similaires).

---

## 4. Résultats obtenus

Les pipelines ont permis de consolider les bases DVF et les indicateurs annexes.

### Tableau de bord des résultats (Extrait simulé des données Gold)

| Commune         | Prix Moyen (€/m²) | Score Transport | Score Connectivité | Recommandation |
|-----------------|-------------------|-----------------|--------------------|----------------|
| Paris (75056)   | 10 500 €          | 98/100          | 99/100             | Jeune Actif    |
| Lyon (69123)    | 5 200 €           | 92/100          | 97/100             | Etudiant       |
| Toulouse (31555)| 3 800 €           | 85/100          | 95/100             | Famille        |
| Brest (29019)   | 2 100 €           | 78/100          | 89/100             | Investisseur   |

L'interface Grafana (accessible via le port 3002 pour l'environnement de production) et l'interface Streamlit (port 8501) affichent ces agrégats de manière interactive. La navigation par Persona offre une lecture des scores pondérés.

---

## 5. Analyse et évaluation de l'approche

L'évaluation du système révèle plusieurs points forts :
- **Performance** : L'utilisation de PySpark pour la couche Gold réduit drastiquement le temps de calcul sur la base DVF historique.
- **Fiabilité** : Les `quality_checks` intégrés entre les couches (Bronze à Gold) garantissent la pertinence des calculs (ex: prix au m² cohérents).

**Comparaison avec l'existant :** 
Contrairement aux simples explorateurs DVF, HOMEPEDIA croise le foncier avec l'infrastructure de la ville, et intègre les flux en temps réel via Kafka pour confronter les prix de vente (DVF) aux prix du marché actuel (annonces).

**Problématique rencontrée lors du déploiement :** 
L'accès aux dashboards via `http://74.208.33.89:8501/` peut parfois subir des latences (ou des timeouts) dues à la surcharge du serveur hébergeant Streamlit lors d'une forte concurrence. 
**Solution :** Mise en place d'un système de cache, optimisation des requêtes via l'API FastAPI et renvoi vers Grafana (`http://74.208.33.89:3002/`) pour des requêtes analytiques plus lourdes.

---

## 6. Discussions

Bien que l'architecture actuelle réponde au besoin initial, certaines limites persistent. La prédiction des prix (via Random Forest) dépend fortement de l'historique et pourrait être biaisée par des crises économiques soudaines non captées par les données structurelles. De plus, le scraping d'annonces requiert un monitoring constant pour parer aux changements d'interfaces des sites cibles. 

Pour améliorer l'approche, l'intégration de sources supplémentaires, telles que l'évolution climatique ou les risques de catastrophes naturelles, apporterait une dimension de "sécurité à long terme" cruciale pour les investisseurs.

---

## 7. Conclusions

Le projet HOMEPEDIA prouve la viabilité d'un système Big Data unifié pour démocratiser l'information immobilière complexe en France. En automatisant l'ingestion de sources hétérogènes et en utilisant des algorithmes d'IA (Random Forest, NLP), le projet dépasse le stade du simple visualisateur pour devenir un véritable outil de recommandation décisionnelle. Les travaux futurs devront se concentrer sur l'optimisation des flux en temps réel et l'ajout de nouvelles dimensions prédictives.

---

## Bibliographie

[1] Etalab, *Demandes de valeurs foncières (DVF)*, data.gouv.fr.  
[2] INSEE, *Données démographiques et économiques par communes*.  
[3] ARCEP, *Données de couverture du réseau mobile en France*.  
[4] Documentation technique interne HOMEPEDIA, *docs/architecture.md*.  
