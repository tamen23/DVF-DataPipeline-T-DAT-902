# Database Schema

The relational model is centered on communes.

## Dimensions

- `regions`
- `departements`
- `communes`

## Facts

- `real_estate_transactions`
- `network_coverage`
- `transport_access`
- `socio_economic_indicators`
- `territorial_scores`

## Design Principles

- `communes.code_commune` is the main geographic business key.
- Every fact table references `communes.id`.
- Source and import metadata are kept on fact tables.
- PostGIS geometry is available on communes for geographic queries.

