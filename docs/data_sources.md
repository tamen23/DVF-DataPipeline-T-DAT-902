# Data Sources

## Version 1

### DVF

Usage:

- real estate transactions
- average price
- price per square meter
- annual evolution
- transaction volume

Expected fields:

- date mutation
- valeur fonciere
- surface reelle bati
- nombre pieces principales
- type local
- code commune
- commune
- code postal

### Commune Reference

Usage:

- commune, department, and region dimensions
- population if available
- latitude and longitude for maps

Recommended sources:

- INSEE official geographic code
- DataGouv commune datasets
- IGN or official administrative boundaries for geometry

## Version 2

### ARCEP / Mobile Coverage

Usage:

- 4G score
- 5G score
- best operator by commune

### Transport

Usage:

- nearest station distance
- simple transport accessibility score

Recommended sources:

- SNCF open data
- transport.data.gouv.fr
- GTFS feeds

## Version 3

Scraping and NLP can be added after the MVP. Possible sources include citizen reviews, city quality-of-life websites, and real estate portals, subject to terms of service.

## Supplied Documents CSV Files

The `Documents` folder contains large CSV files that were profiled and integrated as an external catalog, not as core HOMEPEDIA MVP inputs.

Generated report:

- `docs/documents_csv_analysis.md`

Generated app catalog:

- `data_lake/gold/external_catalog/documents_csv_profiles.json`

### KaDo.csv

Domain:

- retail / customer purchases

Conclusion:

- not useful for the HOMEPEDIA real-estate MVP
- useful as an annex big-data dataset for retail BI, customer segmentation, or basket analysis

### speech_time_mw.csv

Domain:

- media / gender representation

Conclusion:

- not useful for the HOMEPEDIA real-estate MVP
- useful as an annex dataset for time-series dashboards

### data_pathologies.csv

Domain:

- public health / territorial indicators

Conclusion:

- not part of the MVP
- potentially useful later as department/region-level territorial context, after DVF, transport, and network data are stable
