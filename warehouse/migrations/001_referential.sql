-- Geographic referential: the spine of the platform.
-- Every dataset joins onto these tables through the INSEE code.

CREATE SCHEMA IF NOT EXISTS referential;

CREATE TABLE IF NOT EXISTS referential.region (
    code        varchar(3)  PRIMARY KEY,
    name        text        NOT NULL,
    geom        geometry(MultiPolygon, 4326)
);

CREATE TABLE IF NOT EXISTS referential.department (
    code        varchar(3)  PRIMARY KEY,
    name        text        NOT NULL,
    region_code varchar(3)  NOT NULL REFERENCES referential.region(code),
    geom        geometry(MultiPolygon, 4326)
);

CREATE TABLE IF NOT EXISTS referential.commune (
    code_insee      varchar(5)  PRIMARY KEY,
    name            text        NOT NULL,
    department_code varchar(3)  NOT NULL REFERENCES referential.department(code),
    region_code     varchar(3)  NOT NULL REFERENCES referential.region(code),
    population      integer,
    postal_codes    text[],
    geom            geometry(MultiPolygon, 4326)
);

-- spatial indexes (choropleths, point-in-polygon joins for DVF geolocation)
CREATE INDEX IF NOT EXISTS idx_region_geom     ON referential.region     USING gist (geom);
CREATE INDEX IF NOT EXISTS idx_department_geom ON referential.department USING gist (geom);
CREATE INDEX IF NOT EXISTS idx_commune_geom    ON referential.commune    USING gist (geom);

-- frequent lookups
CREATE INDEX IF NOT EXISTS idx_commune_department ON referential.commune (department_code);
CREATE INDEX IF NOT EXISTS idx_commune_name       ON referential.commune (name);
