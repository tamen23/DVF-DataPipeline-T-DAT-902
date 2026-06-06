SELECT
    commune_id,
    EXTRACT(YEAR FROM date_mutation)::INTEGER AS year,
    COUNT(*) AS transaction_count,
    AVG(valeur_fonciere) AS avg_price,
    AVG(prix_m2) AS avg_price_m2,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY prix_m2) AS median_price_m2,
    AVG(surface_reelle_bati) AS avg_surface
FROM {{ ref('stg_real_estate_transactions') }}
GROUP BY commune_id, EXTRACT(YEAR FROM date_mutation)

