SELECT
    id AS commune_id,
    code_commune,
    nom_commune,
    code_postal,
    departement_id,
    latitude,
    longitude,
    population
FROM {{ source('public', 'communes') }}

