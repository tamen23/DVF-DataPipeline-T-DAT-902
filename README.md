# HOMEPEDIA

Housing Market Intelligence Platform for France — Epitech T-DAT-902.

Full specification: [doc/HOMEPEDIA_specification.md](doc/HOMEPEDIA_specification.md)

## Quickstart

Requirements: Docker Desktop (≥ 8 GB RAM allocated).

```bash
cp .env.example .env   # then edit passwords if you want
make up                # or: docker compose up -d --build
```

First boot builds the images (several minutes).

| Service | URL | Credentials (.env) |
|---|---|---|
| Streamlit app | http://localhost:8501 | — |
| Airflow | http://localhost:8080 | AIRFLOW_ADMIN_USER / PASSWORD |
| Spark master UI | http://localhost:8081 | — |
| MinIO console | http://localhost:9001 | MINIO_ROOT_USER / PASSWORD |
| PostgreSQL | localhost:5432 | POSTGRES_USER / PASSWORD |
| MongoDB | localhost:27017 | MONGO_USER / PASSWORD |

To verify the platform: open the Streamlit app (all status cards green) and
trigger the `platform_healthcheck` DAG in Airflow.
