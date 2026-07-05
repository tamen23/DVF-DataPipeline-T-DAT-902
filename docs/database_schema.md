# Database Schema

Two schemas serve the same gold data:

- `database/schema.sql` — PostgreSQL/PostGIS relational model (this page),
  loaded by `data_pipeline.export.load_postgres`, consumed by dbt and psql.
- `database/hive_schema.sql` — Hive external tables over the HDFS Parquet
  files, consumed by the FastAPI backend and Power BI
  (tables: regions, departements, communes, gold_real_estate,
  gold_territory_scores, bronze_listings, silver_listings + views
  vw_commune_full, vw_ranking).

The relational model is centered on communes.

## Dimensions

- `regions`
- `departements`
- `communes`

## Facts

- `real_estate_transactions`
- `network_coverage`
- `transport_access`
- `socio_economic_indicators`
- `territorial_scores`

## Design Principles

- `communes.code_commune` is the main geographic business key.
- Every fact table references `communes.id`.
- Source and import metadata are kept on fact tables.
- PostGIS geometry is available on communes for geographic queries.

