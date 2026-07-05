# Architecture

HOMEPEDIA is a lakehouse running locally on Docker, with two serving branches
fed by the same medallion data lake: a big-data branch (HDFS + Hive) and a
relational branch (PostgreSQL/PostGIS + dbt).

## Data lake layers (local `data_lake/`, mirrored in HDFS)

- `raw`: immutable input files (DVF, INSEE, geo.api.gouv.fr, ARCEP, OSM, GTFS) with import metadata.
- `bronze`: standardized columns, typed Parquet. Kafka listings land here via the bronze consumer.
- `silver`: cleaned business entities (DVF transactions, per-commune listing stats), normalized INSEE codes.
- `gold`: BI-ready marts — real-estate KPIs per commune/year, territory scores per persona.

## Flow

```text
Open data (CSV/API)          Scrapers (SeLoger, LeBonCoin, CDC Habitat)
        |                                   |
        v                              Kafka topics
   raw -> bronze -> silver -> gold          |
        (pandas, or PySpark          bronze consumer -> silver_listings
         with USE_SPARK=1)
        |
        +--> quality gate (check_gold: hard failures + warnings)
        |
        +--> HDFS upload + MSCK repair -> Hive external tables -> FastAPI -> Streamlit
        |
        +--> load_postgres -> PostgreSQL/PostGIS -> dbt marts  -> Grafana / psql
```

## Components (all wired)

- **Ingestion** (`data_pipeline/ingestion/`): one script per source, metadata preserved; `upload_to_hdfs` publishes to HDFS and registers Hive partitions.
- **Transformation**: pandas jobs by default; `data_pipeline/spark_jobs/aggregate_dvf.py` is a feature-equivalent PySpark implementation of the gold aggregation (`USE_SPARK=1 ./pipeline.sh`).
- **Streaming** (`data_pipeline/streaming/`): Kafka producers run the scrapers, the bronze consumer batches listings to Parquet; `silver_listings` aggregates them per commune (postal → INSEE translation included).
- **Quality** (`data_pipeline/quality_checks/`): gate between gold and publication; systematic anomalies fail the run, isolated outliers warn.
- **ML** (`data_pipeline/ml/`): price prediction per commune (RandomForest on the gold DVF history, temporal holdout validation) and similar-communes recommendation (k-NN on the territory score vectors); surfaced in the dashboard as "Prix estimé (IA)" and "Communes similaires".
- **NLP** (`data_pipeline/nlp/`): textual analysis of the scraped listing texts — French lexicon sentiment per commune + word frequencies; surfaced in the dashboard as a sentiment metric and a word cloud.
- **MongoDB** (docker-compose: mongo, :27017): the non-relational store — the Kafka bronze consumer archives raw listing JSON into `homepedia.listings_raw` alongside the Parquet lake.
- **Hive/HDFS** (docker-compose: namenode, datanode, metastore, hive-server): external tables over the gold/silver Parquet, queried by the API.
- **PostgreSQL/PostGIS** (docker-compose: postgres): `data_pipeline/export/load_postgres.py` loads reference tables, transactions and scores; `database/schema.sql` is applied automatically.
- **dbt** (`dbt/`): staging → intermediate → marts over the Postgres tables (`cd dbt && dbt run`).
- **Airflow** (docker-compose: airflow, UI on :8081): `homepedia_dvf_pipeline` DAG runs ingest → bronze → silver → gold → quality → load_postgres. `pipeline.sh`/`pipeline.bat` are the equivalent CLI orchestrators (they add the HDFS upload, which needs the host's docker CLI).
- **FastAPI** (`backend/`): serves Hive data (parameterized HiveQL); `/territories` is the bulk endpoint for BI/dashboard.
- **Streamlit** (`dashboard/`): reads the API when `HOMEPEDIA_API_URL` is set, falls back to local gold Parquet; live listings scraping on demand.
- **Grafana** (docker-compose: grafana, UI on :3000): BI layer — datasource and the HOMEPEDIA dashboard (KPIs, top communes, geomap) auto-provisioned from `grafana/`. Power BI remains a documented alternative over the same Hive views / Postgres marts (`docs/powerbi_views.md`).
- **CI** (`.github/workflows/ci.yml`): Python syntax checks, compose validation, dbt parse, pipeline smoke test on the sample DVF.

## Design notes

- Computation runs where the data volume justifies it: pandas for the MVP scale, Spark available for full-France DVF via the same interface and output contract.
- Both serving branches consume the same gold Parquet, so Hive and Postgres never disagree on numbers.
- The quality gate distinguishes systematic corruption (fails the pipeline) from expected small-commune noise (warns).

## MVP boundary

The DVF + commune reference path is the proven core. Network, transport and
socio-economic indicators enrich the territory scores when their sources have
been ingested; every enrichment is optional and degrades to a neutral score.
