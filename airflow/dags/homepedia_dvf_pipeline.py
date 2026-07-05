from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


# Mounted by the airflow service in docker-compose.yml (.:/opt/airflow/homepedia)
PROJECT_DIR = "/opt/airflow/homepedia"
YEAR = "{{ dag_run.conf.get('year', 2023) }}"
# Optional: pass {"dvf_input": "/path/or/url"} in the trigger conf; without it
# ingest_dvf downloads the official DataGouv file for the year.
DVF_INPUT_FLAG = (
    "{% if dag_run.conf.get('dvf_input') %}--input {{ dag_run.conf.get('dvf_input') }}{% endif %}"
)


with DAG(
    dag_id="homepedia_dvf_pipeline",
    description="Raw to gold DVF pipeline for HOMEPEDIA, loaded into Postgres.",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["homepedia", "dvf", "real-estate"],
) as dag:
    ingest_communes = BashOperator(
        task_id="ingest_communes",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.ingestion.ingest_communes",
    )

    ingest = BashOperator(
        task_id="ingest_dvf",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.ingestion.ingest_dvf {DVF_INPUT_FLAG} --year {YEAR}",
    )

    bronze = BashOperator(
        task_id="bronze_dvf",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.transformation.bronze_dvf --year {YEAR}",
    )

    silver = BashOperator(
        task_id="silver_dvf",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.cleaning.silver_dvf --year {YEAR}",
    )

    gold = BashOperator(
        task_id="gold_real_estate",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.transformation.gold_real_estate --year {YEAR}",
    )

    quality = BashOperator(
        task_id="quality_checks",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.quality_checks.check_gold --year {YEAR}",
    )

    load_postgres = BashOperator(
        task_id="load_postgres",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.export.load_postgres --year {YEAR}",
    )

    ingest >> bronze >> silver >> gold >> quality >> load_postgres
    ingest_communes >> load_postgres
