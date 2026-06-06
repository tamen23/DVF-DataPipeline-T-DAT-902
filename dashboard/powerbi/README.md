# Power BI Dashboard Specification

Connect Power BI to PostgreSQL or to the generated gold Parquet files.

Recommended pages:

1. Global Overview
   - commune count
   - average price per square meter
   - average territorial score
   - top attractive cities

2. Real Estate Analysis
   - average price
   - average price per square meter
   - annual evolution
   - filters: region, department, commune

3. Interactive Map
   - price per square meter
   - global score
   - mobile network score
   - transport score

4. Territory Comparison
   - compare 2 to 5 communes
   - radar chart
   - KPI table

5. Ranking
   - top cities by global score
   - affordable cities
   - connected cities
   - investment candidates

6. Commune Detail
   - commune profile
   - real estate
   - network
   - transport
   - socio-economics
   - final score

Main table for MVP:

- `mart_commune_real_estate`

Future V2 model:

- `territorial_scores`
- `network_coverage`
- `transport_access`
- `socio_economic_indicators`

