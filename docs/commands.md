# Commands

## Environment

```bash
cd homepedia
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Infrastructure (Docker)

```bash
docker compose up -d                 # everything: HDFS, Hive, Postgres, Kafka, Airflow
docker compose up -d postgres        # only the relational branch
docker compose up -d namenode datanode hive-metastore-db hive-metastore hive-server  # only Hive

# Create the Hive tables (once, after hive-server is healthy)
docker exec -i homepedia-hive-server beeline -u jdbc:hive2://localhost:10000 -n hive -f /dev/stdin < database/hive_schema.sql
```

Ports: Hive 10000, Kafka 9092 (host) / kafka:29092 (containers), kafka-ui 8080,
Airflow 8081, Postgres **5433** (5432 is often taken by a native install).

## Full pipeline

```bash
./pipeline.sh 2023                  # Windows: pipeline.bat 2023
USE_SPARK=1 ./pipeline.sh 2023      # gold aggregation with PySpark (requires Java)
SKIP_POSTGRES=1 ./pipeline.sh 2023  # skip the Postgres load step
```

## Pipeline step by step

```bash
python -m data_pipeline.ingestion.ingest_communes
python -m data_pipeline.ingestion.ingest_arcep
python -m data_pipeline.ingestion.ingest_dvf --year 2023          # downloads from DataGouv
python -m data_pipeline.ingestion.ingest_dvf --input ../dvf.csv --year 2023  # or a local file
python -m data_pipeline.transformation.bronze_dvf --year 2023
python -m data_pipeline.cleaning.silver_dvf --year 2023
python -m data_pipeline.transformation.gold_real_estate --year 2023
python -m data_pipeline.quality_checks.check_gold --year 2023
python -m data_pipeline.transformation.build_territory_gold --year 2023
python -m data_pipeline.ingestion.upload_to_hdfs --year 2023      # HDFS + MSCK repair
python -m data_pipeline.export.load_postgres --year 2023          # Postgres/PostGIS
```

## Spark

```bash
python -m data_pipeline.spark_jobs.aggregate_dvf --year 2023
```

Same output contract as the pandas gold builder (single Parquet file,
same columns), so quality checks, HDFS upload and the Postgres load
work unchanged.

## Kafka streaming (listings)

```bash
# Producer: scrape a source and push listings to Kafka
python -m data_pipeline.streaming.producers.listings_producer --source leboncoin --communes 75001 69001
python -m data_pipeline.streaming.producers.listings_producer --source seloger --communes 75056 --loop

# Consumer: write listings to the bronze layer (Ctrl+C to stop,
# or --idle-timeout N to exit after N quiet seconds)
python -m data_pipeline.streaming.consumers.bronze_consumer
python -m data_pipeline.streaming.consumers.bronze_consumer --idle-timeout 120

# Aggregate bronze listings into the silver per-commune mart, then publish
python -m data_pipeline.transformation.silver_listings
python -m data_pipeline.ingestion.upload_to_hdfs --layer silver
```

## Airflow

```bash
docker compose up -d airflow
docker logs homepedia-airflow 2>&1 | grep -i password   # admin password
# UI: http://localhost:8081 — trigger homepedia_dvf_pipeline
# conf (optional): {"year": 2023, "dvf_input": "/opt/airflow/homepedia/samples/dvf_demo_2022.csv"}

docker exec homepedia-airflow airflow dags list
docker exec homepedia-airflow airflow tasks test homepedia_dvf_pipeline load_postgres 2024-01-01
```

## Database (PostgreSQL/PostGIS)

```bash
# schema.sql is applied automatically by the loader
python -m data_pipeline.export.load_postgres --year 2023
python -m data_pipeline.export.load_postgres --year 2023 --skip-transactions  # faster, refs + scores only

# manual access
docker exec -it homepedia-postgres psql -U homepedia -d homepedia
# or: psql "postgresql://homepedia:homepedia@localhost:5433/homepedia"
```

## dbt

```bash
cp dbt/profiles.yml.example dbt/profiles.yml
cd dbt
dbt debug --profiles-dir .
dbt run --profiles-dir .
dbt test --profiles-dir .
```

## API (FastAPI over Hive)

```bash
uvicorn backend.app.main:app --reload
# http://localhost:8000/docs
```

## Streamlit

```bash
HOMEPEDIA_API_URL=http://localhost:8000 python -m streamlit run dashboard/streamlit/app.py
# without HOMEPEDIA_API_URL it reads data_lake/gold/territories/ directly
```

## Generated demo app data

```bash
python -m data_pipeline.generation.generate_demo_territories
```

Output: `data_lake/gold/demo/territory_scores.parquet` (dashboard fallback
when no real data exists).
