# HOMEPEDIA — Housing Market Intelligence Platform for France

## Topic

**Where to live, buy, rent, or invest in France — based on the best compromise between cost, accessibility, and quality of life?**

HOMEPEDIA centralizes scattered public data (DVF, INSEE, rents, reviews) into one interactive platform that tells you where to live, rent, or invest in France.

## Modules

### Module 1 — Buy

- Best cities to buy
- Price per m²
- Price evolution
- Investment score

### Module 2 — Rent

- Best cities to rent
- Average rents
- Rent-to-income ratio
- Tenant attractiveness score

### Module 3 — Compare

- Compare Paris vs Lyon vs Marseille
- Compare departments
- Compare regions

### Module 4 — Maps

- Heatmaps
- Choropleth maps
- Bubble maps

### Module 5 — AI Insights

- Sentiment analysis of city reviews
- Automatic recommendations: "Top 10 cities for families", "Top 10 cities for students"

### Module 6 — Accessibility (Analyse de l'accessibilité)

- Mobile network coverage (4G / 5G, effective coverage)
- Transport accessibility (stations, lines, service level)
- Announced / planned transport projects (future lines, upcoming stations)
- Territorial comparison on accessibility criteria

## Data sources (all free)

### Real estate — Module 1 (Buy)

- **DVF — Demandes de valeurs foncières** (files.data.gouv.fr, Etalab geolocated version): all property sales since 2014 — price, surface, type, date, location
- **DPE — ADEME**: energy performance of dwellings (labels A-G)
- **Sitadel2** (data.gouv.fr): building permits

### Rent — Module 2

- **Carte des loyers** (data.gouv.fr, Ministère de la Transition écologique): rent €/m² indicators per commune

### Territorial / socio-economic — Modules 3 & 5

- **INSEE Recensement**: population, density, age structure, housing stock
- **INSEE Filosofi**: median income, poverty rate
- **INSEE BPE** (Base Permanente des Équipements): schools, shops, doctors, sports facilities per commune
- **data.education.gouv.fr**: school directory, lycée results, IPS social index
- **SSMSI** (data.gouv.fr): crime/delinquency statistics per commune
- **data.ameli.fr**: pathologies dataset (department level)
- **Géorisques**: flood / seismic / industrial risk zones

### Accessibility — Module 6

- **ARCEP "Mon Réseau Mobile"** (open data): 4G/5G coverage per operator — theoretical maps and measured quality (commune-aggregated files)
- **transport.data.gouv.fr**: national GTFS hub — stops, lines, schedules (stops + routes only)
- **data.sncf.com**: stations, lines, punctuality
- **Société des Grands Projets / IDFM / regional portals**: announced lines and future stations
- **OpenStreetMap** (Geofabrik extracts): roads, amenities

### Geographic referential (foundation)

- **geo.api.gouv.fr**: official commune / department / region referential + INSEE codes (join key of the platform)
- **IGN Admin Express** or **france-geojson**: boundary polygons (GeoJSON) for the three levels
- **API Adresse (BAN)**: free geocoding

### Textual — Module 5 (AI Insights)

- **ville-ideale.fr** (scraping): resident reviews per city with sub-ratings
- **bien-dans-ma-ville.fr** (scraping, backup): same kind of reviews

### Ingestion policy

- Bronze: full raw copy of every source (Parquet)
- Silver: filtered columns / years / property types
- Gold: aggregates per commune / department / region
- Source-side filtering only for ARCEP and GTFS (pre-aggregated variants) and ville-ideale (incremental throttled scraping, top communes first)
- Priority: V1 = DVF, geo referential, INSEE recensement + Filosofi, Carte des loyers · V2 = ARCEP, transports, announced projects, BPE · V3 = scraping, education, crime, DPE

## Roadmap

### Version 1 — MVP: "the pipeline works, prices on a map"

- Infra up (Docker Compose local): Airflow, MinIO, Spark cluster, PostgreSQL/PostGIS, MongoDB (container present, empty), Streamlit
- Geographic referential: communes / departments / regions + INSEE codes + GeoJSON boundaries
- DVF integration end-to-end: Airflow DAG → bronze → Spark silver → gold → PostgreSQL, with Great Expectations checks and dbt models
- Easy V1 sources alongside: Carte des loyers, INSEE recensement + Filosofi
- Real estate indicators: price/m², price evolution, transaction volumes (+ basic rent indicators)
- Price cartography: choropleth with region → department → commune drill-down (Streamlit)
- Commune ranking (simple sort on indicators)
- Power BI dashboard (internal)

