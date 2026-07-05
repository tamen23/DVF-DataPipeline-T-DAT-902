-- HOMEPEDIA — Hive Schema
-- Tables are EXTERNAL: data lives in HDFS as Parquet files
-- The pipeline writes Parquet to HDFS, Hive just provides the SQL interface on top
--
-- MIGRATION NOTE (existing deployments only): the communes table LOCATION
-- moved to /homepedia/raw/communes/communes/. CREATE ... IF NOT EXISTS does
-- not relocate an existing table, so on a metastore created before this
-- change run first:
--   DROP TABLE IF EXISTS communes;
-- and remove the old flat files from HDFS:
--   hdfs dfs -rm /homepedia/raw/communes/*.parquet

CREATE DATABASE IF NOT EXISTS homepedia;
USE homepedia;

-- ── Reference tables ──────────────────────────────────────────────

CREATE EXTERNAL TABLE IF NOT EXISTS regions (
    code_region     STRING,
    nom_region      STRING
)
STORED AS PARQUET
LOCATION 'hdfs://namenode:8020/homepedia/raw/communes/regions/';

CREATE EXTERNAL TABLE IF NOT EXISTS departements (
    code_departement    STRING,
    nom_departement     STRING,
    code_region         STRING
)
STORED AS PARQUET
LOCATION 'hdfs://namenode:8020/homepedia/raw/communes/departements/';

CREATE EXTERNAL TABLE IF NOT EXISTS communes (
    code_commune        STRING,
    nom_commune         STRING,
    code_departement    STRING,
    code_region         STRING,
    latitude            DOUBLE,
    longitude           DOUBLE,
    population          INT
)
STORED AS PARQUET
LOCATION 'hdfs://namenode:8020/homepedia/raw/communes/communes/';

-- ── Gold — Real estate aggregates ─────────────────────────────────

CREATE EXTERNAL TABLE IF NOT EXISTS gold_real_estate (
    code_commune            STRING,
    nom_commune             STRING,
    year                    INT,
    transaction_count       BIGINT,
    avg_price               DOUBLE,
    avg_price_m2            DOUBLE,
    median_price_m2         DOUBLE,
    avg_surface             DOUBLE,
    price_m2_yoy_variation  DOUBLE
)
PARTITIONED BY (annee INT)
STORED AS PARQUET
LOCATION 'hdfs://namenode:8020/homepedia/gold/real_estate/';

-- ── Gold — Territory scores (main table for Streamlit & Power BI) ─

CREATE EXTERNAL TABLE IF NOT EXISTS gold_territory_scores (
    code_commune                STRING,
    nom_commune                 STRING,
    code_departement            STRING,
    code_region                 STRING,
    region                      STRING,
    latitude                    DOUBLE,
    longitude                   DOUBLE,
    population                  INT,
    avg_price_m2                DOUBLE,
    avg_price                   DOUBLE,
    median_price_m2             DOUBLE,
    transaction_count           BIGINT,
    annual_price_growth         DOUBLE,
    -- Scores (0-100)
    affordability_score         DOUBLE,
    transport_score             DOUBLE,
    network_score               DOUBLE,
    green_score                 DOUBLE,
    services_score              DOUBLE,
    education_score             DOUBLE,
    health_score                DOUBLE,
    investment_potential_score  DOUBLE,
    income_score                DOUBLE,
    -- Persona scores
    score_etudiant              DOUBLE,
    score_jeune_actif           DOUBLE,
    score_famille               DOUBLE,
    score_personne_agee         DOUBLE,
    score_investisseur          DOUBLE
)
STORED AS PARQUET
LOCATION 'hdfs://namenode:8020/homepedia/gold/territories/';

-- ── Gold — Real estate listings (from Kafka streaming) ───────────

CREATE EXTERNAL TABLE IF NOT EXISTS bronze_listings (
    listing_id      STRING,
    source          STRING,
    commune_code    STRING,
    city            STRING,
    price           DOUBLE,
    surface_m2      DOUBLE,
    price_m2        DOUBLE,
    rooms           INT,
    postal_code     STRING,
    property_type   STRING,
    url             STRING,
    scraped_at      STRING
)
PARTITIONED BY (source_date STRING, source_name STRING)
STORED AS PARQUET
LOCATION 'hdfs://namenode:8020/homepedia/bronze/listings/';

-- ── Silver — Listings aggregated per commune ──────────────────────

CREATE EXTERNAL TABLE IF NOT EXISTS silver_listings (
    code_commune            STRING,
    listing_count           BIGINT,
    avg_listing_price_m2    DOUBLE,
    median_listing_price_m2 DOUBLE,
    min_listing_price_m2    DOUBLE,
    max_listing_price_m2    DOUBLE,
    last_updated            STRING
)
PARTITIONED BY (source_name STRING)
STORED AS PARQUET
LOCATION 'hdfs://namenode:8020/homepedia/silver/listings/';

-- ── Useful views ──────────────────────────────────────────────────

-- silver_listings has one row per (source_name, commune): aggregate across
-- sources before joining so the view stays one row per commune.
CREATE OR REPLACE VIEW vw_commune_full AS
SELECT
    t.*,
    l.avg_listing_price_m2,
    l.listing_count
FROM gold_territory_scores t
LEFT JOIN (
    SELECT
        code_commune,
        AVG(avg_listing_price_m2) AS avg_listing_price_m2,
        SUM(listing_count)        AS listing_count
    FROM silver_listings
    GROUP BY code_commune
) l ON l.code_commune = t.code_commune;

CREATE OR REPLACE VIEW vw_ranking AS
SELECT
    code_commune,
    nom_commune,
    region,
    avg_price_m2,
    affordability_score,
    transport_score,
    network_score,
    score_etudiant,
    score_jeune_actif,
    score_famille,
    score_personne_agee,
    score_investisseur
FROM gold_territory_scores
ORDER BY score_etudiant DESC;
