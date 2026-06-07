# KPI Definitions

## Real Estate

- `transaction_count`: number of valid DVF transactions.
- `avg_price`: average transaction price.
- `avg_price_m2`: average price per square meter.
- `median_price_m2`: median price per square meter.
- `avg_surface`: average built surface.
- `price_m2_yoy_variation`: `(price_m2_N - price_m2_N-1) / price_m2_N-1`.

## Network

- `coverage_4g_score`: normalized commune-level 4G score.
- `coverage_5g_score`: normalized commune-level 5G score.
- `network_score`: weighted average of 4G and 5G scores.

## Transport

- `nearest_station_distance`: distance to nearest station or stop.
- `transport_score`: normalized accessibility score.

## Socio-Economic

- `median_income`: median income by commune.
- `unemployment_rate`: unemployment rate.
- `population_density`: population divided by area.

## Global Score

The generated first version uses persona-specific scores. Each persona applies different weights to commune indicators.

Example:

```text
student_score =
  30% affordability_score
+ 25% transport_score
+ 25% education_score
+ 10% services_score
+ 10% network_score
```

Investment scoring uses:

```text
investment_potential_score =
  45% price_growth_score
+ 35% liquidity_score
+ 20% transport_score
```

Future default territorial formula:

```text
global_score =
  40% real_estate_score
+ 20% network_score
+ 20% transport_score
+ 20% socio_economic_score
```

Weights are configured in `config/score_weights.yml`.

For real estate, lower prices should produce a better affordability score. For investment-oriented scoring, the model can be inverted or combined with price evolution.

## Generated Demo Indicators

- `affordability_score`: inverse normalization of price per square meter.
- `transport_score`: generated accessibility to public transport.
- `network_score`: generated 4G/5G quality indicator.
- `green_score`: generated green-space and environmental comfort score.
- `services_score`: generated proximity to shops, daily services, and leisure.
- `education_score`: generated school and university access score.
- `health_score`: generated healthcare access score.
- `liquidity_score`: normalized transaction count.
- `price_growth_score`: normalized annual price growth.
