-- Serving tables for rent indicators (Carte des loyers) and
-- socio-economic indicators (INSEE Filosofi).

CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.loyers_commune (
    code_insee        varchar(5) PRIMARY KEY,
    rent_m2_apartment numeric(8, 2),
    rent_m2_house     numeric(8, 2),
    nb_observations   integer,
    edition_year      integer
);

CREATE TABLE IF NOT EXISTS gold.filosofi_commune (
    code_insee    varchar(5) PRIMARY KEY,
    median_income numeric(10, 2),
    poverty_rate  numeric(5, 2),
    edition_year  integer
);
