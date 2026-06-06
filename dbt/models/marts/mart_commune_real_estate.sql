SELECT
    c.code_commune,
    c.nom_commune,
    c.population,
    r.year,
    r.transaction_count,
    ROUND(r.avg_price::numeric, 2) AS avg_price,
    ROUND(r.avg_price_m2::numeric, 2) AS avg_price_m2,
    ROUND(r.median_price_m2::numeric, 2) AS median_price_m2,
    ROUND(r.avg_surface::numeric, 2) AS avg_surface
FROM {{ ref('int_real_estate_commune_year') }} r
JOIN {{ ref('stg_communes') }} c
  ON c.commune_id = r.commune_id

