SELECT
    id,
    date_mutation,
    valeur_fonciere,
    surface_reelle_bati,
    nombre_pieces,
    type_local,
    commune_id,
    prix_m2,
    source,
    imported_at
FROM {{ source('public', 'real_estate_transactions') }}
WHERE prix_m2 IS NOT NULL

