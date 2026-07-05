# HOMEPEDIA

HOMEPEDIA is a Data Engineering and BI project for French housing and territorial decision-making.

Main question:

> Where should someone live or invest in France according to the best compromise between housing prices, accessibility, mobile network, quality of life, and territorial indicators?

## First App Version

The current Streamlit app uses generated commune-level data to demonstrate the final HOMEPEDIA concept before the real datasets are fully connected.

It includes:

- persona selection: student, young worker, family, elderly person, investor
- generated French communes
- real-estate price per square meter
- transport, mobile network, green spaces, services, education, health, and investment indicators
- persona-based scoring
- ranking table
- map visualization
- best-commune radar chart

Generate the demo data:

```bash
python -m data_pipeline.generation.generate_demo_territories
```

Start the app:

```bash
python -m streamlit run dashboard/streamlit/app.py
```

## MVP Scope

Version 1 focuses on:

- DVF real estate transactions
- French regions, departments, and communes
- average price and price per square meter
- annual evolution
- commune ranking
- BI-ready gold tables
- Power BI model support
- optional Streamlit prototype

Version 2 adds mobile network, transport, and global scoring. Version 3 adds scraping, NLP, AI, and cloud deployment.

## Architecture

```text
homepedia/
├── data_lake/
│   ├── raw/
│   ├── bronze/
│   ├── silver/
│   └── gold/
├── data_pipeline/
│   ├── ingestion/        # one script per source + HDFS upload
│   ├── cleaning/         # silver transformations
│   ├── generation/       # demo data generator
│   ├── transformation/   # bronze/gold builders, silver listings
│   ├── spark_jobs/       # PySpark gold aggregation (USE_SPARK=1)
│   ├── ml/               # IA: prédiction de prix + communes similaires
│   ├── streaming/        # Kafka producers, scrapers, bronze consumer
│   ├── export/           # PostgreSQL/PostGIS loader
│   └── quality_checks/
├── dbt/                  # staging -> intermediate -> marts (Postgres)
├── airflow/              # DAG run by the compose airflow service
├── database/             # schema.sql (Postgres) + hive_schema.sql (Hive)
├── hadoop/               # HDFS/Hive container config
├── backend/              # FastAPI over Hive
├── dashboard/            # Streamlit (API-first) + Power BI docs
└── docs/
```

## Quick Start

Create the environment:

```bash
cd homepedia
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the environment file:

```bash
cp .env.example .env
```

Start the infrastructure (HDFS, Hive, Postgres, Kafka, Airflow):

```bash
docker compose up -d
```

Create the Hive tables (once, after hive-server is up):

```bash
docker exec -i homepedia-hive-server beeline -u jdbc:hive2://localhost:10000 -n hive -f /dev/stdin < database/hive_schema.sql
```

Run the full pipeline (ingestion → gold → quality → HDFS → Postgres):

```bash
./pipeline.sh 2023          # Linux/macOS (Windows: pipeline.bat 2023)
USE_SPARK=1 ./pipeline.sh   # gold aggregation with PySpark (requires Java)
SKIP_POSTGRES=1 ./pipeline.sh  # skip the Postgres/dbt branch
```

Or step by step with a local DVF CSV:

```bash
python -m data_pipeline.ingestion.ingest_dvf --input ../path/to/dvf.csv --year 2022
python -m data_pipeline.transformation.bronze_dvf --year 2022
python -m data_pipeline.cleaning.silver_dvf --year 2022
python -m data_pipeline.transformation.gold_real_estate --year 2022
python -m data_pipeline.quality_checks.check_gold --year 2022
```

Load PostgreSQL and run the dbt marts (schema.sql is applied automatically):

```bash
python -m data_pipeline.export.load_postgres --year 2023
cp dbt/profiles.yml.example dbt/profiles.yml
cd dbt && dbt run --profiles-dir .
```

Orchestrate with Airflow instead of the shell scripts (UI on http://localhost:8081,
admin password: `docker logs homepedia-airflow 2>&1 | grep -i password`):

```bash
docker compose up -d airflow
# then trigger the homepedia_dvf_pipeline DAG from the UI
```

Start the API (reads Hive):

```bash
uvicorn backend.app.main:app --reload
```

Start the Streamlit dashboard (reads the API, falls back to local parquet):

```bash
HOMEPEDIA_API_URL=http://localhost:8000 python -m streamlit run dashboard/streamlit/app.py
```

Open the BI dashboards (Grafana, auto-provisioned over PostgreSQL):

```text
http://localhost:3000  (admin / homepedia) — folder HOMEPEDIA
```

## Data Lake Layers

- `raw`: original files, unchanged
- `bronze`: standardized columns, typed files, Parquet
- `silver`: cleaned and normalized business entities
- `gold`: BI-ready marts and KPI tables

## Current Deliverables

- technical architecture (docs/architecture.md — matches the code)
- dual serving: Hive external tables (HDFS) and PostgreSQL/PostGIS
- ingestion for DVF, communes, ARCEP, INSEE, OSM, GTFS, loyers, taxe foncière
- bronze, silver, and gold transformations with a quality gate
- Kafka streaming: scrapers → producers → bronze consumer → silver listings
- PySpark gold aggregation, interchangeable with pandas (USE_SPARK=1)
- Airflow DAG runnable from the compose airflow service
- dbt models (staging → marts) running on the loaded Postgres
- FastAPI over Hive (parameterized queries, /territories bulk endpoint)
- Streamlit dashboard reading the API with local-parquet fallback
- Grafana BI dashboards auto-provisioned over PostgreSQL (Power BI views
  remain documented in docs/powerbi_views.md as an alternative)
- IA: prédiction de prix par commune (RandomForest sur l'historique DVF)
  et recommandation de communes similaires (k-NN sur les scores) — colonnes
  « Prix estimé (IA) » et « Communes similaires » dans le dashboard
- analyse textuelle : sentiment FR + nuage de mots par commune calculés
  sur les textes d'annonces scrapées (data_pipeline/nlp)
- MongoDB : archivage non-relationnel du JSON brut des annonces Kafka
- dashboard multi-niveaux : sélecteur de persona (étudiant, jeune actif,
  famille, personne âgée, investisseur), historique de prix + prédiction,
  comparateur de communes, agrégats région/département, choroplèthe des
  prix, écart prix annonces vs ventes DVF
- CI on GitHub Actions: syntax checks, compose validation, dbt parse,
  and a pipeline smoke test on the sample DVF file
