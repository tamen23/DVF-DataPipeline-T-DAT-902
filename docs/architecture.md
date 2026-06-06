# Architecture

HOMEPEDIA follows a lakehouse-style local architecture compatible with AWS or Azure.

## Layers

- `raw`: immutable input files from DVF, INSEE, DataGouv, ARCEP, and transport APIs.
- `bronze`: standardized files with normalized column names and Parquet storage.
- `silver`: cleaned business entities with typed columns and normalized commune codes.
- `gold`: BI-ready marts with KPIs, rankings, and scores.

## Components

- Python ingestion scripts collect files and preserve import metadata.
- Pandas handles MVP transformations.
- PySpark is available for high-volume DVF aggregations.
- PostgreSQL/PostGIS stores relational and geographic data.
- DBT documents and models BI marts.
- Airflow orchestrates the end-to-end pipeline.
- Power BI is the main BI layer.
- Streamlit is provided as a rapid prototype.
- FastAPI exposes selected indicators when an API layer is needed.

## Target Flow

```text
CSV/API
  -> raw
  -> bronze Parquet
  -> silver Parquet
  -> gold Parquet
  -> PostgreSQL/PostGIS
  -> DBT marts
  -> Power BI / API / Streamlit
```

## MVP Boundary

The first version should only prove the full data path with DVF and commune reference data. Network, transport, and socio-economic indicators are added once the pipeline is stable.

