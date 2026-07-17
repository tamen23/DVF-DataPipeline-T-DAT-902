# HOMEPEDIA — Real-Estate & Territory Analytics Platform

> A Big-Data pipeline that ranks French cities by attractiveness — combining property prices, demographics, income, and mobile-network coverage into a single interactive dashboard.

**Epitech MSc Pro — T-DAT-902 (Data Engineering project).**

HOMEPEDIA answers one question:

> **Where should you live or invest in France, given the best trade-off between cost, accessibility, and quality of life?**

It ingests open data from several French public sources, cleans and transforms it through a Bronze → Silver → Gold data-lake pattern, stores it in Hadoop/Hive and PostgreSQL, and serves it through an interactive Streamlit dashboard with maps, city rankings, and multi-criteria comparison.

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Data sources](#data-sources)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Running the data pipeline](#running-the-data-pipeline)
- [Launching the dashboard](#launching-the-dashboard)
- [Project structure](#project-structure)
- [Team](#team)

---

## Features

- **Real-estate analysis** — average price, price per m², transaction volume, year-over-year price evolution.
- **Territory analysis** — population, density, median income, commune-to-commune comparison.
- **Accessibility analysis** — 4G/5G mobile coverage (ARCEP), transport access.
- **Visualization** — interactive dashboard, dynamic maps, city ranking, side-by-side comparison.
- **Predictions** — a RandomForest model projects future prices from historical DVF data.

---

## Architecture

```
Open data sources (DVF, INSEE, ARCEP, DataGouv)
        |
        v
[ Ingestion ]  -> raw files downloaded (data_pipeline/ingestion)
        |
        v
[ Bronze ]     -> raw structured (data_pipeline/transformation)
        |
        v
[ Silver ]     -> cleaned & normalized (data_pipeline/cleaning)
        |
        v
[ Gold ]       -> business aggregates, pandas or PySpark (data_pipeline/transformation | spark_jobs)
        |
        +--> HDFS / Hive        (analytical store)
        +--> PostgreSQL + dbt   (serving layer for the dashboard)
                   |
                   v
        [ Streamlit dashboard ] — maps, rankings, comparison
```

Orchestration is available through **Apache Airflow**; the full run can also be triggered end-to-end with a single script (`pipeline.sh`).

---

## Tech stack

| Layer            | Technologies |
|------------------|--------------|
| Ingestion / ETL  | Python, Pandas, Requests, BeautifulSoup |
| Distributed      | PySpark, Hadoop (HDFS), Hive |
| Streaming        | Kafka, Zookeeper |
| Serving DB       | PostgreSQL, dbt |
| Document store   | MongoDB |
| Orchestration    | Apache Airflow |
| Visualization    | Streamlit, Plotly, Folium (maps), Power BI |
| Monitoring       | Grafana |
| Infrastructure   | Docker, Docker Compose |

---

## Data sources

- **DVF** — Demandes de Valeurs Foncières (property transactions)
- **INSEE** — demographics & socio-economic indicators
- **ARCEP** — mobile network (4G/5G) coverage
- **DataGouv** — French geographic reference data (communes)

---

## Prerequisites

- **Python 3.10+**
- **Docker** and **Docker Compose** (for the Hadoop/Hive/PostgreSQL/Kafka stack)
- **Java 11+** — only required if you run the Gold aggregation with PySpark (`USE_SPARK=1`)
- ~10 GB free disk for the data lake + containers

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/tamen23/DVF-DataPipeline-T-DAT-902.git
cd DVF-DataPipeline-T-DAT-902

# 2. Python environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Environment file
cp .env.example .env             # then edit values if needed

# 4. Start the infrastructure (Hadoop, Hive, PostgreSQL, Kafka, Grafana, Airflow…)
docker compose up -d

# 5. Run the pipeline for a given year (default 2023)
./pipeline.sh 2023               # Windows: pipeline.bat 2023

# 6. Launch the dashboard
streamlit run dashboard/streamlit/app.py
```

Then open the dashboard URL that Streamlit prints (default `http://localhost:8501`).

---

## Running the data pipeline

The pipeline runs in 11 stages: ingest communes & ARCEP, download DVF for the target
year and the previous year (for year-over-year deltas), build Bronze/Silver/Gold layers,
run quality checks, build the territory Gold table, train the price-prediction model,
upload to HDFS, and load PostgreSQL via dbt.

```bash
# Standard run for 2023
./pipeline.sh 2023

# Use PySpark for the Gold aggregation (requires Java)
USE_SPARK=1 ./pipeline.sh 2023

# Skip the PostgreSQL/dbt load (Hive-only run)
SKIP_POSTGRES=1 ./pipeline.sh 2023
```

On Windows, use `pipeline.bat 2023` (same stages).

Individual stages can also be run directly, e.g.:

```bash
python -m data_pipeline.ingestion.ingest_dvf --year 2023
python -m data_pipeline.cleaning.silver_dvf --year 2023
python -m data_pipeline.quality_checks.check_gold --year 2023
```

---

## Launching the dashboard

```bash
streamlit run dashboard/streamlit/app.py
```

The dashboard reads from PostgreSQL (populated by the pipeline). If you only ran the
pipeline with `SKIP_POSTGRES=1`, load PostgreSQL first:

```bash
python -m data_pipeline.export.load_postgres --year 2023
```

---

## Project structure

```
.
├── data_pipeline/        # Core ETL — the heart of the project
│   ├── ingestion/        #   downloaders (DVF, INSEE, ARCEP, communes, HDFS upload)
│   ├── transformation/   #   Bronze + Gold layers
│   ├── cleaning/         #   Silver layer (normalization)
│   ├── spark_jobs/       #   PySpark alternatives for heavy aggregation
│   ├── quality_checks/   #   data-quality gates
│   ├── ml/               #   price-prediction model (RandomForest)
│   ├── nlp/              #   text-analysis modules
│   └── streaming/        #   Kafka producers/consumers
├── dashboard/            # Streamlit app + Power BI assets
├── dbt/                  # dbt models for the PostgreSQL serving layer
├── airflow/              # Airflow DAGs for orchestration
├── hadoop/               # Hadoop/Hive container config
├── grafana/              # Grafana dashboards
├── data_lake/            # Raw/Bronze/Silver/Gold storage
├── database/             # SQL schema / init
├── backend/              # FastAPI service
├── docker-compose.yml    # Full infrastructure stack
├── pipeline.sh           # End-to-end pipeline (Linux/macOS)
├── pipeline.bat          # End-to-end pipeline (Windows)
└── requirements.txt      # Python dependencies
```

---

## Team

| Member  | Role |
|---------|------|
| Yanis   | Product Owner & Architecture |
| Bilal   | Data Ingestion & Data Quality |
| Lys     | PySpark & Transformations |
| Paternus (Leo) | PostgreSQL & Orchestration |
| Marie   | Power BI & Visualization |

---

## Notes

- This is an academic project built for **Epitech MSc Pro (T-DAT-902)**.
- Full history and every contributor's commits are preserved in this repository.
- No live credentials are committed; copy `.env.example` to `.env` and fill in your own.
