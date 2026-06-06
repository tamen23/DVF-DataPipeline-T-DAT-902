# Commands

## Environment

```bash
cd homepedia
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Pipeline

```bash
python -m data_pipeline.ingestion.ingest_dvf --input ../dvf.csv --year 2022
python -m data_pipeline.transformation.bronze_dvf --year 2022
python -m data_pipeline.cleaning.silver_dvf --year 2022
python -m data_pipeline.transformation.gold_real_estate --year 2022
python -m data_pipeline.quality_checks.check_gold --year 2022
```

## Spark

```bash
spark-submit data_pipeline/spark_jobs/aggregate_dvf.py \
  --input data_lake/silver/dvf/2022/real_estate_transactions_2022.parquet \
  --output data_lake/gold/real_estate_spark/2022
```

## Database

```bash
docker compose up -d postgres
psql "$DATABASE_URL" -f database/schema.sql
psql "$DATABASE_URL" -f database/seed.sql
```

## API

```bash
uvicorn backend.app.main:app --reload
```

## Streamlit

```bash
streamlit run dashboard/streamlit/app.py
```

## Documents CSV Profiling

```bash
python -m data_pipeline.profiling.profile_documents --documents-dir ../Documents
```

Outputs:

- `docs/documents_csv_analysis.md`
- `data_lake/gold/external_catalog/documents_csv_profiles.json`

## DBT

```bash
cp dbt/profiles.yml.example ~/.dbt/profiles.yml
cd dbt
dbt debug
dbt run
dbt test
```
