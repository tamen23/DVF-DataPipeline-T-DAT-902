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

Default formula:

```text
global_score =
  40% real_estate_score
+ 20% network_score
+ 20% transport_score
+ 20% socio_economic_score
```

Weights are configured in `config/score_weights.yml`.

For real estate, lower prices should produce a better affordability score. For investment-oriented scoring, the model can be inverted or combined with price evolution.

