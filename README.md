# HOMEPEDIA

HOMEPEDIA is a Data Engineering and BI project for French housing and territorial decision-making.

Main question:

> Where should someone live or invest in France according to the best compromise between housing prices, accessibility, mobile network, quality of life, and territorial indicators?

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
│   ├── ingestion/
│   ├── cleaning/
│   ├── transformation/
│   ├── spark_jobs/
│   └── quality_checks/
├── dbt/
├── airflow/
├── database/
├── backend/
├── dashboard/
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

Run the local pipeline with a local DVF CSV:

```bash
python -m data_pipeline.ingestion.ingest_dvf --input ../path/to/dvf.csv --year 2022
python -m data_pipeline.transformation.bronze_dvf --year 2022
python -m data_pipeline.cleaning.silver_dvf --year 2022
python -m data_pipeline.transformation.gold_real_estate --year 2022
```

Run quality checks:

```bash
python -m data_pipeline.quality_checks.check_gold --year 2022
```

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Load the schema:

```bash
psql "$DATABASE_URL" -f database/schema.sql
```

Start the API:

```bash
uvicorn backend.app.main:app --reload
```

Start the Streamlit prototype:

```bash
streamlit run dashboard/streamlit/app.py
```

## Data Lake Layers

- `raw`: original files, unchanged
- `bronze`: standardized columns, typed files, Parquet
- `silver`: cleaned and normalized business entities
- `gold`: BI-ready marts and KPI tables

## Current Deliverables

- technical architecture
- SQL schema
- DVF ingestion
- bronze, silver, and gold transformations
- PySpark aggregation job
- Airflow DAG
- DBT model skeleton
- FastAPI skeleton
- Streamlit prototype
- BI documentation