### Version 2 — Accessibility & scores: "the platform advises"

- ARCEP 4G/5G integration (effective coverage)
- Transport integration: GTFS stops/lines, SNCF stations
- Announced transport projects (future lines/stations — curated dataset)
- INSEE BPE (schools, shops, doctors, facilities)
- Composite scores (dbt models): territorial attractiveness score, investment score, tenant attractiveness score
- Compare module complete: multi-criteria side-by-side of cities / departments / regions
- Rule-based recommendations: "Top 10 for families / students / investors"

### Version 3 — AI & production: "intelligent and online"

- Scraping ville-ideale.fr (Scrapy, incremental) → MongoDB
- Text analysis: sentiment per city (French NLP model), word clouds
- AI Insights module complete: sentiment integrated into scores and recommendations; price-trend prediction (simple ML, documented)
- Enrichment sources: education results, crime stats, DPE, Géorisques
- VPS deployment: same compose + nginx → app online (bonus)
- Bonuses if time: auth/accounts, Grafana admin view, real-time updates (Redpanda)

## Infrastructure (final)

| Step | Tool |
|---|---|
| Orchestration | Apache Airflow |
| Ingestion | Python + Scrapy (Airflow tasks) |
| Data lake | MinIO + Parquet (medallion: raw / bronze / silver / gold) |
| Processing | Apache Spark cluster (1 master + 2 workers, PySpark) |
| Warehouse modeling | dbt (on PostgreSQL) |
| Data quality | Great Expectations |
| Relational database | PostgreSQL + PostGIS |
| Non-relational database | MongoDB |
| Application | Streamlit + Plotly + Folium (nginx on VPS) |
| Secondary dashboard | Power BI (internal, on PostgreSQL) |
| Infrastructure | Docker Compose — local first, then VPS |

## Repository structure

```
T-DAT-902-PAR_8/
├── docker-compose.yml          # the whole platform, one file
├── docker-compose.prod.yml     # VPS overrides (nginx, restart policies)
├── .env.example                # ports, passwords, bucket names (never commit .env)
├── Makefile                    # make up / make dvf / make app
├── README.md
│
├── doc/                        # specs, schema diagrams, defense material
├── data/                       # local sample files only — NOT the lake
│
├── infra/                      # everything Docker needs to build/configure services
│   ├── airflow/                #   Dockerfile + requirements.txt (providers, dbt, GE)
│   ├── spark/                  #   Dockerfile (Spark + S3A jars for MinIO)
│   ├── postgres/               #   init.sql (postgis extension, schemas, users)
│   ├── minio/                  #   bucket bootstrap (lake/bronze, silver, gold)
│   └── nginx/                  #   conf for the VPS only
│
├── ingestion/                  # getting data INTO bronze
│   ├── downloaders/            #   one module per source: dvf.py, insee.py, loyers.py...
│   └── scraper/                #   Scrapy project for ville-ideale (V3)
│
├── jobs/                       # PySpark transformations
│   ├── common/                 #   spark session factory, MinIO config, INSEE helpers
│   ├── silver/                 #   cleaning jobs
│   └── gold/                   #   aggregation jobs (commune / department / region)
│
├── orchestration/              # Airflow
│   └── dags/                   #   dvf_pipeline.py, referential.py...
│
├── warehouse/                  # serving layer
│   ├── dbt/                    #   dbt project: staging/ + marts/ (scores, rankings)
│   └── migrations/             #   Postgres DDL: referential tables, indexes
│
├── quality/                    # Great Expectations suites
│   └── expectations/           #   one suite per dataset
│
├── app/                        # Streamlit
│   ├── Home.py
│   ├── pages/                  #   1_Buy, 2_Rent, 3_Compare, 4_Maps, 5_AI, 6_Access
│   ├── components/             #   shared map widgets, charts
│   └── queries/                #   SQL/Mongo read functions (app only reads gold)
│
└── powerbi/                    # .pbix files
```

Principles:

- Folders follow the data flow: ingestion → jobs → orchestration → warehouse → quality → app
- One folder per team role
- The data lake (bronze/silver/gold) lives in MinIO volumes, never in the repo
- Compute happens in Spark/dbt; the app only reads gold tables
- docker-compose.prod.yml only adds what the VPS changes (nginx, restart policies, real secrets)
