INSERT INTO regions (code_region, nom_region)
VALUES ('00', 'Unknown')
ON CONFLICT (code_region) DO NOTHING;

INSERT INTO departements (code_departement, nom_departement, region_id)
SELECT '00', 'Unknown', id
FROM regions
WHERE code_region = '00'
ON CONFLICT (code_departement) DO NOTHING;

