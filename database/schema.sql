CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS regions (
    id BIGSERIAL PRIMARY KEY,
    code_region VARCHAR(10) NOT NULL UNIQUE,
    nom_region TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS departements (
    id BIGSERIAL PRIMARY KEY,
    code_departement VARCHAR(10) NOT NULL UNIQUE,
    nom_departement TEXT NOT NULL,
    region_id BIGINT REFERENCES regions(id)
);

CREATE TABLE IF NOT EXISTS communes (
    id BIGSERIAL PRIMARY KEY,
    code_commune VARCHAR(10) NOT NULL UNIQUE,
    nom_commune TEXT NOT NULL,
    code_postal VARCHAR(10),
    departement_id BIGINT REFERENCES departements(id),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    population INTEGER,
    geom GEOMETRY(Point, 4326)
);

CREATE INDEX IF NOT EXISTS idx_communes_geom ON communes USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_communes_departement ON communes (departement_id);

CREATE TABLE IF NOT EXISTS real_estate_transactions (
    id BIGSERIAL PRIMARY KEY,
    date_mutation DATE,
    valeur_fonciere NUMERIC(14, 2),
    surface_reelle_bati NUMERIC(12, 2),
    nombre_pieces INTEGER,
    type_local TEXT,
    commune_id BIGINT REFERENCES communes(id),
    prix_m2 NUMERIC(14, 2),
    source TEXT,
    imported_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_real_estate_commune ON real_estate_transactions (commune_id);
CREATE INDEX IF NOT EXISTS idx_real_estate_date ON real_estate_transactions (date_mutation);

CREATE TABLE IF NOT EXISTS network_coverage (
    id BIGSERIAL PRIMARY KEY,
    commune_id BIGINT REFERENCES communes(id),
    operator TEXT NOT NULL,
    coverage_4g_score NUMERIC(5, 2),
    coverage_5g_score NUMERIC(5, 2),
    source TEXT,
    imported_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transport_access (
    id BIGSERIAL PRIMARY KEY,
    commune_id BIGINT REFERENCES communes(id),
    transport_score NUMERIC(5, 2),
    nearest_station_distance NUMERIC(10, 2),
    source TEXT,
    imported_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS socio_economic_indicators (
    id BIGSERIAL PRIMARY KEY,
    commune_id BIGINT REFERENCES communes(id),
    year INTEGER,
    median_income NUMERIC(12, 2),
    unemployment_rate NUMERIC(5, 2),
    population_density NUMERIC(10, 2),
    source TEXT,
    imported_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (commune_id, year)
);

CREATE TABLE IF NOT EXISTS territorial_scores (
    id BIGSERIAL PRIMARY KEY,
    commune_id BIGINT REFERENCES communes(id),
    year INTEGER NOT NULL,
    real_estate_score NUMERIC(5, 2),
    network_score NUMERIC(5, 2),
    transport_score NUMERIC(5, 2),
    socio_economic_score NUMERIC(5, 2),
    global_score NUMERIC(5, 2),
    computed_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (commune_id, year)
);

CREATE OR REPLACE VIEW vw_real_estate_commune_year AS
SELECT
    c.code_commune,
    c.nom_commune,
    EXTRACT(YEAR FROM t.date_mutation)::INTEGER AS year,
    COUNT(*) AS transaction_count,
    AVG(t.valeur_fonciere)::NUMERIC(14, 2) AS avg_price,
    AVG(t.prix_m2)::NUMERIC(14, 2) AS avg_price_m2,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY t.prix_m2)::NUMERIC(14, 2) AS median_price_m2
FROM real_estate_transactions t
JOIN communes c ON c.id = t.commune_id
WHERE t.prix_m2 IS NOT NULL
GROUP BY c.code_commune, c.nom_commune, EXTRACT(YEAR FROM t.date_mutation);

